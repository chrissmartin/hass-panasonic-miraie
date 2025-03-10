"""Support for Panasonic MirAIe AC climate devices."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_DIFFUSE,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    SWING_BOTH,
    SWING_HORIZONTAL,
    SWING_OFF,
    SWING_ON,
    SWING_VERTICAL,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    API_COMMAND_TIMEOUT,
    API_TIMEOUT,
    CLIMATE_COMMAND_RETRY,
    CLIMATE_UPDATE_INTERVAL,
    DOMAIN,
)
from .decorators.track_command import _track_command

_LOGGER = logging.getLogger(__name__)

HVAC_MODE_MAP = {
    "off": HVACMode.OFF,
    "auto": HVACMode.AUTO,
    "cool": HVACMode.COOL,
    "heat": HVACMode.HEAT,
    "dry": HVACMode.DRY,
    "fan": HVACMode.FAN_ONLY,
}

FAN_MODE_MAP = {
    "auto": FAN_AUTO,
    "low": FAN_LOW,
    "medium": FAN_MEDIUM,
    "high": FAN_HIGH,
    "quiet": FAN_DIFFUSE,
}

SWING_MODE_MAP = {
    SWING_OFF: "3",
    SWING_ON: "0",
    SWING_VERTICAL: "0",
    SWING_HORIZONTAL: "0",
    SWING_BOTH: "0",
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Panasonic MirAIe climate platform.

    Args:
        hass: The Home Assistant instance.
        config_entry: The config entry.
        async_add_entities: Callback to add new entities.

    Returns:
        None

    """
    api = hass.data[DOMAIN][config_entry.entry_id]

    try:
        async with asyncio.timeout(API_TIMEOUT):
            devices = await api.get_devices()
            _LOGGER.debug("Retrieved devices: %s", devices)
    except TimeoutError:
        _LOGGER.error("Timeout retrieving devices from Panasonic MirAIe API")
        devices = []
    except Exception as e:
        _LOGGER.error("Error retrieving devices: %s", e)
        devices = []

    entities = []
    for device in devices:
        topic = device["topic"][0] if device["topic"] else None
        if topic:
            entities.append(
                PanasonicMirAIeClimate(
                    api,
                    topic,
                    device["deviceName"],
                    device["deviceId"],
                )
            )
        else:
            _LOGGER.warning(
                "Device %s (%s) has no MQTT topic, skipping",
                device["deviceName"],
                device["deviceId"],
            )

    if entities:
        _LOGGER.info("Adding %d Panasonic MirAIe climate entities", len(entities))
        async_add_entities(entities)
    else:
        _LOGGER.warning("No valid Panasonic MirAIe climate entities found")


class PanasonicMirAIeClimate(ClimateEntity):
    """Representation of a Panasonic MirAIe climate device."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 16
    _attr_max_temp = 30
    _attr_hvac_modes = list(HVAC_MODE_MAP.values())
    _attr_fan_modes = list(FAN_MODE_MAP.values())
    _attr_swing_modes = list(SWING_MODE_MAP.keys())
    _update_lock = asyncio.Lock()
    _command_lock = asyncio.Lock()
    _last_update_success = False
    _missed_updates = 0
    _state_via_mqtt = {}

    def __init__(self, api, device_topic, device_name, device_id):
        """Initialize the climate device.

        Args:
            api: The API instance for communicating with the device.
            device_topic: The MQTT topic for the device.
            device_name: The name of the device.
            device_id: The unique identifier of the device.

        """
        self._api = api
        self._device_topic = device_topic
        self._device_id = device_id
        self._attr_name = device_name
        self._attr_unique_id = f"panasonic_miraie_{device_id}"
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.SWING_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        self._attr_available = True  # Start optimistically
        self._mqtt_state_received_after_command = False
        self._command_time = 0

        _LOGGER.debug(
            "Initialized climate entity: %s with topic %s",
            self._attr_name,
            self._device_topic,
        )

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass.

        Returns:
            None

        """
        await super().async_added_to_hass()
        _LOGGER.debug("Entity %s added to HASS", self._attr_name)

        # Subscribe to state updates via MQTT
        try:
            await self._api.mqtt_handler.subscribe(
                f"{self._device_topic}/state", self._handle_state_update
            )

            # Get initial state
            await self.async_update()
        except Exception as e:
            _LOGGER.error("Error setting up entity %s: %s", self._attr_name, e)
            self._attr_available = False

        # Schedule periodic updates
        self.async_on_remove(
            async_track_time_interval(
                self.hass,
                self.async_update,
                timedelta(seconds=CLIMATE_UPDATE_INTERVAL),
            )
        )

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass.

        Returns:
            None

        """
        await super().async_will_remove_from_hass()
        try:
            await self._api.mqtt_handler.unsubscribe(f"{self._device_topic}/state")
        except Exception as e:
            _LOGGER.error("Error unsubscribing %s: %s", self._attr_name, e)

    async def async_update(self, *_: Any) -> None:
        """Fetch new state data for this entity.

        Returns:
            None

        """
        # Skip if update is already in progress
        if self._update_lock.locked():
            _LOGGER.debug(
                "Update already in progress for %s, skipping", self._attr_name
            )
            return

        async with self._update_lock:
            try:
                _LOGGER.debug("[async_update] Updating device ID: %s", self._device_id)

                # Set a timeout for the API call
                async with asyncio.timeout(API_TIMEOUT):
                    state = await self._api.get_device_state(self._device_id)

                if state:
                    await self._handle_state_update(self._device_topic, state)
                    self._last_update_success = True
                    self._missed_updates = 0
                else:
                    _LOGGER.warning("Received empty state for %s", self._attr_name)
                    self._increment_missed_updates()
            except TimeoutError:
                _LOGGER.error(
                    "Timeout getting state for %s - API request took too long",
                    self._attr_name,
                )
                self._increment_missed_updates()
            except Exception as e:
                _LOGGER.error("Error updating %s: %s", self._attr_name, e)
                self._increment_missed_updates()
            finally:
                # Always update HA state at the end of update
                self.async_write_ha_state()

    def _increment_missed_updates(self):
        """Handle missed updates by tracking consecutive failures."""
        self._last_update_success = False
        self._missed_updates += 1

        # After 3 consecutive missed updates, mark as unavailable
        # unless we're still getting MQTT updates
        if self._missed_updates >= 3 and not self._state_via_mqtt:
            _LOGGER.warning(
                "Entity %s marked unavailable after %d missed updates",
                self._attr_name,
                self._missed_updates,
            )
            self._attr_available = False

    async def _handle_state_update(self, topic: str, payload: dict[str, Any]) -> None:
        """Handle state updates from the API or MQTT.

        Args:
            topic: The MQTT topic of the update.
            payload: The state payload.

        Returns:
            None

        """
        if not payload:
            _LOGGER.warning("Received empty payload for %s", self._attr_name)
            return

        try:
            # Store the most recent MQTT state update
            if topic.endswith("/state"):
                self._state_via_mqtt = payload

                # Check if this is a response to a recently sent command
                if time.time() - self._command_time < 5:  # Within 5 seconds of command
                    self._mqtt_state_received_after_command = True
                    _LOGGER.debug("Received MQTT update after command")

            online_status = payload.get("onlineStatus")
            self._attr_available = online_status == "true"

            self._attr_current_temperature = (
                float(payload["rmtmp"]) if payload.get("rmtmp") else None
            )
            self._attr_target_temperature = (
                float(payload["actmp"]) if payload.get("actmp") else None
            )

            is_power_on = payload.get("ps") == "on"
            hvac_mode_str = payload.get("acmd")

            self._attr_hvac_mode = (
                HVAC_MODE_MAP.get(hvac_mode_str, HVACMode.OFF)
                if is_power_on
                else HVACMode.OFF
            )

            self._attr_fan_mode = FAN_MODE_MAP.get(payload.get("acfs"), FAN_AUTO)

            vertical_swing = payload.get("acvs")
            horizontal_swing = payload.get("achs")

            if vertical_swing == "0" and horizontal_swing == "0":
                self._attr_swing_mode = SWING_BOTH
            elif vertical_swing == "0":
                self._attr_swing_mode = SWING_VERTICAL
            elif horizontal_swing == "0":
                self._attr_swing_mode = SWING_HORIZONTAL
            else:
                self._attr_swing_mode = SWING_OFF

            self._attr_extra_state_attributes = {
                "nanoe_g": payload.get("acng") == "on",
                "powerful_mode": payload.get("acpm") == "on",
                "economy_mode": payload.get("acec") == "on",
                "filter_dust_level": payload.get("filterDustLevel"),
                "filter_cleaning_required": payload.get("filterCleaningRequired"),
                "errors": payload.get("errors"),
                "warnings": payload.get("warnings"),
                "last_update_success": self._last_update_success,
            }

            _LOGGER.debug(
                "Updated state for %s: HVAC Mode - %s, Fan Mode - %s, Swing Mode - %s, Temperature - %s",
                self._attr_name,
                self._attr_hvac_mode,
                self._attr_fan_mode,
                self._attr_swing_mode,
                self._attr_target_temperature,
            )

            # Mark entity as available as we received a valid state update
            self._attr_available = True
            self._missed_updates = 0

            # Update the state in Home Assistant
            self.async_write_ha_state()
        except Exception as e:
            _LOGGER.error("Error handling state update for %s: %s", self._attr_name, e)

    async def _send_command(self, command_fn, *args, **kwargs):
        """Send a command with retry logic and timeout.

        Args:
            command_fn: The API function to call for sending the command
            *args: Arguments to pass to the command function
            **kwargs: Keyword arguments to pass to the command function

        Returns:
            bool: True if command succeeded, False otherwise

        """
        success = False

        # Use a lock to prevent overlapping commands
        async with self._command_lock:
            for attempt in range(CLIMATE_COMMAND_RETRY + 1):
                if attempt > 0:
                    _LOGGER.debug(
                        "Retrying command for %s (attempt %d/%d)",
                        self._attr_name,
                        attempt,
                        CLIMATE_COMMAND_RETRY,
                    )
                    # Wait briefly before retrying
                    await asyncio.sleep(1)

                try:
                    # Set a timeout for the command
                    async with asyncio.timeout(API_COMMAND_TIMEOUT):
                        await command_fn(*args, **kwargs)
                    success = True

                    # Wait a short time for state update to arrive via MQTT
                    await asyncio.sleep(0.5)

                    # If we haven't received an MQTT update after the wait,
                    # request a state update directly
                    if success and not self._mqtt_state_received_after_command:
                        _LOGGER.debug(
                            "No MQTT update received, requesting state update"
                        )
                        self.hass.async_create_task(self.async_update())

                    break
                except TimeoutError:
                    _LOGGER.error("Timeout sending command to %s", self._attr_name)
                except Exception as e:
                    _LOGGER.error(
                        "Failed to send command to %s: %s", self._attr_name, e
                    )

        return success

    @_track_command
    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature.

        Args:
            **kwargs: Keyword arguments containing the new temperature.

        Returns:
            None

        """
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            _LOGGER.debug(
                "Setting temperature for %s to %s", self._attr_name, temperature
            )

            # Update state optimistically
            self._attr_target_temperature = float(temperature)
            self.async_write_ha_state()

            # Send command with retry logic
            success = await self._send_command(
                self._api.set_temperature, self._device_topic, temperature
            )

            if not success:
                _LOGGER.warning(
                    "Failed to set temperature for %s after retries", self._attr_name
                )
                # Schedule an update to get the correct state
                self.async_schedule_update_ha_state(True)

    @_track_command
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode.

        Args:
            hvac_mode: The new HVAC mode to set.

        Returns:
            None

        """
        _LOGGER.debug("Setting HVAC mode for %s to %s", self._attr_name, hvac_mode)

        # Update state optimistically
        self._attr_hvac_mode = hvac_mode
        self.async_write_ha_state()

        success = False
        if hvac_mode == HVACMode.OFF:
            success = await self._send_command(
                self._api.set_power, self._device_topic, "off"
            )
        else:
            # First ensure the device is on
            power_success = await self._send_command(
                self._api.set_power, self._device_topic, "on"
            )

            if power_success:
                # Then set the mode
                miraie_mode = next(
                    (k for k, v in HVAC_MODE_MAP.items() if v == hvac_mode), None
                )
                if miraie_mode:
                    success = await self._send_command(
                        self._api.set_mode, self._device_topic, miraie_mode
                    )

        if not success:
            _LOGGER.warning(
                "Failed to set HVAC mode for %s after retries", self._attr_name
            )
            # Schedule an update to get the correct state
            self.async_schedule_update_ha_state(True)

    @_track_command
    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode.

        Args:
            fan_mode: The new fan mode to set.

        Returns:
            None

        """
        _LOGGER.debug("Setting fan mode for %s to %s", self._attr_name, fan_mode)

        # Update state optimistically
        self._attr_fan_mode = fan_mode
        self.async_write_ha_state()

        miraie_fan_mode = next(
            (k for k, v in FAN_MODE_MAP.items() if v == fan_mode), None
        )

        if miraie_fan_mode:
            success = await self._send_command(
                self._api.set_fan_mode, self._device_topic, miraie_fan_mode
            )

            if not success:
                _LOGGER.warning(
                    "Failed to set fan mode for %s after retries", self._attr_name
                )
                # Schedule an update to get the correct state
                self.async_schedule_update_ha_state(True)

    @_track_command
    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new target swing operation.

        Args:
            swing_mode: The new swing mode to set.

        Returns:
            None

        """
        _LOGGER.debug("Setting swing mode for %s to %s", self._attr_name, swing_mode)

        # Update state optimistically
        self._attr_swing_mode = swing_mode
        self.async_write_ha_state()

        miraie_swing_mode = SWING_MODE_MAP.get(swing_mode)
        if miraie_swing_mode:
            success = await self._send_command(
                self._api.set_swing_mode, self._device_topic, miraie_swing_mode
            )

            if not success:
                _LOGGER.warning(
                    "Failed to set swing mode for %s after retries", self._attr_name
                )
                # Schedule an update to get the correct state
                self.async_schedule_update_ha_state(True)

    @property
    def device_info(self):
        """Return device information.

        Returns:
            dict: A dictionary containing device information.

        """
        return {
            "identifiers": {(DOMAIN, self._device_id)},
            "name": self._attr_name,
            "manufacturer": "Panasonic",
            "model": "MirAIe AC",
        }
