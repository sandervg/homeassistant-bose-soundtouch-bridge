from __future__ import annotations

import json
import os
import threading
import urllib.request

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover
    mqtt = None

from bose_bridge.constants import SUPERVISOR_TOKEN, SUPERVISOR_URL


def fetch_mqtt_creds(cfg: dict | None = None) -> dict | None:
    """Find MQTT broker credentials.

    Resolution order:
      1. Explicit broker in the add-on/standalone config (``mqtt_host`` etc.).
         Use this for external brokers like EMQX that aren't wired into the
         Supervisor's MQTT service.
      2. The Supervisor's MQTT service (Mosquitto add-on + MQTT integration).
      3. ``MQTT_*`` environment variables (standalone Docker).
    """
    # 1. Explicit config takes precedence.
    if cfg:
        host = str(cfg.get("mqtt_host") or "").strip()
        if host:
            print(f"[mqtt] using broker from config: {host}")
            return {
                "host": host,
                "port": int(cfg.get("mqtt_port") or 1883),
                "username": str(cfg.get("mqtt_username") or ""),
                "password": str(cfg.get("mqtt_password") or ""),
            }

    # 2. Supervisor-provided broker.
    if SUPERVISOR_TOKEN:
        try:
            req = urllib.request.Request(
                f"{SUPERVISOR_URL}/services/mqtt",
                headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"},
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.load(r).get("data")
        except Exception as e:
            print(f"[mqtt] supervisor MQTT lookup failed: {e}")

    # 3. Environment variables (standalone Docker).
    host = os.environ.get("MQTT_HOST", "").strip()
    if not host:
        return None
    return {
        "host": host,
        "port": int(os.environ.get("MQTT_PORT", "1883")),
        "username": os.environ.get("MQTT_USERNAME", ""),
        "password": os.environ.get("MQTT_PASSWORD", ""),
    }


class MqttPublisher:
    def __init__(self):
        self._lock = threading.Lock()
        self._client: mqtt.Client | None = None

    def set_client(self, client: mqtt.Client | None):
        with self._lock:
            self._client = client

    def publish(self, topic: str, payload: str, retain: bool = True):
        with self._lock:
            client = self._client
        if not client:
            return
        client.publish(topic, payload, qos=1, retain=retain)


def publish_discovery(
    client: mqtt.Client,
    device_id: str,
    friendly: str,
    model: str,
    presets: dict,
    availability_topic: str,
):
    device = {
        "identifiers": [f"bose_soundtouch_{device_id}"],
        "name": friendly,
        "manufacturer": "Bose",
        "model": model,
    }
    cmd_base = f"bose_bridge/{device_id}/preset"
    for n in range(1, 7):
        meta = presets.get(n, {})
        url = meta.get("url", "")
        label = meta.get("name") or f"Preset {n}"
        unique = f"bose_{device_id}_preset_{n}"
        cfg = {
            "name": f"Preset {n}: {label}" if url else f"Preset {n}",
            "unique_id": unique,
            "object_id": unique,
            "command_topic": f"{cmd_base}/{n}/command",
            "icon": "mdi:radio",
            "device": device,
            "availability_topic": availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
        }
        topic = f"homeassistant/button/{unique}/config"
        client.publish(topic, json.dumps(cfg), qos=1, retain=True)

    base = f"bose_bridge/{device_id}"

    ws_unique = f"bose_{device_id}_ws_connected"
    ws_cfg = {
        "name": "WebSocket",
        "unique_id": ws_unique,
        "object_id": ws_unique,
        "state_topic": f"{base}/ws",
        "payload_on": "online",
        "payload_off": "offline",
        "device_class": "connectivity",
        "device": device,
        "availability_topic": availability_topic,
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    client.publish(f"homeassistant/binary_sensor/{ws_unique}/config", json.dumps(ws_cfg), qos=1, retain=True)

    last_preset_unique = f"bose_{device_id}_last_preset"
    last_preset_cfg = {
        "name": "Last Preset",
        "unique_id": last_preset_unique,
        "object_id": last_preset_unique,
        "state_topic": f"{base}/last_preset",
        "icon": "mdi:gesture-tap-button",
        "device": device,
        "availability_topic": availability_topic,
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    client.publish(f"homeassistant/sensor/{last_preset_unique}/config", json.dumps(last_preset_cfg), qos=1, retain=True)

    last_time_unique = f"bose_{device_id}_last_preset_time"
    last_time_cfg = {
        "name": "Last Preset Time",
        "unique_id": last_time_unique,
        "object_id": last_time_unique,
        "state_topic": f"{base}/last_preset_time",
        "device_class": "timestamp",
        "device": device,
        "availability_topic": availability_topic,
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    client.publish(f"homeassistant/sensor/{last_time_unique}/config", json.dumps(last_time_cfg), qos=1, retain=True)

    last_error_unique = f"bose_{device_id}_last_error"
    last_error_cfg = {
        "name": "Last Error",
        "unique_id": last_error_unique,
        "object_id": last_error_unique,
        "state_topic": f"{base}/last_error",
        "icon": "mdi:alert-circle-outline",
        "device": device,
        "availability_topic": availability_topic,
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    client.publish(f"homeassistant/sensor/{last_error_unique}/config", json.dumps(last_error_cfg), qos=1, retain=True)

    print(f"[mqtt] published HA discovery (buttons + sensors) for device {device_id}")
