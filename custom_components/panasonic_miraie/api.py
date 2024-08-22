import logging
import random
import async_timeout
from typing import Any, Dict
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    MIRAIE_AUTH_API_BASE_URL,
    MIRAIE_APP_API_BASE_URL,
    LOGIN_RETRY_DELAY,
    LOGIN_TOKEN_REFRESH_INTERVAL,
)
from .mqtt_handler import MQTTHandler

_LOGGER = logging.getLogger(__name__)


class PanasonicMirAIeAPI:
    def __init__(self, hass: HomeAssistant, user_id: str, password: str):
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

    async def login(self):
        """Login to the MirAIe API."""
        if self.access_token:
            _LOGGER.debug("Already logged in, skipping login process")
            return True

        login_url = f"{MIRAIE_AUTH_API_BASE_URL}/userManagement/login"
        _LOGGER.debug(f"Attempting to login to {login_url}")

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
            async with async_timeout.timeout(10):
                async with self.http_session.post(login_url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.access_token = data.get("accessToken")
                        _LOGGER.info("Login successful")
                        _LOGGER.debug(f"Login response: {data}")
                        return True
                    else:
                        _LOGGER.error(
                            f"Login failed with status code: {response.status}"
                        )
                        return False
        except Exception as e:
            _LOGGER.error(f"Unexpected error during login: {e}")
            return False

    async def fetch_home_details(self):
        """Fetch the home details registered with the user's MirAIe platform account."""
        if not self.access_token:
            _LOGGER.error("No access token available. Please login first.")
            return False

        homes_url = f"{MIRAIE_APP_API_BASE_URL}/homeManagement/homes"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        _LOGGER.debug(f"Home details API: {homes_url} , headers: {headers}")

        try:
            async with self.http_session.get(homes_url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    _LOGGER.debug(f"Home details response: {data}")
                    if data:
                        self.home_id = data[0].get("homeId")
                        _LOGGER.debug(f"Home ID: {self.home_id}")
                        return True
                    else:
                        _LOGGER.error("No home details found")
                        return False
                else:
                    _LOGGER.error(
                        f"Failed to fetch home details. Status code: {response.status}"
                    )
                    return False
        except Exception as e:
            _LOGGER.error(f"Error fetching home details: {e}")
            return False

    async def connect_mqtt(self):
        if not self.home_id or not self.access_token:
            _LOGGER.error(
                "Home ID or access token not available. Cannot connect to MQTT."
            )
            return False

        try:
            _LOGGER.debug(
                f"[connect_mqtt] home_id: {self.home_id} , access_token: {self.access_token}"
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
            _LOGGER.error(f"Failed to connect to MQTT broker: {e}")
            return False

    async def logout(self):
        """Logout and disconnect MQTT."""
        await self.mqtt_handler.disconnect()
        self.access_token = None
        self.home_id = None

    async def get_devices(self):
        """Fetch all devices associated with the user's account."""
        if not self.access_token:
            if not await self.login():
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
                    _LOGGER.debug(f"Retrieved {len(devices)} devices")
                    return devices
                else:
                    _LOGGER.error(
                        f"Failed to fetch devices. Status code: {response.status}"
                    )
                    return []
        except Exception as e:
            _LOGGER.error(f"Error fetching devices: {e}")
            return []

    async def get_device_state(self, device_id: str) -> Dict[str, Any]:
        """Fetch the current state of a device."""
        if not self.access_token:
            if not await self.login():
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
                    _LOGGER.debug(f"Received device state for {device_id}: {data}")
                    return self._parse_device_state(data)
                elif response.status == 401:
                    _LOGGER.warning("Access token expired, attempting to login again")
                    if await self.login():
                        return await self.get_device_state(device_id)
                    else:
                        raise HomeAssistantError("Failed to refresh access token")
                else:
                    _LOGGER.error(
                        f"Failed to fetch device state. Status code: {response.status}"
                    )
                    raise HomeAssistantError(
                        f"Failed to fetch device state. Status code: {response.status}"
                    )
        except Exception as e:
            _LOGGER.error(f"Error fetching device state: {e}")
            raise HomeAssistantError(f"Error fetching device state: {e}")

    def _parse_device_state(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse the raw device state into a format matching MQTT updates."""
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
        _LOGGER.debug(f"Parsed device state: {parsed_state}")
        return parsed_state

    async def set_power(self, device_topic: str, state: str):
        """Set the power state of a device."""
        await self.mqtt_handler.publish(f"{device_topic}/control", {"ps": state})

    async def set_mode(self, device_topic: str, mode: str):
        """Set the operation mode of a device."""
        await self.mqtt_handler.publish(f"{device_topic}/control", {"acmd": mode})

    async def set_temperature(self, device_topic: str, temperature: float):
        """Set the target temperature of a device."""
        await self.mqtt_handler.publish(
            f"{device_topic}/control", {"actmp": str(temperature)}
        )

    async def set_fan_mode(self, device_topic: str, fan_mode: str):
        """Set the fan mode of a device."""
        await self.mqtt_handler.publish(f"{device_topic}/control", {"acfs": fan_mode})

    async def set_swing_mode(self, device_topic: str, swing_mode: str):
        """Set the swing mode of a device."""
        await self.mqtt_handler.publish(f"{device_topic}/control", {"acvs": swing_mode})

    def _get_scope(self):
        if "miraie_scope_id" not in self.hass.data:
            self.hass.data["miraie_scope_id"] = random.randint(0, 999999999)
        return f"an_{self.hass.data['miraie_scope_id']}"
