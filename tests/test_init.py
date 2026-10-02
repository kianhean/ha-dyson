"""Setup, entity and service tests for Dyson Local, run inside Home Assistant."""

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from libdyson.dyson_device import DysonDevice
from libdyson.exceptions import DysonConnectTimeout
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dyson_local.const import DOMAIN
from tests.fake_device import CREDENTIAL, DEVICE_TYPE, NAME, SERIAL


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=NAME,
        unique_id=SERIAL,
        data={
            "serial": SERIAL,
            "credential": CREDENTIAL,
            "device_type": DEVICE_TYPE,
            "name": NAME,
            "host": "192.0.2.10",
        },
    )
    entry.add_to_hass(hass)
    return entry


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
