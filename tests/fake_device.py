"""Protocol-level model of a Dyson Pure Cool (438 / TP04) fan.

Shared by the in-process integration tests, which feed these messages
straight into a libdyson device, and the e2e device simulator, which serves
them over MQTT exactly like real hardware does.
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

SERIAL = "XX1-EU-ABC1234A"
CREDENTIAL = "e2e-credential"
DEVICE_TYPE = "438"
NAME = "Living Room Fan"

COMMAND_TOPIC = f"{DEVICE_TYPE}/{SERIAL}/command"
STATUS_TOPIC = f"{DEVICE_TYPE}/{SERIAL}/status/current"

INITIAL_STATE: dict[str, str] = {
    "fpwr": "ON",
    "fdir": "ON",
    "auto": "OFF",
    "oscs": "ON",
    "oson": "ON",
    "nmod": "OFF",
    "rhtm": "ON",
    "fnst": "FAN",
    "ercd": "NONE",
    "wacd": "NONE",
    "nmdv": "0004",
    "fnsp": "0005",
    "bril": "0002",
    "corf": "ON",
    "cflr": "0095",
    "hflr": "0090",
    "sltm": "OFF",
    "osal": "0045",
    "osau": "0315",
    "ancp": "CUST",
}

# Extra state reported by other fan families, keyed by device type.
EXTRA_STATE: dict[str, dict[str, str]] = {
    DEVICE_TYPE: {},
    # Pure Hot+Cool (HP04)
    "527": {"hmod": "OFF", "hmax": "2960", "hsta": "OFF", "ffoc": "ON", "tilt": "OK"},
    # Pure Humidify+Cool (PH01)
    "358": {
        "ancp": "0045",
        "hume": "HUMD",
        "haut": "OFF",
        "humt": "0050",
        "rect": "0050",
        "wath": "1350",
        "cltr": "0100",
        "cdrr": "0000",
        "msta": "OFF",
        "psta": "CLNG",
    },
}

ENVIRONMENTAL_DATA: dict[str, str] = {
    "tact": "2950",
    "hact": "0045",
    "pm25": "0010",
    "pm10": "0008",
    "p25r": "0011",
    "p10r": "0009",
    "va10": "0004",
    "noxl": "0002",
    "sltm": "OFF",
}


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class FakeDysonFan:
    """Answers libdyson commands the way a real Pure Cool fan does."""

    def __init__(self, device_type: str = DEVICE_TYPE) -> None:
        self.device_type = device_type
        self.state = {**copy.deepcopy(INITIAL_STATE), **EXTRA_STATE[device_type]}
        self.environmental = copy.deepcopy(ENVIRONMENTAL_DATA)
        self.received: list[dict[str, Any]] = []

    def current_state(self) -> dict[str, Any]:
        return {
            "msg": "CURRENT-STATE",
            "time": _now(),
            "mode-reason": "LAPP",
            "state-reason": "MODE",
            "product-state": copy.deepcopy(self.state),
        }

    def environmental_state(self) -> dict[str, Any]:
        return {
            "msg": "ENVIRONMENTAL-CURRENT-SENSOR-DATA",
            "time": _now(),
            "data": copy.deepcopy(self.environmental),
        }

    def apply_state_set(self, data: dict[str, str]) -> dict[str, Any]:
        """Apply a STATE-SET and return the STATE-CHANGE the device emits."""
        old = copy.deepcopy(self.state)
        self.state.update(data)
        if "fpwr" in data:
            self.state["fnst"] = "FAN" if data["fpwr"] == "ON" else "OFF"
        if "sltm" in data:
            # The running timer is reported with the environmental data.
            self.environmental["sltm"] = data["sltm"]
        return {
            "msg": "STATE-CHANGE",
            "time": _now(),
            "mode-reason": "LAPP",
            "state-reason": "MODE",
            "product-state": {key: [old.get(key, value), value] for key, value in self.state.items()},
        }

    def handle_command(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Return the messages the device publishes in reply to a command."""
        self.received.append(payload)
        msg = payload.get("msg")
        if msg == "REQUEST-CURRENT-STATE":
            return [self.current_state()]
        if msg == "REQUEST-PRODUCT-ENVIRONMENT-CURRENT-SENSOR-DATA":
            return [self.environmental_state()]
        if msg == "STATE-SET":
            return [self.apply_state_set(payload.get("data", {}))]
        return []
