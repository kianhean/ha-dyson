"""The e2e suite talks to a running Home Assistant over HTTP and MQTT.

It runs without pytest-homeassistant-custom-component, so the in-process
fixtures from tests/conftest.py are switched off here.
"""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations():
    yield


@pytest.fixture(autouse=True)
def _mock_zeroconf():
    yield
