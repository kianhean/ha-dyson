"""Diagnostics support for Dyson Local."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from . import DysonAccountData, DysonConfigEntry, DysonDeviceData
from .cloud.const import CONF_AUTH
from .const import CONF_CREDENTIAL, CONF_SERIAL

TO_REDACT = {CONF_AUTH, CONF_CREDENTIAL, CONF_HOST, CONF_SERIAL}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DysonConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data
    diagnostics: dict[str, Any] = {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
    }
    if isinstance(data, DysonDeviceData):
        device = data.device
        # The raw protocol state is what's needed to support new models and firmware.
        diagnostics["device"] = {
            "class": type(device).__name__,
            "device_type": device.device_type,
            "connected": device.is_connected,
            "state": device._status,
            "environmental_data": getattr(device, "_environmental_data", None),
        }
    elif isinstance(data, DysonAccountData):
        diagnostics["account_devices"] = [
            {
                "product_type": device.product_type,
                "variant": getattr(device, "variant", None),
                "version": getattr(device, "version", None),
            }
            for device in data.devices
        ]
    return diagnostics
