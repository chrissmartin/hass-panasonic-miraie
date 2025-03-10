"""Decorator module for tracking command execution in Panasonic Miraie device control.

This module provides decorators to track command execution timing and manage MQTT state
tracking flags for Panasonic Miraie device integration with Home Assistant.
"""

from functools import wraps
import time


def _track_command(method):
    """Track command execution and reset MQTT tracking flags."""

    @wraps(method)
    async def wrapper(self, *args, **kwargs):
        # Reset MQTT update tracking flag
        self._mqtt_state_received_after_command = False
        self._command_time = time.time()

        # Call the original method
        return await method(self, *args, **kwargs)

    return wrapper
