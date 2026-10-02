"""Setup, entity and service tests for Dyson Local, run inside Home Assistant."""

import threading
from unittest.mock import MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from libdyson.dyson_device import DysonDevice
from libdyson.exceptions import DysonConnectTimeout
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dyson_local.const import DOMAIN
from tests.fake_device import SERIAL


def _entity_id(hass: HomeAssistant, domain: str, suffix: str | None = None) -> str:
    unique_id = SERIAL if suffix is None else f"{SERIAL}-{suffix}"
    entity_id = er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique_id)
    assert entity_id is not None, f"no {domain} entity with unique_id {unique_id}"
    return entity_id


async def test_setup_and_unload(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_fan
) -> None:
    """The entry loads, exposes the device's state and unloads cleanly."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED

    fan = hass.states.get(_entity_id(hass, "fan"))
    assert fan.state == STATE_ON
    assert fan.attributes["percentage"] == 50
    assert fan.attributes["oscillating"] is True

    assert hass.states.get(_entity_id(hass, "sensor", "pm25")).state == "11"
    assert hass.states.get(_entity_id(hass, "sensor", "pm10")).state == "9"
    assert hass.states.get(_entity_id(hass, "sensor", "hepa_filter_life")).state == "90"
    assert hass.states.get(_entity_id(hass, "switch", "night_mode")).state == STATE_OFF

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retries_when_device_unreachable(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """An unreachable device puts the entry into setup-retry, not error."""
    with patch.object(DysonDevice, "connect", side_effect=DysonConnectTimeout):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_fan_services_send_commands(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_fan
) -> None:
    """Fan services reach the device and the reported state flows back."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    fan_id = _entity_id(hass, "fan")

    await hass.services.async_call(
        "fan", "turn_off", {ATTR_ENTITY_ID: fan_id}, blocking=True
    )
    await hass.async_block_till_done()
    assert fake_fan.received[-1]["msg"] == "STATE-SET"
    assert fake_fan.received[-1]["data"]["fpwr"] == "OFF"
    assert hass.states.get(fan_id).state == STATE_OFF

    await hass.services.async_call(
        "fan", "set_percentage", {ATTR_ENTITY_ID: fan_id, "percentage": 80}, blocking=True
    )
    await hass.async_block_till_done()
    assert fake_fan.state["fnsp"] == "0008"
    assert fake_fan.state["fpwr"] == "ON"
    state = hass.states.get(fan_id)
    assert state.state == STATE_ON
    assert state.attributes["percentage"] == 80


async def test_night_mode_switch(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_fan
) -> None:
    """The night mode switch toggles the device setting."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    switch_id = _entity_id(hass, "switch", "night_mode")

    await hass.services.async_call(
        "switch", "turn_on", {ATTR_ENTITY_ID: switch_id}, blocking=True
    )
    await hass.async_block_till_done()

    assert fake_fan.state["nmod"] == "ON"
    assert hass.states.get(switch_id).state == STATE_ON


@pytest.mark.parametrize(
    ("domain", "suffix", "service", "data", "expected"),
    [
        ("switch", "auto_mode", "turn_on", {}, {"auto": "ON"}),
        ("switch", "oscillation", "turn_off", {}, {"oson": "OFF"}),
        ("number", "airflow_speed", "set_value", {"value": 3}, {"fnsp": "0003", "auto": "OFF"}),
        ("number", "sleep_timer", "set_value", {"value": 30}, {"sltm": "0030"}),
        ("number", "sleep_timer", "set_value", {"value": 0}, {"sltm": "OFF"}),
        ("select", "airflow_direction", "select_option", {"option": "Back"}, {"fdir": "OFF"}),
    ],
)
async def test_control_entities(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    fake_fan,
    domain: str,
    suffix: str,
    service: str,
    data: dict,
    expected: dict,
) -> None:
    """Each control entity sends the matching setting to the device."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        domain,
        service,
        {ATTR_ENTITY_ID: _entity_id(hass, domain, suffix), **data},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert {key: fake_fan.state[key] for key in expected} == expected


async def test_sleep_timer_reports_remaining_minutes(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_fan
) -> None:
    """The sleep timer number reflects the timer the device reports."""
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    timer_id = _entity_id(hass, "number", "sleep_timer")
    assert hass.states.get(timer_id).state == "0"

    await hass.services.async_call(
        "number", "set_value", {ATTR_ENTITY_ID: timer_id, "value": 45}, blocking=True
    )
    await hass.async_block_till_done()

    assert hass.states.get(timer_id).state == "45"


@pytest.mark.parametrize(
    ("device_type", "platform", "expected"),
    [
        ("527", "climate", "cool"),
        ("358", "humidifier", "on"),
    ],
)
async def test_other_fan_families_load(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    fake_fan,
    device_type: str,
    platform: str,
    expected: str,
) -> None:
    """Hot+Cool and Humidify+Cool fans load their extra platforms."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(_entity_id(hass, "fan")).state == STATE_ON
    assert hass.states.get(_entity_id(hass, platform)).state == expected

    assert await hass.config_entries.async_unload(config_entry.entry_id)


class _FakeDiscovery:
    """DysonDiscovery stand-in that finds every registered device at once."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._discovered: dict[str, str] = {}
        self._registered: dict[str, object] = {}

    def start_discovery(self, zeroconf) -> None:
        pass

    def stop_discovery(self) -> None:
        pass

    def register_device(self, device, callback) -> None:
        # Called from an executor thread, like the real zeroconf callback.
        self._registered[device.serial] = callback
        callback("192.0.2.20")


async def test_setup_via_discovery(
    hass: HomeAssistant, config_entry: MockConfigEntry, fake_fan
) -> None:
    """Without a static host the device connects once zeroconf finds it."""
    hass.config_entries.async_update_entry(
        config_entry, data={**config_entry.data, "host": None}
    )
    with patch("custom_components.dyson_local.DysonDiscovery", _FakeDiscovery):
        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        assert config_entry.state is ConfigEntryState.LOADED
        assert hass.states.get(_entity_id(hass, "fan")).state == STATE_ON

        assert await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_cloud_account_starts_device_discovery(hass: HomeAssistant) -> None:
    """A MyDyson account entry offers each cloud device for setup."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="MyDyson: user@example.com (GB)",
        unique_id="global_user@example.com",
        data={"region": "GB", "auth": {"token": "secret"}},
    )
    entry.add_to_hass(hass)
    cloud_device = MagicMock(
        serial=SERIAL, name="Bedroom", product_type="438", variant=None
    )
    cloud_device.name = "Bedroom"

    with patch("custom_components.dyson_local.DysonAccount") as account_cls:
        account_cls.return_value.devices.return_value = [cloud_device]
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["step_id"] for flow in flows] == ["host"]
    assert flows[0]["context"]["unique_id"] == SERIAL

    assert await hass.config_entries.async_unload(entry.entry_id)
