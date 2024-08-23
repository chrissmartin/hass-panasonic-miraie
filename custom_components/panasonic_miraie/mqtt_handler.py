import asyncio
import logging
import uuid
import json
from typing import Callable, Any
from homeassistant.core import HomeAssistant
from asyncio_mqtt import Client, MqttError
import ssl

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
        self._mqtt_task = None

    async def connect(self, username: str, password: str):
        """Connect to the MQTT broker."""
        self.username = username
        self.password = password

        _LOGGER.info(
            f"Initiating MQTT connection to {MIRAIE_BROKER_HOST}:{MIRAIE_BROKER_PORT}"
        )

        client_id = f"ha-panasonic-miraie-{uuid.uuid4().hex}"
        try:
            tls_context = None
            if MIRAIE_BROKER_USE_SSL:
                tls_context = ssl.create_default_context()

            self.client = Client(
                hostname=MIRAIE_BROKER_HOST,
                port=MIRAIE_BROKER_PORT,
                username=username,
                password=password,
                client_id=client_id,
                tls_context=tls_context,
            )

            await self.client.connect()
            self.connected.set()
            _LOGGER.info("Connected to Panasonic MirAIe MQTT broker")

            # Start the message loop
            self._mqtt_task = asyncio.create_task(self._message_loop())

        except MqttError as error:
            _LOGGER.error(f"Error connecting to MQTT broker: {error}")
            self.connected.clear()
            raise

    async def _message_loop(self):
        """Message loop to handle incoming messages."""
        try:
            async with self.client.messages() as messages:
                async for message in messages:
                    await self._handle_message(message)
        except MqttError as error:
            _LOGGER.error(f"MQTT Error in message loop: {error}")
            self.connected.clear()
            # Attempt to reconnect
            await self.connect_with_retry(self.username, self.password)
        except asyncio.CancelledError:
            _LOGGER.info("MQTT message loop cancelled")
        except Exception as e:
            _LOGGER.error(f"Unexpected error in MQTT message loop: {e}")

    async def _handle_message(self, message):
        """Handle incoming MQTT message."""
        _LOGGER.debug(f"Received message on topic {message.topic}")
        try:
            payload_dict = json.json_loads(message.payload.decode())
            if message.topic in self.subscriptions:
                callback = self.subscriptions[message.topic]
                await self.hass.async_add_job(callback, message.topic, payload_dict)
            else:
                _LOGGER.warning(
                    f"Received message on unsubscribed topic: {message.topic}"
                )
        except json.JSONDecodeError:
            _LOGGER.error(f"Failed to decode MQTT message: {message.payload}")
        except Exception as e:
            _LOGGER.error(f"Error handling MQTT message: {e}")

    async def connect_with_retry(self, username: str, password: str, max_retries=3):
        for attempt in range(max_retries):
            try:
                await self.connect(username, password)
                return True
            except Exception as e:
                _LOGGER.error(f"MQTT connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)  # Wait 5 seconds before retrying
        return False

    async def disconnect(self):
        """Disconnect from the MQTT broker."""
        _LOGGER.info("Initiating disconnect from MQTT broker")
        if self._mqtt_task:
            self._mqtt_task.cancel()
            try:
                await self._mqtt_task
            except asyncio.CancelledError:
                pass
        if self.client:
            await self.client.disconnect()
            self.client = None
        self.connected.clear()
        _LOGGER.info("Disconnected from Panasonic MirAIe MQTT broker")

    async def subscribe(self, topic: str, callback: Callable[[str, Any], None]):
        """Subscribe to an MQTT topic."""
        _LOGGER.debug(f"Attempting to subscribe to topic: {topic}")
        await self.connected.wait()
        self.subscriptions[topic] = callback
        await self.client.subscribe(topic)
        _LOGGER.debug(f"Successfully subscribed to topic: {topic}")

    async def unsubscribe(self, topic: str):
        """Unsubscribe from an MQTT topic."""
        _LOGGER.debug(f"Attempting to unsubscribe from topic: {topic}")
        await self.connected.wait()
        await self.client.unsubscribe(topic)
        self.subscriptions.pop(topic, None)
        _LOGGER.debug(f"Successfully unsubscribed from topic: {topic}")

    async def publish(self, topic: str, payload: dict):
        """Publish a message to a topic."""
        if not self.connected.is_set():
            _LOGGER.error("Cannot publish: MQTT client is not connected")
            return

        try:
            _LOGGER.debug(f"Attempting to publish to {topic}: {payload}")
            await self.client.publish(topic, json.dumps(payload))
            _LOGGER.debug(f"Successfully published to {topic}: {payload}")
        except Exception as e:
            _LOGGER.error(f"Error publishing to {topic}: {e}")

    def is_connected(self):
        """Check if the MQTT client is connected."""
        return self.connected.is_set()

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
