import json
import logging
import asyncio
import socket
from typing import Callable, Any
from homeassistant.core import HomeAssistant
import paho.mqtt.client as mqtt

from .const import MIRAIE_BROKER_HOST, MIRAIE_BROKER_PORT, MIRAIE_BROKER_USE_SSL

_LOGGER = logging.getLogger(__name__)


class MQTTHandler:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.client = None
        self.connected = asyncio.Event()
        self.subscriptions = {}
        self.connect_future = None
        self.reconnect_interval = 5
        self.max_reconnect_interval = 300
        self.reconnect_count = 0
        self.max_reconnect_attempts = 10
        self.username = None
        self.password = None

    async def connect(self, username: str, password: str):
        """Connect to the MQTT broker."""
        self.username = username
        self.password = password
        self.client = mqtt.Client(
            "PBcMcfG19njNCL8AOgvRzIC8AjQa", clean_session=True, protocol=mqtt.MQTTv311
        )
        self.client.username_pw_set(username, password)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        # Set a longer keep-alive interval and disable automatic reconnect
        self.client.keepalive = 60
        self.client.reconnect_delay_set(min_delay=1, max_delay=120)

        if MIRAIE_BROKER_USE_SSL:
            self.client.tls_set()

        self.connect_future = asyncio.Future()

        try:
            _LOGGER.debug(f"Resolving hostname {MIRAIE_BROKER_HOST}")
            ip_address = socket.gethostbyname(MIRAIE_BROKER_HOST)
            _LOGGER.debug(f"Resolved {MIRAIE_BROKER_HOST} to {ip_address}")

            _LOGGER.debug(
                f"Attempting to connect with username: {username}, password: {password[:5]}..."
            )
            self.client.connect_async(MIRAIE_BROKER_HOST, MIRAIE_BROKER_PORT)
            self.client.loop_start()

            # Wait for the connection to be established
            await asyncio.wait_for(self.connect_future, timeout=10.0)
            _LOGGER.info("Connected to Panasonic MirAIe MQTT broker")
            self.reconnect_count = 0
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout while connecting to MQTT broker")
            await self.disconnect()
        except Exception as error:
            _LOGGER.error(f"Error connecting to MQTT broker: {error}")
            await self.disconnect()

    async def disconnect(self):
        """Disconnect from the MQTT broker."""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.client = None
        self.connected.clear()
        _LOGGER.info("Disconnected from Panasonic MirAIe MQTT broker")

    async def subscribe(self, topic: str, callback: Callable[[str, Any], None]):
        """Subscribe to an MQTT topic."""
        await self.connected.wait()
        self.subscriptions[topic] = callback
        result, _ = self.client.subscribe(topic)
        if result == mqtt.MQTT_ERR_SUCCESS:
            _LOGGER.debug(f"Subscribed to topic: {topic}")
        else:
            _LOGGER.error(f"Failed to subscribe to topic: {topic}")

    async def unsubscribe(self, topic: str):
        """Unsubscribe from an MQTT topic."""
        await self.connected.wait()
        result, _ = self.client.unsubscribe(topic)
        if result == mqtt.MQTT_ERR_SUCCESS:
            self.subscriptions.pop(topic, None)
            _LOGGER.debug(f"Unsubscribed from topic: {topic}")
        else:
            _LOGGER.error(f"Failed to unsubscribe from topic: {topic}")

    async def publish(self, topic: str, payload: dict):
        """Publish a message to a topic."""
        if not self.is_connected():
            _LOGGER.warning("Cannot publish: MQTT client is not connected")
            await self.reconnect()
            if not self.is_connected():
                _LOGGER.error("Failed to reconnect. Cannot publish message.")
                return

        try:
            _LOGGER.debug(f"Attempting to publish to {topic}: {payload}")
            message_info = self.client.publish(topic, json.dumps(payload))
            if message_info.is_published():
                _LOGGER.debug(f"Successfully published to {topic}: {payload}")
            else:
                _LOGGER.warning(f"Failed to publish to {topic}: {payload}")
        except Exception as e:
            _LOGGER.error(f"Error publishing to {topic}: {e}")

    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when the client receives a CONNACK response from the server."""
        if rc == 0:
            self.connected.set()
            if not self.connect_future.done():
                self.connect_future.set_result(True)
            _LOGGER.info("Successfully connected to MQTT broker")
            self.reconnect_interval = 5
            self.reconnect_count = 0
        else:
            error_message = f"Connection failed with code {rc}: "
            if rc == 1:
                error_message += "Incorrect protocol version"
            elif rc == 2:
                error_message += "Invalid client identifier"
            elif rc == 3:
                error_message += "Server unavailable"
            elif rc == 4:
                error_message += "Bad username or password"
            elif rc == 5:
                error_message += "Not authorised"
            else:
                error_message += "Unknown error"

            _LOGGER.error(error_message)
            _LOGGER.debug(
                f"Connection attempt details - Host: {MIRAIE_BROKER_HOST}, Port: {MIRAIE_BROKER_PORT}, SSL: {MIRAIE_BROKER_USE_SSL}"
            )

            if not self.connect_future.done():
                self.connect_future.set_exception(Exception(error_message))

    def _on_disconnect(self, client, userdata, rc):
        """Callback for when the client disconnects from the server."""
        self.connected.clear()
        if rc == 0:
            _LOGGER.info("Disconnected from MQTT broker")
        else:
            error_message = f"Unexpected disconnection. RC: {rc}. "
            if rc == 1:
                error_message += "Unacceptable protocol version"
            elif rc == 2:
                error_message += "Identifier rejected"
            elif rc == 3:
                error_message += "Server unavailable"
            elif rc == 4:
                error_message += "Bad user name or password"
            elif rc == 5:
                error_message += "Not authorized"
            elif rc == 7:
                error_message += "Network error"
            else:
                error_message += "Unknown error"

            _LOGGER.warning(error_message)
            _LOGGER.debug("Attempting to reconnect...")

        # Attempt to reconnect
        self.hass.loop.call_soon_threadsafe(self.reconnect())

    def _schedule_reconnect(self):
        """Schedule the reconnection task on the event loop."""
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = self.hass.loop.create_task(self._reconnect())

    def _on_message(self, client, userdata, message):
        """Callback for when a PUBLISH message is received from the server."""
        try:
            payload_dict = json.loads(message.payload.decode())
            if message.topic in self.subscriptions:
                callback = self.subscriptions[message.topic]
                asyncio.run_coroutine_threadsafe(
                    callback(message.topic, payload_dict), self.hass.loop
                )
        except json.JSONDecodeError:
            _LOGGER.error(f"Failed to decode MQTT message: {message.payload}")
        except Exception as e:
            _LOGGER.error(f"Error handling MQTT message: {e}")

    async def wait_for_connection(self, timeout=10):
        """Wait for the MQTT connection to be established."""
        try:
            await asyncio.wait_for(self.connected.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            _LOGGER.error(
                f"Timeout waiting for MQTT connection after {timeout} seconds"
            )
            raise

    async def reconnect(self):
        """Reconnect to the MQTT broker with exponential backoff."""
        while (
            not self.is_connected()
            and self.reconnect_count < self.max_reconnect_attempts
        ):
            self.reconnect_count += 1
            try:
                _LOGGER.info(
                    f"Attempting to reconnect in {self.reconnect_interval} seconds (attempt {self.reconnect_count}/{self.max_reconnect_attempts})..."
                )
                await asyncio.sleep(self.reconnect_interval)
                await self.connect(self.username, self.password)
                if self.is_connected():
                    _LOGGER.info("Successfully reconnected to MQTT broker")
                    return
            except Exception as e:
                _LOGGER.error(f"Reconnection attempt failed: {e}")

            # Increase reconnect interval with exponential backoff
            self.reconnect_interval = min(
                self.reconnect_interval * 2, self.max_reconnect_interval
            )

        if self.reconnect_count >= self.max_reconnect_attempts:
            _LOGGER.error(
                "Max reconnection attempts reached. Please check your network connection and MQTT broker status."
            )

    def is_connected(self):
        """Check if the MQTT client is connected."""
        return self.client and self.client.is_connected() and self.connected.is_set()
