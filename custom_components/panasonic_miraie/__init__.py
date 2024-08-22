"""The Panasonic MirAI.e integration."""

from __future__ import annotations

import logging
import random
import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.const import CONF_PASSWORD
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, CONF_USER_ID
from .api import PanasonicMirAIeAPI

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["climate"]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Panasonic MirAI.e component."""
    hass.data.setdefault(DOMAIN, {})
    hass.data["miraie_scope_id"] = random.randint(0, 999999999)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Panasonic MirAI.e from a config entry."""
    user_id = entry.data[CONF_USER_ID]
    password = entry.data[CONF_PASSWORD]

    api = PanasonicMirAIeAPI(hass, user_id, password)

    try:
        # Set a timeout for the login and MQTT connection process
        async with asyncio.timeout(30):  # 30 seconds timeout
            if not await api.login():
                raise ConfigEntryNotReady("Failed to login to Panasonic MirAI.e API")

            # Ensure MQTT connection is established
            if not await api.mqtt_handler.wait_for_connection(timeout=10):
                raise ConfigEntryNotReady("Failed to establish MQTT connection")

    except asyncio.TimeoutError:
        _LOGGER.error("Timeout while setting up Panasonic MirAI.e integration")
        raise ConfigEntryNotReady("Setup timed out")
    except Exception as ex:
        _LOGGER.error("Error setting up Panasonic MirAI.e integration: %s", str(ex))
        raise ConfigEntryNotReady from ex

    hass.data[DOMAIN][entry.entry_id] = api

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        api = hass.data[DOMAIN].pop(entry.entry_id)
        await api.mqtt_handler.disconnect()

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
