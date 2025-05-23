"""Services for Panasonic MirAIe integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, entity_registry as er

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_NANOE = "set_nanoe"
SERVICE_SET_POWERFUL_MODE = "set_powerful_mode"
SERVICE_SET_ECONOMY_MODE = "set_economy_mode"

# Common validation schema for all services with entity_id and state
SERVICE_BASE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("state"): cv.boolean,
    }
)

SERVICE_SCHEMAS = {
    SERVICE_SET_NANOE: SERVICE_BASE_SCHEMA,
    SERVICE_SET_POWERFUL_MODE: SERVICE_BASE_SCHEMA,
    SERVICE_SET_ECONOMY_MODE: SERVICE_BASE_SCHEMA,
}


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up Panasonic MirAIe services."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_NANOE):
        return

    async def async_handle_set_nanoe(service_call: ServiceCall) -> None:
        """Handle set nanoe service call."""
        await _async_set_special_mode(hass, service_call, "set_nanoe")

    async def async_handle_set_powerful_mode(service_call: ServiceCall) -> None:
        """Handle set powerful mode service call."""
        await _async_set_special_mode(hass, service_call, "set_powerful_mode")

    async def async_handle_set_economy_mode(service_call: ServiceCall) -> None:
        """Handle set economy mode service call."""
        await _async_set_special_mode(hass, service_call, "set_economy_mode")

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_NANOE,
        async_handle_set_nanoe,
        schema=SERVICE_SCHEMAS[SERVICE_SET_NANOE],
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_POWERFUL_MODE,
        async_handle_set_powerful_mode,
        schema=SERVICE_SCHEMAS[SERVICE_SET_POWERFUL_MODE],
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_ECONOMY_MODE,
        async_handle_set_economy_mode,
        schema=SERVICE_SCHEMAS[SERVICE_SET_ECONOMY_MODE],
    )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload Panasonic MirAIe services."""
    if not hass.services.has_service(DOMAIN, SERVICE_SET_NANOE):
        return

    hass.services.async_remove(DOMAIN, SERVICE_SET_NANOE)
    hass.services.async_remove(DOMAIN, SERVICE_SET_POWERFUL_MODE)
    hass.services.async_remove(DOMAIN, SERVICE_SET_ECONOMY_MODE)


async def _async_set_special_mode(
    hass: HomeAssistant, service_call: ServiceCall, api_method: str
) -> None:
    """Handle special mode service call."""
    entity_id = service_call.data["entity_id"]
    state = service_call.data["state"]

    # Find the entity registry entry
    entity_registry = er.async_get(hass)
    registry_entry = entity_registry.async_get(entity_id)

    if registry_entry is None or registry_entry.platform != DOMAIN:
        _LOGGER.error(
            "Failed to call %s service: Entity %s not found or not a Panasonic MirAIe entity",
            api_method,
            entity_id,
        )
        return

    # Get the device entry from the registry
    device_id = registry_entry.device_id
    if device_id is None:
        _LOGGER.error(
            "Failed to call %s service: Entity %s is not associated with a device",
            api_method,
            entity_id,
        )
        return

    # Get all config entries for this domain
    for _, api in hass.data[DOMAIN].items():
        # Find the device in this entry's devices
        device = None
        for dev in api.devices:
            if dev.get("id") == device_id or dev.get("uniqueId") == device_id:
                device = dev
                break

        if device:
            # Call the appropriate API method
            topic = device.get("topic")
            if not topic:
                _LOGGER.error(
                    "Failed to call %s service: Device %s has no topic",
                    api_method,
                    device_id,
                )
                return

            api_func = getattr(api, api_method)
            await api_func(topic, state)
            _LOGGER.debug(
                "Successfully called %s with state %s for device %s",
                api_method,
                state,
                device_id,
            )
            return

    _LOGGER.error(
        "Failed to call %s service: Device %s not found in any config entry",
        api_method,
        device_id,
    )
