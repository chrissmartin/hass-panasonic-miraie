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
    PRESET_CLEAN,
    PRESET_CONVERTI7_40,
    PRESET_CONVERTI7_55,
    PRESET_CONVERTI7_70,
    PRESET_CONVERTI7_80,
    PRESET_CONVERTI7_90,
    PRESET_CONVERTI7_FC,
    PRESET_CONVERTI7_HC,
    PRESET_CONVERTI7_OFF,
    PRESET_ECONOMY,
    PRESET_MODES,
    PRESET_NANOE,
    PRESET_NANOE_ECONOMY,
    PRESET_NANOE_POWERFUL,
    PRESET_NONE,
    PRESET_POWERFUL,
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
    _attr_preset_modes = list(PRESET_MODES.keys())
    _attr_translation_key = "panasonic_miraie"
    _update_lock = asyncio.Lock()
    _command_lock = asyncio.Lock()
    _last_update_success = False
    _missed_updates = 0
    _state_via_mqtt = {}

    # Converti7 mode mapping
    CONVERTI7_TO_PAYLOAD_MAP = {
        PRESET_CONVERTI7_HC: "110",
        PRESET_CONVERTI7_FC: "100",
        PRESET_CONVERTI7_90: "90",
        PRESET_CONVERTI7_80: "80",
        PRESET_CONVERTI7_70: "70",
        PRESET_CONVERTI7_55: "55",
        PRESET_CONVERTI7_40: "40",
        PRESET_CONVERTI7_OFF: "0",
    }

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
            | ClimateEntityFeature.PRESET_MODE
        )
        self._attr_available = True  # Start optimistically
        self._mqtt_state_received_after_command = False
        self._command_time = 0
        self._attr_preset_mode = PRESET_NONE

        # Initialize entity attributes
        self._attr_extra_state_attributes = {
            "nanoe_g": False,
            "powerful_mode": False,
            "economy_mode": False,
            "clean_mode": False,
            "converti7_mode": None,
            "filter_dust_level": None,
            "filter_cleaning_required": None,
            "errors": None,
            "warnings": None,
            "last_update_success": False,
        }

        # Initialize preset mode

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

    def _update_swing_mode(self, payload: dict[str, Any]) -> None:
        """Update swing mode based on payload data.

        Args:
            payload: The state payload containing swing mode data.

        """
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

    def _update_preset_mode(
        self,
        payload: dict[str, Any],
        nanoe_active: bool,
        powerful_active: bool,
        economy_active: bool,
        clean_active: bool,
    ) -> None:
        """Update preset mode based on active features and Converti7 mode.

        Args:
            payload: The state payload containing Converti7 data.
            nanoe_active: Whether nanoe mode is active.
            powerful_active: Whether powerful mode is active.
            economy_active: Whether economy mode is active.
            clean_active: Whether clean mode is active.

        """
        # Set the preset mode based on active features
        if nanoe_active and powerful_active:
            self._attr_preset_mode = PRESET_NANOE_POWERFUL
        elif nanoe_active and economy_active:
            self._attr_preset_mode = PRESET_NANOE_ECONOMY
        elif nanoe_active:
            self._attr_preset_mode = PRESET_NANOE
        elif powerful_active:
            self._attr_preset_mode = PRESET_POWERFUL
        elif economy_active:
            self._attr_preset_mode = PRESET_ECONOMY
        elif clean_active:
            self._attr_preset_mode = PRESET_CLEAN
        else:
            self._attr_preset_mode = PRESET_NONE

        # Handle Converti7 mode
        # Check for cnv field first, then fall back to accm for compatibility
        cnv_value = payload.get("cnv")
        accm_value = payload.get("accm")
        converti7_value = str(cnv_value) if cnv_value is not None else accm_value

        self._attr_extra_state_attributes["converti7_mode"] = converti7_value

        # Use the centralized mapping for Converti7 modes
        # Use the reverse mapping for Converti7 modes
        payload_to_converti7_map = {
            v: k for k, v in self.CONVERTI7_TO_PAYLOAD_MAP.items()
        }

        if converti7_value in payload_to_converti7_map:
            converti7_preset = payload_to_converti7_map[converti7_value]

            # Only set Converti7 preset if it's active (not OFF)
            # Never set to PRESET_CONVERTI7_OFF as that duplicates PRESET_NONE functionality
            if converti7_preset != PRESET_CONVERTI7_OFF:
                self._attr_preset_mode = converti7_preset
            elif self._attr_preset_mode == PRESET_CONVERTI7_OFF:
                # If currently showing PRESET_CONVERTI7_OFF, set to PRESET_NONE instead
                self._attr_preset_mode = PRESET_NONE

    async def _handle_state_update(self, topic: str, payload: dict[str, Any]) -> None:  # noqa: C901
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

            rmtmp = payload.get("rmtmp")
            self._attr_current_temperature = float(rmtmp) if rmtmp is not None else None
            actmp = payload.get("actmp")
            self._attr_target_temperature = float(actmp) if actmp is not None else None

            is_power_on = payload.get("ps") == "on"
            hvac_mode_str = payload.get("acmd")

            self._attr_hvac_mode = (
                self.HVAC_MODE_MAP.get(hvac_mode_str, HVACMode.OFF)
                if is_power_on
                else HVACMode.OFF
            )

            acfs_value = payload.get("acfs")
            self._attr_fan_mode = (
                FAN_MODE_MAP.get(acfs_value, FAN_AUTO) if acfs_value else FAN_AUTO
            )

            # Update swing mode
            self._update_swing_mode(payload)

            # Get the status of special modes
            nanoe_active = payload.get("acng") == "on"
            powerful_active = payload.get("acpm") == "on"
            clean_active = payload.get("acec") == "on"
            economy_active = payload.get("acem") == "on"

            # Update preset mode based on active features
            self._update_preset_mode(
                payload, nanoe_active, powerful_active, economy_active, clean_active
            )

            # Update entity attributes
            self._attr_extra_state_attributes.update(
                {
                    "nanoe_g": nanoe_active,
                    "powerful_mode": powerful_active,
                    "economy_mode": economy_active,
                    "clean_mode": clean_active,
                    "filter_dust_level": payload.get("filterDustLevel"),
                    "filter_cleaning_required": payload.get("filterCleaningRequired"),
                    "errors": payload.get("errors"),
                    "warnings": payload.get("warnings"),
                    "last_update_success": self._last_update_success,
                    # "converti7_mode" is already updated in _update_preset_mode
                }
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
                    await asyncio.sleep(2)

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

    @_track_command
    async def _handle_converti7_preset(self, preset_mode: str) -> bool:
        """Handle Converti7 preset mode setting.

        Args:
            preset_mode: The Converti7 preset mode to set.

        Returns:
            bool: True if successful, False otherwise.

        """
        if self._attr_hvac_mode != HVACMode.COOL:
            _LOGGER.warning(
                "Converti7 can only be used in Cool mode. Current mode: %s",
                self._attr_hvac_mode,
            )
            # Revert optimistic update
            self.async_schedule_update_ha_state(True)
            return False

        numeric_value_str = self.CONVERTI7_TO_PAYLOAD_MAP[preset_mode]

        success = await self._send_command(
            self._api.set_converti7_mode, self._device_topic, numeric_value_str
        )

        if success:
            # Turn off other modes
            if (
                await self._send_command(self._api.set_nanoe, self._device_topic, False)
                is False
            ):
                success = False  # Log if this fails but continue
            if (
                await self._send_command(
                    self._api.set_powerful_mode, self._device_topic, False
                )
                is False
            ):
                success = False
            if (
                await self._send_command(
                    self._api.set_economy_mode, self._device_topic, False
                )
                is False
            ):
                success = False

        if not success:
            _LOGGER.warning(
                "Failed to set Converti7 mode for %s after retries", self._attr_name
            )
            self.async_schedule_update_ha_state(True)

        return success

    async def _handle_special_modes(self, preset_mode: str) -> bool:
        """Handle setting special modes (nanoe, powerful, economy, clean).

        Args:
            preset_mode: The preset mode to determine which special modes to activate.

        Returns:
            bool: True if all commands succeeded, False otherwise.

        """
        # Determine which special modes to enable/disable based on preset mode
        nanoe_active = preset_mode in [
            PRESET_NANOE,
            PRESET_NANOE_POWERFUL,
            PRESET_NANOE_ECONOMY,
        ]
        powerful_active = preset_mode in [PRESET_POWERFUL, PRESET_NANOE_POWERFUL]
        economy_active = preset_mode in [PRESET_ECONOMY, PRESET_NANOE_ECONOMY]
        clean_active = preset_mode == PRESET_CLEAN

        # Can't have multiple special modes active at once
        if powerful_active and economy_active:
            _LOGGER.warning(
                "Cannot activate both powerful and economy modes. Defaulting to powerful."
            )
            economy_active = False

        if clean_active and (powerful_active or economy_active or nanoe_active):
            _LOGGER.warning(
                "Cannot activate clean mode with other modes. Defaulting to clean only."
            )
            powerful_active = False
            economy_active = False
            nanoe_active = False

        # Send commands to update device state for Nanoe, Powerful, Economy, Clean
        success = True
        if (
            await self._send_command(
                self._api.set_nanoe, self._device_topic, nanoe_active
            )
            is False
        ):
            success = False
        if (
            await self._send_command(
                self._api.set_powerful_mode, self._device_topic, powerful_active
            )
            is False
        ):
            success = False
        if (
            await self._send_command(
                self._api.set_economy_mode, self._device_topic, economy_active
            )
            is False
        ):
            success = False
        if (
            await self._send_command(
                self._api.set_clean_mode, self._device_topic, clean_active
            )
            is False
        ):
            success = False

        return success

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode.

        Args:
            preset_mode: The new preset mode to set.

        Returns:
            None

        """
        _LOGGER.debug(
            "Setting preset mode for %s to %s (%s)",
            self._attr_name,
            preset_mode,
            PRESET_MODES.get(preset_mode, {}).get("name", preset_mode),
        )

        # Update state optimistically
        self._attr_preset_mode = preset_mode
        self.async_write_ha_state()

        success = True  # Initialize success to True

        if preset_mode in self.CONVERTI7_TO_PAYLOAD_MAP:
            success = await self._handle_converti7_preset(preset_mode)
            return  # Processed Converti7, so exit

        # Handle setting to PRESET_NONE or PRESET_CONVERTI7_OFF
        # Both should result in all modes being turned off
        if preset_mode in (PRESET_NONE, PRESET_CONVERTI7_OFF):
            _LOGGER.debug(
                "Setting to %s for %s, turning off all modes",
                preset_mode,
                self._attr_name,
            )
            # Turn off Converti7 first
            await self._send_command(
                self._api.set_converti7_mode, self._device_topic, "0"
            )

        # If not a Converti7 mode, ensure Converti7 is turned off (set to "0")
        # This will also handle other non-Converti7 presets
        # Get current converti7 mode and ensure it's a string for comparison
        current_converti7 = str(
            self._attr_extra_state_attributes.get("converti7_mode", "0")
        )
        if current_converti7 != "0" and current_converti7 != "None":
            converti7_result = await self._send_command(
                self._api.set_converti7_mode, self._device_topic, "0"
            )
            if converti7_result is False:
                success = False  # Log if this fails but continue with other modes
                _LOGGER.warning(
                    "Failed to turn off Converti7 mode for %s when setting %s mode",
                    self._attr_name,
                    preset_mode,
                )

        # Handle special modes (nanoe, powerful, economy, clean)
        special_modes_success = await self._handle_special_modes(preset_mode)
        if not special_modes_success:
            success = False

        if not success:
            _LOGGER.warning(
                "Failed to set preset mode for %s after retries (some operations might have failed)",
                self._attr_name,
            )
            # Schedule an update to get the correct state
            self.async_schedule_update_ha_state(True)

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        return self._attr_hvac_mode

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

    @property
    def preset_modes(self) -> list[str]:
        """Return available preset modes."""
        modes = list(PRESET_MODES.keys())
        # Remove redundant Converti7 Off as it duplicates None functionality
        if PRESET_CONVERTI7_OFF in modes:
            modes.remove(PRESET_CONVERTI7_OFF)
        return modes
