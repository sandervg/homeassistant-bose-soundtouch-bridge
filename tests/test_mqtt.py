import io
import json
import os
import unittest
from unittest.mock import MagicMock, patch

import bose_bridge.mqtt as mqtt_module
from bose_bridge.mqtt import MqttPublisher, fetch_mqtt_creds, publish_discovery


class DummyResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestMqtt(unittest.TestCase):
    def test_fetch_mqtt_creds_from_env(self):
        env = {
            "MQTT_HOST": "mqtt.example.local",
            "MQTT_PORT": "1884",
            "MQTT_USERNAME": "user",
            "MQTT_PASSWORD": "pass",
        }
        with patch.dict(os.environ, env, clear=True), patch.object(mqtt_module, "SUPERVISOR_TOKEN", ""):
            creds = fetch_mqtt_creds()

        self.assertEqual(creds, {
            "host": "mqtt.example.local",
            "port": 1884,
            "username": "user",
            "password": "pass",
        })

    def test_fetch_mqtt_creds_returns_none_without_host(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(mqtt_module, "SUPERVISOR_TOKEN", ""):
            creds = fetch_mqtt_creds()

        self.assertIsNone(creds)

    def test_fetch_mqtt_creds_uses_supervisor(self):
        supervisor_data = {
            "data": {
                "host": "supervisor.local",
                "port": 1885,
                "username": "svc",
                "password": "secret",
            }
        }
        response = DummyResponse(json.dumps(supervisor_data).encode())

        with patch.object(mqtt_module, "SUPERVISOR_TOKEN", "token123"), patch.object(mqtt_module, "SUPERVISOR_URL", "http://supervisor"):
            with patch("bose_bridge.mqtt.urllib.request.urlopen", return_value=response):
                creds = fetch_mqtt_creds()

        self.assertEqual(creds, supervisor_data["data"])

    def test_mqtt_publisher_publish_without_client(self):
        publisher = MqttPublisher()
        publisher.publish("topic/test", "payload")  # no client should be safe

    def test_mqtt_publisher_publish_with_client(self):
        client = MagicMock()
        publisher = MqttPublisher()
        publisher.set_client(client)
        publisher.publish("topic/test", "payload", retain=False)

        client.publish.assert_called_once_with("topic/test", "payload", qos=1, retain=False)

    def test_publish_discovery_publishes_entities(self):
        client = MagicMock()
        device_id = "device123"
        friendly = "Bose Test"
        model = "SoundTouch 10"
        availability_topic = "bose/device123/availability"
        presets = {
            1: {"url": "http://stream.example/1", "name": "Station One"},
            2: {"url": "http://stream.example/2"},
        }

        publish_discovery(client, device_id, friendly, model, presets, availability_topic)

        self.assertEqual(client.publish.call_count, 10)
        expected_topics = {
            f"homeassistant/button/bose_{device_id}_preset_1/config",
            f"homeassistant/button/bose_{device_id}_preset_2/config",
            f"homeassistant/button/bose_{device_id}_preset_3/config",
            f"homeassistant/binary_sensor/bose_{device_id}_ws_connected/config",
            f"homeassistant/sensor/bose_{device_id}_last_preset/config",
            f"homeassistant/sensor/bose_{device_id}_last_preset_time/config",
        }
        actual_topics = {call.args[0] for call in client.publish.call_args_list}
        self.assertTrue(expected_topics.issubset(actual_topics))


if __name__ == "__main__":
    unittest.main()
