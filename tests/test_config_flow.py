"""Config flow tests for Dyson Local."""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from libdyson.dyson_device import DysonDevice
from libdyson.exceptions import DysonConnectTimeout, DysonInvalidCredential
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dyson_local.const import DOMAIN
from tests.fake_device import CREDENTIAL, DEVICE_TYPE, SERIAL

HOST = "192.0.2.10"

MANUAL_INPUT = {
    "serial": SERIAL,
    "credential": CREDENTIAL,
    "device_type": DEVICE_TYPE,
    "host": HOST,
}


async def _start_manual_flow(hass: HomeAssistant) -> str:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"method": "manual"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"
    return result["flow_id"]


async def test_manual_flow_creates_entry(hass: HomeAssistant, fake_fan) -> None:
    """A reachable device produces a config entry with its connection data."""
    flow_id = await _start_manual_flow(hass)

    with patch(
        "custom_components.dyson_local.async_setup_entry", return_value=True
    ) as mock_setup_entry:
        result = await hass.config_entries.flow.async_configure(flow_id, MANUAL_INPUT)
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {**MANUAL_INPUT, "name": result["title"]}
    assert result["result"].unique_id == SERIAL
    assert len(mock_setup_entry.mock_calls) == 1
    # The flow verified the connection by fetching state from the device.
    assert {msg["msg"] for msg in fake_fan.received} >= {
        "REQUEST-CURRENT-STATE",
        "REQUEST-PRODUCT-ENVIRONMENT-CURRENT-SENSOR-DATA",
    }


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        (DysonInvalidCredential, "invalid_auth"),
        (DysonConnectTimeout, "cannot_connect"),
    ],
)
async def test_manual_flow_connection_errors(
    hass: HomeAssistant, exception: type[Exception], error: str
) -> None:
    """Connection failures are reported on the form and can be retried."""
    flow_id = await _start_manual_flow(hass)

    with patch.object(DysonDevice, "connect", side_effect=exception):
        result = await hass.config_entries.flow.async_configure(flow_id, MANUAL_INPUT)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manual"
    assert result["errors"] == {"base": error}


async def test_manual_flow_already_configured(hass: HomeAssistant) -> None:
    """Adding the same serial twice aborts."""
    MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, data=MANUAL_INPUT).add_to_hass(hass)
    flow_id = await _start_manual_flow(hass)

    result = await hass.config_entries.flow.async_configure(flow_id, MANUAL_INPUT)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
