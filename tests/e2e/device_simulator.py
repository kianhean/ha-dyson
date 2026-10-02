"""Simulated Dyson Pure Cool fan firmware for the e2e stack.

Connects to the fan's MQTT broker and answers libdyson's commands using the
same protocol model as the in-process tests (tests/fake_device.py).
"""

import json
import logging
import os

import paho.mqtt.client as mqtt

from tests.fake_device import COMMAND_TOPIC, STATUS_TOPIC, FakeDysonFan

_LOGGER = logging.getLogger("device_simulator")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    fan = FakeDysonFan()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="dyson-fan-firmware")

    def on_connect(client, userdata, flags, reason_code, properties):
        _LOGGER.info("Connected to broker (%s), listening on %s", reason_code, COMMAND_TOPIC)
        client.subscribe(COMMAND_TOPIC, qos=1)

    def on_message(client, userdata, message):
        payload = json.loads(message.payload)
        _LOGGER.info("<- %s", payload)
        for reply in fan.handle_command(payload):
            _LOGGER.info("-> %s", reply["msg"])
            client.publish(STATUS_TOPIC, json.dumps(reply), qos=1)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(os.environ.get("MQTT_HOST", "localhost"), 1883)
    client.loop_forever()


if __name__ == "__main__":
    main()
