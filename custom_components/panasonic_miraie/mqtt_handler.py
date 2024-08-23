"""MQTT Handler for Panasonic MirAIe integration with Home Assistant.

Provides an MQTT client implementation for communication with Panasonic MirAIe
devices. Handles connection management, message processing, subscriptions,
and publishing within the Home Assistant ecosystem.

"""

import asyncio
from collections.abc import Callable
import contextlib
import json
import logging
import ssl
from typing import Any
import uuid

from asyncio_mqtt import Client, MqttError

from homeassistant.core import HomeAssistant

from .const import MIRAIE_BROKER_HOST, MIRAIE_BROKER_PORT, MIRAIE_BROKER_USE_SSL

_LOGGER = logging.getLogger(__name__)


class MQTTHandler:
    """Handler for MQTT communication with Panasonic MirAIe devices."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the MQTT Handler.

        Args:
            hass: The Home Assistant instance.

        """
        self.hass = hass
        self.client = None
        self.connected = asyncio.Event()
        self.subscriptions = {}
        self.username = None
        self.password = None
        self._mqtt_task = None

    async def connect(self, username: str, password: str):
        """Connect to the MQTT broker.

        Args:
            username: The username for MQTT authentication.
            password: The password for MQTT authentication.

        Raises:
            MqttError: If there's an error connecting to the MQTT broker.

        """
        self.username = username
        self.password = password

        _LOGGER.info(
            "Initiating MQTT connection to %s:%s",
            MIRAIE_BROKER_HOST,
            MIRAIE_BROKER_PORT,
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
            _LOGGER.error("Error connecting to MQTT broker: %s", error)
            self.connected.clear()
            raise

    async def _message_loop(self):
        """Handle the message loop for incoming MQTT messages."""
        try:
            async with self.client.messages() as messages:
                async for message in messages:
                    await self._handle_message(message)
        except MqttError as error:
            _LOGGER.error("MQTT Error in message loop: %s", error)
            self.connected.clear()
            # Attempt to reconnect
            await self.connect_with_retry(self.username, self.password)
        except asyncio.CancelledError:
            _LOGGER.info("MQTT message loop cancelled")
        except Exception as e:
            _LOGGER.error("Unexpected error in MQTT message loop: %s", e)

    async def _handle_message(self, message):
        """Handle incoming MQTT message.

        Args:
            message: The incoming MQTT message.

        """
        _LOGGER.debug("Received message on topic %s", message.topic)
        try:
            payload_dict = json.loads(message.payload.decode())
            if message.topic in self.subscriptions:
                callback = self.subscriptions[message.topic]
                await self.hass.async_add_job(callback, message.topic, payload_dict)
            else:
                _LOGGER.warning(
                    "Received message on unsubscribed topic: %s", message.topic
                )
        except json.JSONDecodeError:
            _LOGGER.error("Failed to decode MQTT message: %s", message.payload)
        except Exception as e:
            _LOGGER.error("Error handling MQTT message: %s", e)

    async def connect_with_retry(self, username: str, password: str, max_retries=3):
        """Attempt to connect to the MQTT broker with retries.

        Args:
            username: The username for MQTT authentication.
            password: The password for MQTT authentication.
            max_retries: The maximum number of connection attempts.

        Returns:
            bool: True if connection was successful, False otherwise.

        """
        for attempt in range(max_retries):
            try:
                await self.connect(username, password)
                return True
            except Exception as e:
                _LOGGER.error("MQTT connection attempt %d failed: %s", attempt + 1, e)
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)  # Wait 5 seconds before retrying
        return False

    async def disconnect(self):
        """Disconnect from the MQTT broker."""
        _LOGGER.info("Initiating disconnect from MQTT broker")
        if self._mqtt_task:
            self._mqtt_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._mqtt_task
        if self.client:
            await self.client.disconnect()
            self.client = None
        self.connected.clear()
        _LOGGER.info("Disconnected from Panasonic MirAIe MQTT broker")

    async def subscribe(self, topic: str, callback: Callable[[str, Any], None]):
        """Subscribe to an MQTT topic.

        Args:
            topic: The MQTT topic to subscribe to.
            callback: The callback function to handle received messages.

        """
        _LOGGER.debug("Attempting to subscribe to topic: %s", topic)
        await self.connected.wait()
        self.subscriptions[topic] = callback
        await self.client.subscribe(topic)
        _LOGGER.debug("Successfully subscribed to topic: %s", topic)

    async def unsubscribe(self, topic: str):
        """Unsubscribe from an MQTT topic.

        Args:
            topic: The MQTT topic to unsubscribe from.

        """
        _LOGGER.debug("Attempting to unsubscribe from topic: %s", topic)
        await self.connected.wait()
        await self.client.unsubscribe(topic)
        self.subscriptions.pop(topic, None)
        _LOGGER.debug("Successfully unsubscribed from topic: %s", topic)

    async def publish(self, topic: str, payload: dict):
        """Publish a message to a topic.

        Args:
            topic: The MQTT topic to publish to.
            payload: The message payload to publish.

        """
        if not self.connected.is_set():
            _LOGGER.error("Cannot publish: MQTT client is not connected")
            return

        try:
            _LOGGER.debug("Attempting to publish to %s: %s", topic, payload)
            await self.client.publish(topic, json.dumps(payload))
            _LOGGER.debug("Successfully published to %s: %s", topic, payload)
        except Exception as e:
            _LOGGER.error("Error publishing to %s: %s", topic, e)

    def is_connected(self):
        """Check if the MQTT client is connected.

        Returns:
            bool: True if connected, False otherwise.

        """
        return self.connected.is_set()

    async def wait_for_connection(self, timeout=10):
        """Wait for the MQTT connection to be established.

        Args:
            timeout: The maximum time to wait for the connection in seconds.

        Raises:
            TimeoutError: If the connection is not established within the timeout period.

        """
        _LOGGER.debug("Waiting for MQTT connection (timeout: %d seconds)", timeout)
        try:
            await asyncio.wait_for(self.connected.wait(), timeout=timeout)
            _LOGGER.info("MQTT connection established")
        except TimeoutError:
            _LOGGER.error(
                "Timeout waiting for MQTT connection after %d seconds", timeout
            )
            raise
