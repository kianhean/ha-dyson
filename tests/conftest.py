"""Shared fixtures for the Dyson Local tests."""

from __future__ import annotations

from collections.abc import Generator
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from tests.fake_device import FakeDysonFan

if TYPE_CHECKING:
    from libdyson.dyson_device import DysonDevice


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow Home Assistant to load custom_components/dyson_local."""
    yield


@pytest.fixture(autouse=True)
def _mock_zeroconf(mock_async_zeroconf):
    """The integration depends on zeroconf, which would otherwise open sockets."""
    yield


class _LoopbackMqttClient:
    """Stands in for paho, routing publishes to a FakeDysonFan in-process."""

    def __init__(self, device: DysonDevice, fan: FakeDysonFan) -> None:
        self._device = device
        self._fan = fan

    def publish(self, topic: str, payload: str, qos: int = 0) -> None:
        for reply in self._fan.handle_command(json.loads(payload)):
            self._device._handle_message(reply)

    def disconnect(self) -> None:
        self._device._disconnected.set()

    def loop_stop(self) -> None:
        pass


@pytest.fixture
def fake_fan() -> Generator[FakeDysonFan]:
    """Replace libdyson's MQTT transport with an in-process fake fan.

    Everything above the transport (libdyson parsing, the integration,
    Home Assistant) runs for real.
    """
    from libdyson.dyson_device import DysonDevice  # noqa: PLC0415

    fan = FakeDysonFan()

    def _connect(self: DysonDevice, host: str) -> None:
        self._mqtt_client = _LoopbackMqttClient(self, fan)
        self._disconnected.clear()
        self._connected.set()
        self._request_first_data()

    def _disconnect(self: DysonDevice) -> None:
        self._connected.clear()
        self._disconnected.set()
        self._mqtt_client = None

    with (
        patch.object(DysonDevice, "connect", _connect),
        patch.object(DysonDevice, "disconnect", _disconnect),
    ):
        yield fan
