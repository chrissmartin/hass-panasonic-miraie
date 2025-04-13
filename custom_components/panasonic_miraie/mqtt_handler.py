"""MQTT Handler for Panasonic MirAIe integration with Home Assistant.

Provides an MQTT client implementation for communication with Panasonic MirAIe
devices. Handles connection management, message processing, subscriptions,
and publishing within the Home Assistant ecosystem.

"""

import asyncio
from collections.abc import Callable
import contextlib
from datetime import timedelta
import json
import logging
import ssl
import time
import uuid

from aiomqtt import Client, MqttError

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    MIRAIE_BROKER_HOST,
    MIRAIE_BROKER_PORT,
    MIRAIE_BROKER_USE_SSL,
    MQTT_CONNECTION_TIMEOUT,
    MQTT_KEEPALIVE,
    MQTT_PING_INTERVAL,
    MQTT_RECONNECT_INTERVAL,
)

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
        self._reconnect_task = None
        self._retry_count = 0
        self._max_retry_count = 10
        self._last_successful_connection = 0
        self._last_message_time = 0
        self._connection_monitor = None
        self._ping_task = None
        self._pending_reconnect = False
        self._client_id = f"ha-panasonic-miraie-{uuid.uuid4().hex}"

    async def connect(self, username: str, password: str) -> bool:  # noqa: C901
        """Connect to the MQTT broker.

        Args:
            username: The username for MQTT authentication.
            password: The password for MQTT authentication.

        Returns:
            bool: True if connection was successful, False otherwise.

        Raises:
            MqttError: If there's an error connecting to the MQTT broker.

        """
        if self._pending_reconnect:
            _LOGGER.debug("Connection attempt already in progress, skipping")
            return False

        self._pending_reconnect = True
        self.username = username
        self.password = password

        _LOGGER.info(
            "Initiating MQTT connection to %s:%s",
            MIRAIE_BROKER_HOST,
            MIRAIE_BROKER_PORT,
        )

        try:
            tls_context = None
            if MIRAIE_BROKER_USE_SSL:
                tls_context = await self.hass.async_add_executor_job(
                    ssl.create_default_context
                )

            # Cancel existing client if there is one
            if self.client:
                with contextlib.suppress(Exception):
                    await self.client.disconnect()
                self.client = None

            # Cancel existing ping task
            if self._ping_task:
                self._ping_task.cancel()
                with contextlib.suppress(Exception):
                    await self._ping_task
                self._ping_task = None

            self.client = Client(
                hostname=MIRAIE_BROKER_HOST,
                port=MIRAIE_BROKER_PORT,
                username=username,
                password=password,
                client_id=self._client_id,
                tls_context=tls_context,
                keepalive=MQTT_KEEPALIVE,
            )

            # Set a timeout for the connection
            try:
                async with asyncio.timeout(MQTT_CONNECTION_TIMEOUT):
                    await self.client.connect()
            except TimeoutError:
                _LOGGER.error("Timeout connecting to MQTT broker")
                self._pending_reconnect = False
                return False

            self.connected.set()
            current_time = time.time()
            self._last_successful_connection = current_time
            self._last_message_time = current_time
            self._retry_count = 0
            _LOGGER.info("Connected to Panasonic MirAIe MQTT broker")

            # Re-subscribe to topics if reconnecting
            if self.subscriptions:
                _LOGGER.debug("Resubscribing to %d topics", len(self.subscriptions))
                for topic in self.subscriptions:
                    await self.client.subscribe(topic)

            # Start the message loop
            if self._mqtt_task:
                self._mqtt_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._mqtt_task

            self._mqtt_task = asyncio.create_task(self._message_loop())

            # Start the ping task to keep connection alive
            self._ping_task = asyncio.create_task(self._keep_connection_alive())

            self._pending_reconnect = False

            # Start the connection monitor if not already running
            if not self._connection_monitor:
                self._connection_monitor = async_track_time_interval(
                    self.hass,
                    self._check_connection_status,
                    timedelta(seconds=MQTT_RECONNECT_INTERVAL),
                )

            return True

        except MqttError as error:
            _LOGGER.error("Error connecting to MQTT broker: %s", error)
            self.connected.clear()
            self._pending_reconnect = False
            raise
        except Exception as e:
            _LOGGER.error("Unexpected error connecting to MQTT broker: %s", e)
            self.connected.clear()
            self._pending_reconnect = False
            return False

    async def _keep_connection_alive(self) -> None:
        """Keep the MQTT connection alive by periodically checking the status."""
        try:
            while self.connected.is_set():
                await asyncio.sleep(MQTT_PING_INTERVAL)
                if not self.client or not self.connected.is_set():
                    break

                # check connection status and force a ping via the client's internal mechanism
                try:
                    # For asyncio-mqtt, we can force a ping by checking the connection status
                    is_connected = self.client._client.is_connected()
                    if is_connected:
                        # Just updating the timestamp since we had a successful connection check
                        self._last_message_time = time.time()
                        _LOGGER.debug("Connection check successful")
                    else:
                        _LOGGER.warning("Connection check failed, client disconnected")
                        self.connected.clear()
                        break
                except Exception as e:
                    _LOGGER.warning("Error checking connection status: %s", e)
                    # If we can't check status, assume disconnected
                    self.connected.clear()
                    break
        except asyncio.CancelledError:
            _LOGGER.debug("Connection monitoring loop cancelled")
        except Exception as e:
            _LOGGER.error("Unexpected error in connection monitoring: %s", e)
            # If monitoring fails, mark as disconnected so reconnect process starts
            self.connected.clear()

    async def _check_connection_status(self, *_) -> None:
        """Periodically check the connection status and reconnect if needed."""
        if not self.connected.is_set() and not self._pending_reconnect:
            _LOGGER.info("Connection monitor detected disconnected state, reconnecting")
            await self.connect_with_retry(self.username, self.password)
        elif self.connected.is_set():
            # Check if connection is stale (no message received for a while)
            connection_age = time.time() - self._last_message_time
            stale_threshold = MQTT_KEEPALIVE * 1.5

            if connection_age > stale_threshold:
                _LOGGER.warning(
                    "MQTT connection may be stale (no activity for %d seconds), reconnecting",
                    connection_age,
                )
                # Instead of just clearing the connected flag, handle graceful disconnection first
                await self._handle_graceful_reconnect()

    async def _handle_graceful_reconnect(self) -> None:
        """Handle a reconnection with proper cleanup."""
        # First mark as disconnected to prevent other operations
        self.connected.clear()

        # Try to gracefully disconnect existing client
        if self.client:
            with contextlib.suppress(Exception):
                await self.client.disconnect()
            self.client = None

        # Cancel existing message loop
        if self._mqtt_task:
            self._mqtt_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._mqtt_task
            self._mqtt_task = None

        # Cancel existing ping task
        if self._ping_task:
            self._ping_task.cancel()
            with contextlib.suppress(Exception):
                await self._ping_task
            self._ping_task = None

        # Now reconnect
        await self.connect_with_retry(self.username, self.password)

    async def _message_loop(self):
        """Handle the message loop for incoming MQTT messages."""
        try:
            async with self.client.messages() as messages:
                async for message in messages:
                    # Update last message time whenever we receive a message
                    self._last_message_time = time.time()
                    await self._handle_message(message)
        except MqttError as error:
            if self.connected.is_set():  # Only log if we thought we were connected
                _LOGGER.error("MQTT Error in message loop: %s", error)
                self.connected.clear()
                # Handle reconnection outside the exception handler
                self.hass.async_create_task(self._handle_message_loop_error())
        except asyncio.CancelledError:
            _LOGGER.debug("MQTT message loop cancelled")
        except Exception as e:
            if self.connected.is_set():  # Only log if we thought we were connected
                _LOGGER.error("Unexpected error in MQTT message loop: %s", e)
                self.connected.clear()
                # Handle reconnection outside the exception handler
                self.hass.async_create_task(self._handle_message_loop_error())

    async def _handle_message_loop_error(self) -> None:
        """Handle errors in the message loop with delayed reconnection."""
        # Wait a short time before reconnecting to avoid rapid reconnection loops
        await asyncio.sleep(1)
        if not self._pending_reconnect:
            await self.connect_with_retry(self.username, self.password)

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
                _LOGGER.debug(
                    "Received message on unsubscribed topic: %s", message.topic
                )
        except json.JSONDecodeError:
            _LOGGER.error("Failed to decode MQTT message: %s", message.payload)
        except Exception as e:
            _LOGGER.error("Error handling MQTT message: %s", e)

    async def connect_with_retry(self, username: str, password: str, max_retries=None):
        """Attempt to connect to the MQTT broker with retries.

        Args:
            username: The username for MQTT authentication.
            password: The password for MQTT authentication.
            max_retries: The maximum number of connection attempts.

        Returns:
            bool: True if connection was successful, False otherwise.

        """
        if max_retries is None:
            max_retries = self._max_retry_count

        if self._pending_reconnect:
            _LOGGER.debug("Reconnection already in progress, skipping")
            return False

        # Use exponential backoff for reconnection attempts
        for attempt in range(max_retries):
            if attempt > 0:
                # Calculate backoff time: 2^attempt with a max of 60 seconds
                backoff_time = min(2**attempt, 60)
                _LOGGER.info(
                    "Waiting %d seconds before reconnection attempt %d/%d",
                    backoff_time,
                    attempt + 1,
                    max_retries,
                )
                await asyncio.sleep(backoff_time)

            try:
                connected = await self.connect(username, password)
                if connected:
                    return True
            except Exception as e:
                _LOGGER.error("MQTT connection attempt %d failed: %s", attempt + 1, e)

        _LOGGER.error(
            "Failed to reconnect to MQTT broker after %d attempts", max_retries
        )
        return False

    async def disconnect(self):
        """Disconnect from the MQTT broker."""
        _LOGGER.info("Initiating disconnect from MQTT broker")

        # Cancel connection monitor
        if self._connection_monitor:
            self._connection_monitor()
            self._connection_monitor = None

        # Cancel message loop task
        if self._mqtt_task:
            self._mqtt_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._mqtt_task
            self._mqtt_task = None

        # Cancel ping task
        if self._ping_task:
            self._ping_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ping_task
            self._ping_task = None

        # Disconnect from broker
        if self.client:
            try:
                await self.client.disconnect()
            except Exception as e:
                _LOGGER.debug("Error during MQTT disconnect: %s", e)
            self.client = None

        self.connected.clear()
        _LOGGER.info("Disconnected from Panasonic MirAIe MQTT broker")

    async def subscribe(self, topic: str, callback: Callable[[str, any], None]):
        """Subscribe to an MQTT topic.

        Args:
            topic: The MQTT topic to subscribe to.
            callback: The callback function to handle received messages.

        """
        _LOGGER.debug("Attempting to subscribe to topic: %s", topic)
        self.subscriptions[topic] = callback

        if self.connected.is_set():
            try:
                async with asyncio.timeout(5):
                    await self.client.subscribe(topic)
                _LOGGER.debug("Successfully subscribed to topic: %s", topic)
            except (TimeoutError, Exception) as e:
                _LOGGER.error("Error subscribing to topic %s: %s", topic, e)
                # Force reconnection on subscription error
                self.connected.clear()
                self.hass.async_create_task(
                    self.connect_with_retry(self.username, self.password)
                )
        else:
            _LOGGER.debug(
                "Client not connected, topic %s will be subscribed upon reconnection",
                topic,
            )

    async def unsubscribe(self, topic: str):
        """Unsubscribe from an MQTT topic.

        Args:
            topic: The MQTT topic to unsubscribe from.

        """
        _LOGGER.debug("Attempting to unsubscribe from topic: %s", topic)
        self.subscriptions.pop(topic, None)

        if self.connected.is_set():
            try:
                async with asyncio.timeout(5):
                    await self.client.unsubscribe(topic)
                _LOGGER.debug("Successfully unsubscribed from topic: %s", topic)
            except (TimeoutError, Exception) as e:
                _LOGGER.error("Error unsubscribing from topic %s: %s", topic, e)

    async def publish(self, topic: str, payload: dict):
        """Publish a message to a topic.

        Args:
            topic: The MQTT topic to publish to.
            payload: The message payload to publish.

        Returns:
            bool: True if publishing was successful, False otherwise.

        """
        if not self.connected.is_set():
            _LOGGER.warning(
                "Cannot publish to %s: MQTT client is not connected. Attempting reconnection.",
                topic,
            )
            connected = await self.connect_with_retry(
                self.username, self.password, max_retries=2
            )
            if not connected:
                _LOGGER.error("Failed to reconnect, cannot publish message")
                return False

        try:
            _LOGGER.debug("Attempting to publish to %s: %s", topic, payload)
            async with asyncio.timeout(5):
                await self.client.publish(topic, json.dumps(payload))
            _LOGGER.debug("Successfully published to %s", topic)
            self._last_message_time = (
                time.time()
            )  # Update last message time after successful publish
            return True
        except TimeoutError:
            _LOGGER.error("Timeout publishing to %s", topic)
            # Force reconnection on timeout
            self.connected.clear()
            return False
        except Exception as e:
            _LOGGER.error("Error publishing to %s: %s", topic, e)
            # Force reconnection on error
            self.connected.clear()
            return False

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
