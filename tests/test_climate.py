import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.panasonic_miraie import climate as climate_module
from custom_components.panasonic_miraie.api import PanasonicMirAIeAPI
from custom_components.panasonic_miraie.climate import PanasonicMirAIeClimate
from custom_components.panasonic_miraie.const import PRESET_CLEAN, PRESET_NONE
from homeassistant.components.climate.const import (
    FAN_HIGH,
    SWING_ON,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE


def _state(**changes):
    state = {
        "onlineStatus": "true",
        "rmtmp": "23.0",
        "actmp": "24.0",
        "ps": "on",
        "acmd": "cool",
        "acfs": "auto",
        "acvs": "3",
        "achs": "3",
        "acng": "off",
        "acpm": "off",
        "acec": "off",
        "acem": "off",
        "cnv": 0,
    }
    state.update(changes)
    return state


def _entity(api=None):
    if api is None:
        api = SimpleNamespace()
    entity = PanasonicMirAIeClimate(api, "device/topic", "Bedroom", "device-id")
    entity.async_write_ha_state = Mock()

    def close_task(coro):
        coro.close()

    entity.hass = SimpleNamespace(async_create_task=close_task)
    return entity


def test_reliability_state_and_locks_are_per_entity() -> None:
    first = _entity()
    second = _entity()

    assert first._update_lock is not second._update_lock
    assert first._command_lock is not second._command_lock
    assert "_last_update_success" in first.__dict__
    assert "_missed_updates" in first.__dict__


def test_explicit_offline_status_is_preserved_but_omission_is_fresh() -> None:
    entity = _entity()

    asyncio.run(
        entity._handle_state_update("device/topic/state", _state(onlineStatus="false"))
    )

    assert entity.available is False
    assert entity._attr_extra_state_attributes["last_update_success"] is True

    state_without_online_status = _state()
    state_without_online_status.pop("onlineStatus")
    asyncio.run(
        entity._handle_state_update("device/topic/state", state_without_online_status)
    )

    assert entity.available is True


def test_poll_success_updates_last_update_success_attribute() -> None:
    api = SimpleNamespace(get_device_state=AsyncMock(return_value=_state()))
    entity = _entity(api)

    asyncio.run(entity.async_update())

    assert entity._last_update_success is True
    assert entity._attr_extra_state_attributes["last_update_success"] is True


def test_poll_without_online_status_is_fresh_and_available() -> None:
    raw_state = _state()
    raw_state.pop("onlineStatus")
    parsed_state = PanasonicMirAIeAPI._parse_device_state(None, raw_state)
    api = SimpleNamespace(get_device_state=AsyncMock(return_value=parsed_state))
    entity = _entity(api)
    entity._attr_available = False

    asyncio.run(entity.async_update())

    assert entity.available is True


def test_failed_polls_expire_historical_mqtt_state_and_recover() -> None:
    api = SimpleNamespace(
        get_device_state=AsyncMock(side_effect=RuntimeError("API unavailable"))
    )
    entity = _entity(api)
    asyncio.run(entity._handle_state_update("device/topic/state", _state()))

    for _ in range(3):
        asyncio.run(entity.async_update())

    assert entity.available is False
    assert entity._attr_extra_state_attributes["last_update_success"] is False

    state_without_online_status = _state()
    state_without_online_status.pop("onlineStatus")
    asyncio.run(
        entity._handle_state_update("device/topic/state", state_without_online_status)
    )

    assert entity.available is True
    assert entity._missed_updates == 0
    assert entity._attr_extra_state_attributes["last_update_success"] is True


def test_false_command_result_is_a_failure(monkeypatch) -> None:
    command = AsyncMock(return_value=False)
    entity = _entity()
    monkeypatch.setattr(climate_module, "CLIMATE_COMMAND_RETRY", 0)
    monkeypatch.setattr(climate_module.asyncio, "sleep", AsyncMock())

    success = asyncio.run(entity._send_command(command))

    assert success is False
    command.assert_awaited_once()


@pytest.mark.parametrize(
    ("setter", "expected_attribute", "expected_value"),
    [
        (
            lambda entity: entity.async_set_temperature(**{ATTR_TEMPERATURE: 26}),
            "_attr_target_temperature",
            24.0,
        ),
        (
            lambda entity: entity.async_set_fan_mode(FAN_HIGH),
            "_attr_fan_mode",
            "auto",
        ),
        (
            lambda entity: entity.async_set_swing_mode(SWING_ON),
            "_attr_swing_mode",
            "off",
        ),
        (
            lambda entity: entity.async_set_preset_mode(PRESET_CLEAN),
            "_attr_preset_mode",
            PRESET_NONE,
        ),
    ],
)
def test_setters_do_not_change_state_without_confirmation(
    monkeypatch, setter, expected_attribute, expected_value
) -> None:
    failed_command = AsyncMock(return_value=False)
    api = SimpleNamespace(
        set_temperature=failed_command,
        set_fan_mode=failed_command,
        set_swing_mode=failed_command,
        set_nanoe=failed_command,
        set_powerful_mode=failed_command,
        set_economy_mode=failed_command,
        set_clean_mode=failed_command,
        set_converti7_mode=failed_command,
    )
    entity = _entity(api)
    asyncio.run(entity._handle_state_update("device/topic/state", _state()))
    monkeypatch.setattr(climate_module, "CLIMATE_COMMAND_RETRY", 0)
    monkeypatch.setattr(climate_module.asyncio, "sleep", AsyncMock())

    asyncio.run(setter(entity))

    assert getattr(entity, expected_attribute) == expected_value


def test_missing_mqtt_confirmation_polls_before_setter_returns(monkeypatch) -> None:
    api = SimpleNamespace(
        set_temperature=AsyncMock(return_value=True),
        get_device_state=AsyncMock(return_value=_state(actmp="25.0")),
    )
    entity = _entity(api)
    asyncio.run(entity._handle_state_update("device/topic/state", _state()))
    monkeypatch.setattr(climate_module.asyncio, "sleep", AsyncMock())

    asyncio.run(entity.async_set_temperature(**{ATTR_TEMPERATURE: 26}))

    api.get_device_state.assert_awaited_once_with("device-id")
    assert entity.target_temperature == 25.0


def test_each_publish_requires_its_own_confirmation(monkeypatch) -> None:
    api = SimpleNamespace()
    entity = _entity(api)

    async def set_power(*_):
        await entity._handle_state_update("device/topic/state", _state(acmd="cool"))
        return True

    api.set_power = set_power
    api.set_mode = AsyncMock(return_value=True)
    api.get_device_state = AsyncMock(return_value=_state(acmd="heat"))
    monkeypatch.setattr(climate_module.asyncio, "sleep", AsyncMock())

    asyncio.run(entity.async_set_hvac_mode(HVACMode.HEAT))

    api.get_device_state.assert_awaited_once_with("device-id")
    assert entity.hvac_mode == HVACMode.HEAT
