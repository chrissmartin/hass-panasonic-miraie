import asyncio
from unittest.mock import AsyncMock, MagicMock

from custom_components.panasonic_miraie.mqtt_handler import MQTTHandler


def test_connected_quiet_subscription_is_not_reconnected() -> None:
    handler = MQTTHandler(MagicMock())
    handler.connected.set()
    handler._last_message_time = 0
    handler.connect_with_retry = AsyncMock(return_value=True)

    asyncio.run(handler._check_connection_status())

    handler.connect_with_retry.assert_not_awaited()


def test_disconnected_client_is_still_reconnected() -> None:
    handler = MQTTHandler(MagicMock())
    handler.connect_with_retry = AsyncMock(return_value=True)

    asyncio.run(handler._check_connection_status())

    handler.connect_with_retry.assert_awaited_once_with(None, None)
