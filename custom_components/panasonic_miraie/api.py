"""API client for Panasonic MirAIe devices integration with Home Assistant."""

from asyncio import timeout
import logging
import random
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    MIRAIE_APP_API_BASE_URL,
    MIRAIE_AUTH_API_BASE_URL,
)
from .mqtt_handler import MQTTHandler

_LOGGER = logging.getLogger(__name__)


class PanasonicMirAIeAPI:
    """API client for interacting with Panasonic MirAIe devices."""

    def __init__(self, hass: HomeAssistant, user_id: str, password: str):
        """Initialize the PanasonicMirAIeAPI.

        Args:
            hass: The Home Assistant instance.
            user_id: The user ID (email or mobile) for the MirAIe account.
            password: The password for the MirAIe account.

        """
        self.hass = hass
        self.user_id = user_id
        self.password = password
        self.access_token = None
        self.home_id = None
        self.http_session = async_get_clientsession(hass)
        self.mqtt_handler = MQTTHandler(hass)

    async def initialize(self):
        """Initialize the API by logging in, fetching home details, and connecting to MQTT."""
        if not await self.login():
            raise HomeAssistantError("Failed to login to Panasonic MirAI.e API")

        if not await self.fetch_home_details():
            raise HomeAssistantError("Failed to fetch home details")

        if not await self.connect_mqtt():
            raise HomeAssistantError("Failed to connect to MQTT broker")

    def _get_scope(self):
        """Get a unique scope ID for the API requests.

        Returns:
            str: A unique scope ID.

        """
        if "miraie_scope_id" not in self.hass.data:
            self.hass.data["miraie_scope_id"] = random.randint(0, 999999999)
        return f"an_{self.hass.data['miraie_scope_id']}"

    async def login(self):
        """Login to the MirAIe API.

        Returns:
            bool: True if login was successful, False otherwise.

        """
        if self.access_token:
            _LOGGER.debug("Already logged in, skipping login process")
            return True

        login_url = f"{MIRAIE_AUTH_API_BASE_URL}/userManagement/login"
        _LOGGER.debug("Attempting to login to %s", login_url)

        payload = {
            "clientId": "PBcMcfG19njNCL8AOgvRzIC8AjQa",
            "password": self.password,
            "scope": self._get_scope(),
        }

        if "@" in self.user_id:
            payload["email"] = self.user_id
        else:
            payload["mobile"] = self.user_id

        try:
            async with (
                timeout(10),
                self.http_session.post(login_url, json=payload) as response,
            ):
                if response.status == 200:
                    data = await response.json()
                    self.access_token = data.get("accessToken")
                    _LOGGER.info("Login successful")
                    _LOGGER.debug("Login response: %s", data)
                    return True
                else:
                    _LOGGER.error("Login failed with status code: %d", response.status)
                    return False
        except Exception as e:
            _LOGGER.error("Unexpected error during login: %s", e)
            return False

    async def fetch_home_details(self):
        """Fetch the home details registered with the user's MirAIe platform account.

        Returns:
            bool: True if home details were successfully fetched, False otherwise.

        """
        if not self.access_token:
            _LOGGER.error("No access token available. Please login first.")
            return False

        homes_url = f"{MIRAIE_APP_API_BASE_URL}/homeManagement/homes"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        _LOGGER.debug("Home details API: %s , headers: %s", homes_url, headers)

        try:
            async with self.http_session.get(homes_url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    _LOGGER.debug("Home details response: %s", data)
                    if data:
                        self.home_id = data[0].get("homeId")
                        _LOGGER.debug("Home ID: %s", self.home_id)
                        return True
                    else:
                        _LOGGER.error("No home details found")
                        return False
                else:
                    _LOGGER.error(
                        "Failed to fetch home details. Status code: %d", response.status
                    )
                    return False
        except Exception as e:
            _LOGGER.error("Error fetching home details: %s", e)
            return False

    async def connect_mqtt(self):
        """Connect to the MQTT broker.

        Returns:
            bool: True if successfully connected to MQTT broker, False otherwise.

        """
        if not self.home_id or not self.access_token:
            _LOGGER.error(
                "Home ID or access token not available. Cannot connect to MQTT."
            )
            return False

        try:
            _LOGGER.debug(
                "connect_mqtt home_id: %s , access_token: %s",
                self.home_id,
                self.access_token,
            )
            connected = await self.mqtt_handler.connect_with_retry(
                self.home_id, self.access_token
            )
            if connected:
                _LOGGER.info("Successfully connected to MQTT broker")
                return True
            else:
                _LOGGER.error(
                    "Failed to connect to MQTT broker after multiple attempts"
                )
                return False
        except Exception as e:
            _LOGGER.error("Failed to connect to MQTT broker: %s", e)
            return False

    async def logout(self):
        """Logout and disconnect MQTT."""
        await self.mqtt_handler.disconnect()
        self.access_token = None
        self.home_id = None

    async def get_devices(self):
        """Fetch all devices associated with the user's account.

        Returns:
            list: A list of dictionaries containing device information.

        """
        if not self.access_token and not await self.login():
            return []

        homes_url = f"{MIRAIE_APP_API_BASE_URL}/homeManagement/homes"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        try:
            async with self.http_session.get(homes_url, headers=headers) as response:
                if response.status == 200:
                    homes = await response.json()
                    devices = []
                    for home in homes:
                        for space in home.get("spaces", []):
                            for device in space.get("devices", []):
                                devices.append(
                                    {
                                        "deviceId": device.get("deviceId"),
                                        "deviceName": device.get("deviceName"),
                                        "topic": device.get("topic", []),
                                        "homeId": home.get("homeId"),
                                        "homeName": home.get("homeName"),
                                        "spaceId": space.get("spaceId"),
                                        "spaceName": space.get("spaceName"),
                                        "spaceType": space.get("spaceType"),
                                    }
                                )
                    _LOGGER.debug("Retrieved %d devices", len(devices))
                    return devices
                else:
                    _LOGGER.error(
                        "Failed to fetch devices. Status code: %d", response.status
                    )
                    return []
        except Exception as e:
            _LOGGER.error("Error fetching devices: %s", e)
            return []

    async def get_device_state(self, device_id: str) -> dict[str, Any]:
        """Fetch the current state of a device.

        Args:
            device_id: The ID of the device to fetch the state for.

        Returns:
            dict: A dictionary containing the device state.

        Raises:
            HomeAssistantError: If there's an error fetching the device state.

        """
        if not self.access_token and not await self.login():
            raise HomeAssistantError("Failed to login to Panasonic MirAI.e API")

        url = f"{MIRAIE_APP_API_BASE_URL}/deviceManagement/devices/{device_id}/mobile/status"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        try:
            async with self.http_session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    _LOGGER.debug("Received device state for %s: %s", device_id, data)
                    return self._parse_device_state(data)
                elif response.status == 401:
                    _LOGGER.warning("Access token expired, attempting to login again")
                    if await self.login():
                        return await self.get_device_state(device_id)
                    else:
                        raise HomeAssistantError("Failed to refresh access token")
                else:
                    _LOGGER.error(
                        "Failed to fetch device state. Status code: %d", response.status
                    )
                    raise HomeAssistantError(
                        f"Failed to fetch device state. Status code: {response.status}"
                    )
        except Exception as e:
            _LOGGER.error("Error fetching device state: %s", e)
            raise HomeAssistantError(f"Error fetching device state: {e}")

    def _parse_device_state(self, data: dict[str, Any]) -> dict[str, Any]:
        """Parse the raw device state into a format matching MQTT updates.

        Args:
            data: The raw device state data.

        Returns:
            dict: A dictionary containing the parsed device state.

        """
        parsed_state = {
            "onlineStatus": data.get("onlineStatus"),
            "rmtmp": data.get("rmtmp"),
            "actmp": data.get("actmp"),
            "acmd": data.get("acmd"),
            "acfs": data.get("acfs"),
            "acvs": data.get("acvs"),
            "achs": data.get("achs"),
            "ps": data.get("ps"),
            "acng": data.get("acng"),
            "acpm": data.get("acpm"),
            "acec": data.get("acec"),
            "ts": data.get("ts"),
            "errors": data.get("errors"),
            "warnings": data.get("warnings"),
            "filterDustLevel": data.get("filterDustLevel"),
            "filterCleaningRequired": data.get("filterCleaningRequired"),
        }
        _LOGGER.debug("Parsed device state: %s", parsed_state)
        return parsed_state

    async def set_power(self, device_topic: str, state: str):
        """Set the power state of a device.

        Args:
            device_topic: The MQTT topic for the device.
            state: The desired power state ("ON" or "OFF").

        """
        payload = self._get_base_payload()
        payload.update({"ps": state})
        await self.mqtt_handler.publish(f"{device_topic}/control", payload)

    async def set_mode(self, device_topic: str, mode: str):
        """Set the operation mode of a device.

        Args:
            device_topic: The MQTT topic for the device.
            mode: The desired operation mode.

        """
        payload = self._get_base_payload()
        payload.update({"acmd": mode})
        await self.mqtt_handler.publish(f"{device_topic}/control", payload)

    async def set_temperature(self, device_topic: str, temperature: float):
        """Set the target temperature of a device.

        Args:
            device_topic: The MQTT topic for the device.
            temperature: The desired target temperature.

        """
        payload = self._get_base_payload()
        payload.update({"actmp": str(temperature)})
        await self.mqtt_handler.publish(f"{device_topic}/control", payload)

    async def set_fan_mode(self, device_topic: str, fan_mode: str):
        """Set the fan mode of a device.

        Args:
            device_topic: The MQTT topic for the device.
            fan_mode: The desired fan mode.

        """
        payload = self._get_base_payload()
        payload.update({"acfs": fan_mode})
        await self.mqtt_handler.publish(f"{device_topic}/control", payload)

    async def set_swing_mode(self, device_topic: str, swing_mode: str):
        """Set the swing mode of a device.

        Args:
            device_topic: The MQTT topic for the device.
            swing_mode: The desired swing mode.

        """
        payload = self._get_base_payload()
        payload.update({"acvs": swing_mode})
        await self.mqtt_handler.publish(f"{device_topic}/control", payload)

    def _get_base_payload(self):
        """Get the base payload for MQTT messages.

        Returns:
            dict: A dictionary containing the base payload for MQTT messages.

        """
        return {"ki": 1, "cnt": "an", "sid": "1"}
