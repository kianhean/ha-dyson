"""End-to-end tests: a real Home Assistant talking MQTT to a simulated fan.

Needs the stack from tests/e2e/docker-compose.yml to be running. Everything is
driven the way a user would: onboarding, the config flow, and service calls
all go through Home Assistant's HTTP API, and the commands that reach the fan
are observed on its MQTT broker.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
import json
import os
import queue
import time
from typing import Any

import paho.mqtt.client as mqtt
import pytest
import requests

from tests.fake_device import COMMAND_TOPIC, CREDENTIAL, DEVICE_TYPE, SERIAL

HA_URL = os.environ.get("HA_URL", "http://localhost:8123")
MQTT_HOST = os.environ.get("E2E_MQTT_HOST", "localhost")
# The address Home Assistant uses to reach the fan, inside the compose network.
FAN_HOST = os.environ.get("E2E_FAN_HOST", "fan")

CLIENT_ID = f"{HA_URL}/"
USERNAME = "e2e"
PASSWORD = "e2e-password"
TIMEOUT = 60


def wait_for(condition: Callable[[], Any], timeout: float = TIMEOUT, what: str = "") -> Any:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if result := condition():
                return result
        except (requests.RequestException, KeyError, AssertionError) as err:
            last_error = err
        time.sleep(1)
    raise TimeoutError(f"Timed out waiting for {what or condition}: {last_error}")


def _token_from_code(code: str) -> str:
    response = requests.post(
        f"{HA_URL}/auth/token",
        data={"grant_type": "authorization_code", "code": code, "client_id": CLIENT_ID},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _onboard_or_login() -> str:
    """Create the owner on a fresh instance, or log in to an onboarded one."""
    response = requests.post(
        f"{HA_URL}/api/onboarding/users",
        json={
            "client_id": CLIENT_ID,
            "name": "E2E",
            "username": USERNAME,
            "password": PASSWORD,
            "language": "en",
        },
        timeout=10,
    )
    if response.ok:
        return _token_from_code(response.json()["auth_code"])

    flow = requests.post(
        f"{HA_URL}/auth/login_flow",
        json={
            "client_id": CLIENT_ID,
            "handler": ["homeassistant", None],
            "redirect_uri": CLIENT_ID,
        },
        timeout=10,
    ).json()
    result = requests.post(
        f"{HA_URL}/auth/login_flow/{flow['flow_id']}",
        json={"client_id": CLIENT_ID, "username": USERNAME, "password": PASSWORD},
        timeout=10,
    ).json()
    return _token_from_code(result["result"])


class HomeAssistantApi:
    def __init__(self, token: str) -> None:
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {token}"

    def get(self, path: str) -> Any:
        response = self._session.get(f"{HA_URL}{path}", timeout=10)
        response.raise_for_status()
        return response.json()

    def post(self, path: str, payload: dict | None = None) -> Any:
        response = self._session.post(f"{HA_URL}{path}", json=payload or {}, timeout=30)
        response.raise_for_status()
        return response.json()

    def delete(self, path: str) -> None:
        self._session.delete(f"{HA_URL}{path}", timeout=10).raise_for_status()

    def state(self, entity_id: str) -> dict[str, Any]:
        return self.get(f"/api/states/{entity_id}")

    def find_entity(self, domain: str, friendly_name: str) -> str:
        for state in self.get("/api/states"):
            if (
                state["entity_id"].startswith(f"{domain}.")
                and state["attributes"].get("friendly_name") == friendly_name
            ):
                return state["entity_id"]
        raise KeyError(f"{domain} entity named {friendly_name!r}")

    def entries(self) -> list[dict[str, Any]]:
        return self.get("/api/config/config_entries/entry?domain=dyson_local")

    def call(self, domain: str, service: str, data: dict[str, Any]) -> None:
        self.post(f"/api/services/{domain}/{service}", data)


class FanCommands:
    """Records the commands Home Assistant sends to the fan over MQTT."""

    def __init__(self) -> None:
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="e2e-observer")
        self._client.on_connect = lambda client, *_: client.subscribe(COMMAND_TOPIC, qos=1)
        self._client.on_message = lambda _c, _u, msg: self._queue.put(json.loads(msg.payload))
        self._client.connect(MQTT_HOST, 1883)
        self._client.loop_start()

    def clear(self) -> None:
        while not self._queue.empty():
            self._queue.get_nowait()

    def expect_state_set(self, timeout: float = 15) -> dict[str, str]:
        deadline = time.monotonic() + timeout
        while (remaining := deadline - time.monotonic()) > 0:
            try:
                command = self._queue.get(timeout=remaining)
            except queue.Empty:
                break
            if command["msg"] == "STATE-SET":
                return command["data"]
        raise AssertionError("Home Assistant sent no STATE-SET to the fan")

    def close(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()


@pytest.fixture(scope="module")
def api() -> HomeAssistantApi:
    wait_for(
        lambda: requests.get(f"{HA_URL}/manifest.json", timeout=5).ok,
        timeout=300,
        what="Home Assistant to start",
    )
    ha = HomeAssistantApi(_onboard_or_login())
    for entry in ha.entries():
        ha.delete(f"/api/config/config_entries/entry/{entry['entry_id']}")
    return ha


@pytest.fixture(scope="module")
def fan_commands() -> Generator[FanCommands]:
    commands = FanCommands()
    yield commands
    commands.close()


@pytest.fixture(scope="module")
def entry_id(api: HomeAssistantApi, fan_commands: FanCommands) -> str:
    """Add the fan through the config flow, exactly as a user would."""
    flow = api.post("/api/config/config_entries/flow", {"handler": "dyson_local"})
    assert flow["type"] == "form" and flow["step_id"] == "user"

    flow = api.post(f"/api/config/config_entries/flow/{flow['flow_id']}", {"method": "manual"})
    assert flow["type"] == "form" and flow["step_id"] == "manual"

    result = api.post(
        f"/api/config/config_entries/flow/{flow['flow_id']}",
        {
            "serial": SERIAL,
            "credential": CREDENTIAL,
            "device_type": DEVICE_TYPE,
            "host": FAN_HOST,
        },
    )
    assert result["type"] == "create_entry", result
    return result["result"]["entry_id"]


@pytest.fixture(scope="module")
def name(api: HomeAssistantApi, entry_id: str) -> str:
    """The device name, which the manual flow takes from the model name."""
    return next(e["title"] for e in api.entries() if e["entry_id"] == entry_id)


def _entry_state(api: HomeAssistantApi, entry_id: str) -> str:
    return next(e["state"] for e in api.entries() if e["entry_id"] == entry_id)


def test_config_entry_loads(api: HomeAssistantApi, entry_id: str) -> None:
    wait_for(lambda: _entry_state(api, entry_id) == "loaded", what="the entry to load")


def test_entities_reflect_device_state(api: HomeAssistantApi, name: str) -> None:
    fan_id = wait_for(lambda: api.find_entity("fan", name), what="the fan entity")
    fan = api.state(fan_id)
    assert fan["state"] == "on"
    assert fan["attributes"]["percentage"] == 50

    assert api.state(api.find_entity("sensor", f"{name} PM 2.5"))["state"] == "11"
    assert api.state(api.find_entity("sensor", f"{name} HEPA Filter Life"))["state"] == "90"


def test_fan_control_round_trip(
    api: HomeAssistantApi, name: str, fan_commands: FanCommands
) -> None:
    fan_id = api.find_entity("fan", name)

    fan_commands.clear()
    api.call("fan", "turn_off", {"entity_id": fan_id})
    assert fan_commands.expect_state_set()["fpwr"] == "OFF"
    wait_for(lambda: api.state(fan_id)["state"] == "off", what="the fan to report off")

    fan_commands.clear()
    api.call("fan", "set_percentage", {"entity_id": fan_id, "percentage": 80})
    assert fan_commands.expect_state_set()["fnsp"] == "0008"
    wait_for(
        lambda: api.state(fan_id)["attributes"]["percentage"] == 80,
        what="the fan to report 80%",
    )


def test_switch_round_trip(
    api: HomeAssistantApi, name: str, fan_commands: FanCommands
) -> None:
    switch_id = api.find_entity("switch", f"{name} Night Mode")

    fan_commands.clear()
    api.call("switch", "turn_on", {"entity_id": switch_id})
    assert fan_commands.expect_state_set()["nmod"] == "ON"
    wait_for(lambda: api.state(switch_id)["state"] == "on", what="night mode to report on")


def test_number_round_trip(
    api: HomeAssistantApi, name: str, fan_commands: FanCommands
) -> None:
    number_id = api.find_entity("number", f"{name} Airflow Speed")

    fan_commands.clear()
    api.call("number", "set_value", {"entity_id": number_id, "value": 3})
    assert fan_commands.expect_state_set()["fnsp"] == "0003"
    wait_for(lambda: float(api.state(number_id)["state"]) == 3, what="airflow speed to report 3")


def test_reload_reconnects(api: HomeAssistantApi, entry_id: str, name: str) -> None:
    api.post(f"/api/config/config_entries/entry/{entry_id}/reload")
    wait_for(lambda: _entry_state(api, entry_id) == "loaded", what="the entry to reload")
    fan_id = api.find_entity("fan", name)
    wait_for(lambda: api.state(fan_id)["state"] != "unavailable", what="the fan to come back")


def test_no_integration_errors_logged(api: HomeAssistantApi, entry_id: str) -> None:
    response = api._session.get(f"{HA_URL}/api/error_log", timeout=10)
    response.raise_for_status()
    errors = [
        line
        for line in response.text.splitlines()
        if " ERROR " in line and ("dyson_local" in line or "libdyson" in line)
    ]
    assert not errors, "\n".join(errors)
