import asyncio
import logging
from homeassistant.util import json
from typing import Callable, Any
from homeassistant.core import HomeAssistant, callback
import paho.mqtt.client as mqtt

from .const import MIRAIE_BROKER_HOST, MIRAIE_BROKER_PORT, MIRAIE_BROKER_USE_SSL

_LOGGER = logging.getLogger(__name__)


class MQTTHandler:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.client = None
        self.connected = asyncio.Event()
        self.subscriptions = {}
        self.username = None
        self.password = None

    async def connect(self, username: str, password: str):
        """Connect to the MQTT broker."""
        self.username = username
        self.password = password

        _LOGGER.info(
            f"Initiating MQTT connection to {MIRAIE_BROKER_HOST}:{MIRAIE_BROKER_PORT}"
        )

        self.client = mqtt.Client("PBcMcfG19njNCL8AOgvRzIC8AjQa", protocol=mqtt.MQTTv5)
        self.client.username_pw_set(username, password)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        self.client.keepalive = 60

        if MIRAIE_BROKER_USE_SSL:
            _LOGGER.debug("Configuring TLS for MQTT connection")
            self.client.tls_set()

        try:
            async with asyncio.timeout(30):  # 30 seconds timeout
                _LOGGER.debug("Attempting to connect to MQTT broker")
                await self.hass.async_add_executor_job(
                    self.client.connect, MIRAIE_BROKER_HOST, MIRAIE_BROKER_PORT
                )
                self.client.loop_start()
                _LOGGER.debug("Waiting for MQTT connection to be established")
                await asyncio.wait_for(self.connected.wait(), timeout=30.0)
                _LOGGER.info("Connected to Panasonic MirAIe MQTT broker")
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout while connecting to MQTT broker")
            await self.disconnect()
            raise
        except Exception as error:
            _LOGGER.error(f"Error connecting to MQTT broker: {error}")
            await self.disconnect()
            raise

    async def disconnect(self):
        """Disconnect from the MQTT broker."""
        _LOGGER.info("Initiating disconnect from MQTT broker")
        if self.client:
            self.client.loop_stop()
            await self.hass.async_add_executor_job(self.client.disconnect)
            self.client = None
        self.connected.clear()
        _LOGGER.info("Disconnected from Panasonic MirAIe MQTT broker")

    async def subscribe(self, topic: str, callback: Callable[[str, Any], None]):
        """Subscribe to an MQTT topic."""
        _LOGGER.debug(f"Attempting to subscribe to topic: {topic}")
        await self.connected.wait()
        self.subscriptions[topic] = callback
        result, _ = await self.hass.async_add_executor_job(self.client.subscribe, topic)
        if result == mqtt.MQTT_ERR_SUCCESS:
            _LOGGER.debug(f"Successfully subscribed to topic: {topic}")
        else:
            _LOGGER.error(f"Failed to subscribe to topic: {topic}")

    async def unsubscribe(self, topic: str):
        """Unsubscribe from an MQTT topic."""
        _LOGGER.debug(f"Attempting to unsubscribe from topic: {topic}")
        await self.connected.wait()
        result, _ = await self.hass.async_add_executor_job(
            self.client.unsubscribe, topic
        )
        if result == mqtt.MQTT_ERR_SUCCESS:
            self.subscriptions.pop(topic, None)
            _LOGGER.debug(f"Successfully unsubscribed from topic: {topic}")
        else:
            _LOGGER.error(f"Failed to unsubscribe from topic: {topic}")

    async def publish(self, topic: str, payload: dict):
        """Publish a message to a topic."""
        if not self.is_connected():
            _LOGGER.error("Cannot publish: MQTT client is not connected")
            return

        try:
            _LOGGER.debug(f"Attempting to publish to {topic}: {payload}")
            message_info = await self.hass.async_add_executor_job(
                self.client.publish, topic, json.dumps(payload)
            )
            if message_info.is_published():
                _LOGGER.debug(f"Successfully published to {topic}: {payload}")
            else:
                _LOGGER.warning(f"Failed to publish to {topic}: {payload}")
        except Exception as e:
            _LOGGER.error(f"Error publishing to {topic}: {e}")

    @callback
    def _on_connect(self, client, userdata, flags, rc, properties=None):
        """Callback for when the client receives a CONNACK response from the server."""
        if rc == 0:
            self.hass.loop.call_soon_threadsafe(self.connected.set)
            _LOGGER.info("Successfully connected to MQTT broker")
            _LOGGER.debug(f"Connection flags: {flags}")
            if properties:
                _LOGGER.debug(f"Connection properties: {properties}")
        else:
            error_message = f"Connection failed with code {rc}: {self._rc_to_error(rc)}"
            _LOGGER.error(error_message)
            if properties:
                _LOGGER.debug(f"Failed connection properties: {properties}")

    @callback
    def _on_disconnect(self, client, userdata, rc, properties=None):
        """Callback for when the client disconnects from the server."""
        self.hass.loop.call_soon_threadsafe(self.connected.clear)
        if rc != 0:
            _LOGGER.warning(
                f"Unexpected disconnection. RC: {rc}. {self._rc_to_error(rc)}"
            )
            if properties:
                _LOGGER.debug(f"Disconnection properties: {properties}")
        else:
            _LOGGER.info("Disconnected from MQTT broker (expected)")

    @callback
    def _on_message(self, client, userdata, message):
        """Callback for when a PUBLISH message is received from the server."""
        _LOGGER.debug(f"Received message on topic {message.topic}")
        try:
            payload_dict = json.json_loads(message.payload.decode())
            if message.topic in self.subscriptions:
                callback = self.subscriptions[message.topic]
                self.hass.async_create_task(callback(message.topic, payload_dict))
            else:
                _LOGGER.warning(
                    f"Received message on unsubscribed topic: {message.topic}"
                )
        except json.JSONDecodeError:
            _LOGGER.error(f"Failed to decode MQTT message: {message.payload}")
        except Exception as e:
            _LOGGER.error(f"Error handling MQTT message: {e}")

    def is_connected(self):
        """Check if the MQTT client is connected."""
        is_connected = (
            self.client and self.client.is_connected() and self.connected.is_set()
        )
        _LOGGER.debug(
            f"MQTT connection status: {'Connected' if is_connected else 'Disconnected'}"
        )
        return is_connected

    async def wait_for_connection(self, timeout=10):
        """Wait for the MQTT connection to be established."""
        _LOGGER.debug(f"Waiting for MQTT connection (timeout: {timeout} seconds)")
        try:
            await asyncio.wait_for(self.connected.wait(), timeout=timeout)
            _LOGGER.info("MQTT connection established")
        except asyncio.TimeoutError:
            _LOGGER.error(
                f"Timeout waiting for MQTT connection after {timeout} seconds"
            )
            raise

    @staticmethod
    def _rc_to_error(rc: int) -> str:
        """Convert RC code to human-readable error message."""
        rc_messages = {
            1: "Incorrect protocol version",
            2: "Invalid client identifier",
            3: "Server unavailable",
            4: "Bad username or password",
            5: "Not authorized",
            7: "Network error",
        }
        return rc_messages.get(rc, "Unknown error")
