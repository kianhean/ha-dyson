"""Diagnostics tests for Dyson Local."""

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)

from tests.fake_device import CREDENTIAL, SERIAL


async def test_device_diagnostics(
    hass: HomeAssistant, hass_client, config_entry: MockConfigEntry, fake_fan
) -> None:
    """Diagnostics include the raw device state but no secrets."""
    assert await async_setup_component(hass, "diagnostics", {})
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await get_diagnostics_for_config_entry(hass, hass_client, config_entry)

    assert result["device"]["class"] == "DysonPureCool"
    assert result["device"]["connected"] is True
    assert result["device"]["state"]["fpwr"] == "ON"
    assert result["device"]["environmental_data"]["p25r"] == "0011"
    assert result["entry_data"]["credential"] == "**REDACTED**"
    assert result["entry_data"]["host"] == "**REDACTED**"
    assert CREDENTIAL not in str(result)
    assert SERIAL not in str(result)
