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
SERVICE_SET_CLEAN_MODE = "set_clean_mode"
SERVICE_SET_CONVERTI7_MODE = "set_converti7_mode"

# Common validation schema for all services with state parameter
SERVICE_BASE_SCHEMA = vol.Schema(
    {
        vol.Required("state"): cv.boolean,
    }
)

# Schema for converti7 mode service with mode_value parameter
SERVICE_CONVERTI7_SCHEMA = vol.Schema(
    {
        vol.Required("mode_value"): cv.string,
    }
)

SERVICE_SCHEMAS = {
    SERVICE_SET_NANOE: SERVICE_BASE_SCHEMA,
    SERVICE_SET_POWERFUL_MODE: SERVICE_BASE_SCHEMA,
    SERVICE_SET_ECONOMY_MODE: SERVICE_BASE_SCHEMA,
    SERVICE_SET_CLEAN_MODE: SERVICE_BASE_SCHEMA,
    SERVICE_SET_CONVERTI7_MODE: SERVICE_CONVERTI7_SCHEMA,
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

    async def async_handle_set_clean_mode(service_call: ServiceCall) -> None:
        """Handle set clean mode service call."""
        await _async_set_special_mode(hass, service_call, "set_clean_mode")

    async def async_handle_set_converti7_mode(service_call: ServiceCall) -> None:
        """Handle set converti7 mode service call."""
        await _async_set_special_mode(
            hass, service_call, "set_converti7_mode", "mode_value"
        )

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

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CLEAN_MODE,
        async_handle_set_clean_mode,
        schema=SERVICE_SCHEMAS[SERVICE_SET_CLEAN_MODE],
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CONVERTI7_MODE,
        async_handle_set_converti7_mode,
        schema=SERVICE_SCHEMAS[SERVICE_SET_CONVERTI7_MODE],
    )


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload Panasonic MirAIe services."""
    if not hass.services.has_service(DOMAIN, SERVICE_SET_NANOE):
        return

    hass.services.async_remove(DOMAIN, SERVICE_SET_NANOE)
    hass.services.async_remove(DOMAIN, SERVICE_SET_POWERFUL_MODE)
    hass.services.async_remove(DOMAIN, SERVICE_SET_ECONOMY_MODE)
    hass.services.async_remove(DOMAIN, SERVICE_SET_CLEAN_MODE)
    hass.services.async_remove(DOMAIN, SERVICE_SET_CONVERTI7_MODE)


async def _async_set_special_mode(  # noqa: C901
    hass: HomeAssistant,
    service_call: ServiceCall,
    api_method: str,
    param_name: str = "state",
) -> None:
    """Handle special mode service call."""
    param_value = service_call.data[param_name]
    target_entities = service_call.target.get("entity_id", [])

    if not target_entities:
        _LOGGER.error(
            "Failed to call %s service: No target entities specified",
            api_method,
        )
        return

    entity_registry = er.async_get(hass)

    # Process each target entity
    for entity_id in target_entities:
        # Find the entity registry entry
        registry_entry = entity_registry.async_get(entity_id)

        if registry_entry is None or registry_entry.platform != DOMAIN:
            _LOGGER.error(
                "Failed to call %s service: Entity %s not found or not a Panasonic MirAIe entity",
                api_method,
                entity_id,
            )
            continue

        # Get the device entry from the registry
        device_id = registry_entry.device_id
        if device_id is None:
            _LOGGER.error(
                "Failed to call %s service: Entity %s is not associated with a device",
                api_method,
                entity_id,
            )
            continue

        found_device = False
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
                    continue

                api_func = getattr(api, api_method)
                await api_func(topic, param_value)
                _LOGGER.debug(
                    "Successfully called %s with %s %s for device %s",
                    api_method,
                    param_name,
                    param_value,
                    device_id,
                )
                found_device = True
                break

        if not found_device:
            _LOGGER.error(
                "Failed to call %s service: Device %s not found in any config entry",
                api_method,
                device_id,
            )
