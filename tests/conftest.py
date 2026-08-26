"""Minimal test setup for optional runtime dependencies."""

import sys
from types import ModuleType

try:
    import aiomqtt  # noqa: F401
except ModuleNotFoundError:
    aiomqtt = ModuleType("aiomqtt")

    class MqttError(Exception):
        """Stand-in used when aiomqtt is not installed in the test environment."""

    class Client:
        """Stand-in used only while importing the integration."""

    aiomqtt.Client = Client
    aiomqtt.MqttError = MqttError
    sys.modules["aiomqtt"] = aiomqtt
