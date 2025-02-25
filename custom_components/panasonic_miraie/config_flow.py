"""Config flow for Panasonic MirAIe integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .api import PanasonicMirAIeAPI
from .const import CONF_PASSWORD, CONF_USER_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Panasonic MirAIe."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                # Set unique ID first, then check if already configured
                await self.async_set_unique_id(user_input[CONF_USER_ID])

                # This will raise AbortFlow if already configured - we handle it in the except block
                self._abort_if_unique_id_configured()

                # Validate input and create entry on success
                info = await validate_input(self.hass, user_input)
                return self.async_create_entry(title=info["title"], data=user_input)

            except config_entries.data_entry_flow.AbortFlow as abort_exc:
                # Handle the abort flow case properly
                _LOGGER.debug("Configuration already exists for this account")
                return self.async_abort(reason=abort_exc.reason)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception as e:
                _LOGGER.exception("Unexpected exception: %s", e)
                errors["base"] = "unknown"

        # Schema and form display
        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_USER_ID, description="User ID (Email or Mobile)"
                ): str,
                vol.Required(CONF_PASSWORD, description="Password"): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate user input, testing credentials and connectivity."""
    api = PanasonicMirAIeAPI(hass, data[CONF_USER_ID], data[CONF_PASSWORD])

    # Authentication and connection check
    if not await api.login():
        raise InvalidAuth

    try:
        # Check if API call to fetch home details is successful
        homes = await api.fetch_home_details()
        if not homes:
            raise CannotConnect
    except Exception as err:
        _LOGGER.error("Error fetching home details: %s", err)
        raise CannotConnect from err

    # Successful validation, ready to create entry
    return {"title": f"Panasonic MirAIe ({data[CONF_USER_ID]})"}


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate invalid authentication."""
