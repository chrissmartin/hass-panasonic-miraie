"""Support for Panasonic MirAI.e AC climate devices."""

from __future__ import annotations

from datetime import timedelta
import logging
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

from .const import DOMAIN

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
    """Set up the Panasonic MirAI.e climate platform.

    Args:
        hass: The Home Assistant instance.
        config_entry: The config entry.
        async_add_entities: Callback to add new entities.

    Returns:
        None

    """
    api = hass.data[DOMAIN][config_entry.entry_id]
    devices = await api.get_devices()
    _LOGGER.debug("Retrieved devices: %s", devices)

    entities = [
        PanasonicMirAIeClimate(
            api,
            device["topic"][0] if device["topic"] else None,
            device["deviceName"],
            device["deviceId"],
        )
        for device in devices
    ]

    _LOGGER.info("Adding %d Panasonic MirAI.e climate entities", len(entities))
    async_add_entities(entities)


class PanasonicMirAIeClimate(ClimateEntity):
    """Representation of a Panasonic MirAI.e climate device."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 16
    _attr_max_temp = 30
    _attr_hvac_modes = list(HVAC_MODE_MAP.values())
    _attr_fan_modes = list(FAN_MODE_MAP.values())
    _attr_swing_modes = list(SWING_MODE_MAP.keys())

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

        try:
            await self._api.mqtt_handler.subscribe(
                f"{self._device_topic}/state", self._handle_state_update
            )
            await self.async_update()
        except Exception as e:
            _LOGGER.error("Error setting up entity %s: %s", self._attr_name, e)
            self._attr_available = False

        self.async_on_remove(
            async_track_time_interval(
                self.hass, self.async_update, timedelta(minutes=5)
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

    async def async_update(self) -> None:
        """Fetch new state data for this entity.

        Returns:
            None

        """
        try:
            state = await self._api.get_device_state(self._device_id)
            await self._handle_state_update(self._device_topic, state)
        except Exception as e:
            _LOGGER.error("Error updating %s: %s", self._attr_name, e)
            self._attr_available = False
            self.async_write_ha_state()

    async def _handle_state_update(self, topic: str, payload: dict[str, Any]) -> None:
        """Handle state updates from the API.

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
            self._attr_available = payload.get("onlineStatus") == "true"
            self._attr_current_temperature = (
                float(payload["rmtmp"]) if payload.get("rmtmp") else None
            )
            self._attr_target_temperature = (
                float(payload["actmp"]) if payload.get("actmp") else None
            )

            is_power_on = payload.get("ps") == "on"
            self._attr_hvac_mode = (
                HVAC_MODE_MAP.get(payload.get("acmd")) if is_power_on else HVACMode.OFF
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
            }

            _LOGGER.debug(
                "Updated state for %s: HVAC Mode - %s, Fan Mode - %s, Swing Mode - %s, Temperature - %s",
                self._attr_name,
                self._attr_hvac_mode,
                self._attr_fan_mode,
                self._attr_swing_mode,
                self._attr_target_temperature,
            )
            self.async_write_ha_state()
        except Exception as e:
            _LOGGER.error("Error handling state update for %s: %s", self._attr_name, e)

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
            try:
                await self._api.set_temperature(self._device_topic, temperature)
                await self.async_update()
            except Exception as e:
                _LOGGER.error(
                    "Error setting temperature for %s: %s", self._attr_name, e
                )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode.

        Args:
            hvac_mode: The new HVAC mode to set.

        Returns:
            None

        """
        _LOGGER.debug("Setting HVAC mode for %s to %s", self._attr_name, hvac_mode)
        try:
            if hvac_mode == HVACMode.OFF:
                await self._api.set_power(self._device_topic, "off")
            else:
                await self._api.set_power(self._device_topic, "on")
                miraie_mode = next(
                    (k for k, v in HVAC_MODE_MAP.items() if v == hvac_mode), None
                )
                if miraie_mode:
                    await self._api.set_mode(self._device_topic, miraie_mode)

            await self.async_update()
        except Exception as e:
            _LOGGER.error("Error setting HVAC mode for %s: %s", self._attr_name, e)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode.

        Args:
            fan_mode: The new fan mode to set.

        Returns:
            None

        """
        _LOGGER.debug("Setting fan mode for %s to %s", self._attr_name, fan_mode)
        try:
            miraie_fan_mode = next(
                (k for k, v in FAN_MODE_MAP.items() if v == fan_mode), None
            )
            if miraie_fan_mode:
                await self._api.set_fan_mode(self._device_topic, miraie_fan_mode)
            await self.async_update()
        except Exception as e:
            _LOGGER.error("Error setting fan mode for %s: %s", self._attr_name, e)

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set new target swing operation.

        Args:
            swing_mode: The new swing mode to set.

        Returns:
            None

        """
        _LOGGER.debug("Setting swing mode for %s to %s", self._attr_name, swing_mode)
        try:
            miraie_swing_mode = SWING_MODE_MAP.get(swing_mode)
            if miraie_swing_mode:
                await self._api.set_swing_mode(self._device_topic, miraie_swing_mode)
            await self.async_update()
        except Exception as e:
            _LOGGER.error("Error setting swing mode for %s: %s", self._attr_name, e)

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
