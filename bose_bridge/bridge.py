import json
import threading
import time
from datetime import datetime

try:
    import websocket
except ImportError:
    websocket = None

from bose_bridge.config import get_version, load_options
from bose_bridge.constants import *
from bose_bridge.discovery import (
    discover_soundtouch_all,
    fetch_speaker_info,
    get_upnp_services,
)
from bose_bridge.helpers import (
    _parse_ws_preset_id,
    apply_preset_meta_overrides,
    build_didl,
)
from bose_bridge.metadata import lookup_station
from bose_bridge.mqtt import MqttPublisher, fetch_mqtt_creds, publish_discovery
from bose_bridge.preset_sync import sync_presets


class SpeakerBridge:
    def __init__(self, host: str, config: dict, mqtt_pub: MqttPublisher):
        self.host = host
        self.config = config
        self.mqtt_pub = mqtt_pub
        self.device_id = None
        self.friendly = "SoundTouch"
        self.model = "SoundTouch"
        self.av = None
        self.rc = None
        self.presets = {}
        self.ws = None
        self.active = True

    def _get_preset_map(self) -> dict:
        """Build a map of preset_id -> {url, name, favicon} for this speaker."""
        res = {}
        for n in range(1, 7):
            url = self.config.get(f"preset_{n}_url")
            if url:
                res[n] = {
                    "url": url,
                    "name": self.config.get(f"preset_{n}_name"),
                    "favicon": self.config.get(f"preset_{n}_favicon"),
                }
        return res

    def _update_ha_status(self, key: str, value: str):
        if not self.device_id:
            return
        topic = f"bose_bridge/{self.device_id}/{key}"
        self.mqtt_pub.publish(topic, value)

    def _play_preset(self, n: int):
        try:
            # 1. Always report to HA first (allows using presets as generic triggers)
            print(f"[{self.host}] reporting preset {n} to Home Assistant")
            self._update_ha_status("last_preset", str(n))
            self._update_ha_status("last_preset_time", datetime.now().isoformat())

            # 2. Check if we have a URL to play ourselves
            if n not in self.presets:
                print(f"[{self.host}] no local URL for preset {n} — HA automation should handle this")
                return

            entry = self.presets[n]
            url = entry["url"]
            
            print(f"[{self.host}] playing local preset {n}: {url}")

            # Fetch metadata
            meta = lookup_station(url)
            meta = apply_preset_meta_overrides(self.config, n, meta)
            didl = build_didl(url, meta)

            # UPnP Playback
            if self.av:
                self.av.Stop(InstanceID=0)
                self.av.SetAVTransportURI(InstanceID=0, CurrentURI=url, CurrentURIMetaData=didl)
                self.av.Play(InstanceID=0, Speed="1")
                print(f"[{self.host}] UPnP play command sent")
        except BoseError as e:
            print(f"[{self.host}] {e}")
        except Exception as e:
            err = f"play error: {e}"
            print(f"[{self.host}] {err}")
            self._update_ha_status("last_error", err)

    def _on_message(self, ws, message):
        # print(f"[{self.host}] ws: {message}")
        preset_id = _parse_ws_preset_id(message)
        if preset_id:
            print(f"[{self.host}] physical preset button {preset_id} detected")
            self._play_preset(preset_id)

    def _on_error(self, ws, error):
        print(f"[{self.host}] ws error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        print(f"[{self.host}] ws closed")
        self._update_ha_status("ws", "offline")

    def _on_open(self, ws):
        print(f"[{self.host}] ws connected")
        self._update_ha_status("ws", "online")

    def run(self):
        print(f"[{self.host}] starting bridge thread")
        
        # 1. Info & UPnP Setup
        try:
            self.device_id, self.friendly, self.model = fetch_speaker_info(self.host)
            print(f"[{self.host}] device: {self.friendly} ({self.model}, ID: {self.device_id})")
            self.av, self.rc = get_upnp_services(self.host, self.device_id)
        except Exception as e:
            print(f"[{self.host}] failed to initialize UPnP/info: {e}")
            return

        # 2. Preset Sync
        self.presets = self._get_preset_map()
        if self.config.get("sync_presets_on_startup", True):
            sync_presets(self.host, self.presets)

        # 3. MQTT Discovery
        availability_topic = f"bose_bridge/{self.device_id}/availability"
        self.mqtt_pub.publish(availability_topic, "online")
        
        # We need the actual client to publish discovery
        # This is a bit tricky with MqttPublisher abstraction
        # For now, we assume the publisher's client is set
        # In a real app, we might wait for it.
        
        # 4. WebSocket Loop
        ws_url = f"ws://{self.host}:8080"
        while self.active:
            try:
                self.ws = websocket.WebSocketApp(
                    ws_url,
                    subprotocols=["gabbo"],
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self.ws.run_forever(ping_interval=10, ping_timeout=5)
            except Exception as e:
                print(f"[{self.host}] ws loop crashed: {e}")
            
            if self.active:
                print(f"[{self.host}] ws reconnecting in 5s...")
                time.sleep(5)


def main():
    print(f"--- Bose SoundTouch Bridge (v{get_version()}) ---")
    cfg = load_options()
    
    # Speaker Instances
    speaker_instances: dict[str, SpeakerBridge] = {}
    
    # MQTT Setup
    mqtt_pub = MqttPublisher()
    creds = fetch_mqtt_creds()
    if creds and websocket:
        import paho.mqtt.client as mqtt
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if creds.get("username"):
            client.username_pw_set(creds["username"], creds["password"])
        
        def on_connect(client, userdata, flags, rc, properties=None):
            print(f"[mqtt] connected to {creds['host']}")
            mqtt_pub.set_client(client)
            # Subscribe to all bridge commands
            client.subscribe("bose_bridge/+/preset/+/command")

        def on_message(client, userdata, msg):
            # Topic: bose_bridge/<device_id>/preset/<n>/command
            parts = msg.topic.split("/")
            if len(parts) == 5 and parts[0] == "bose_bridge" and parts[2] == "preset":
                dev_id = parts[1]
                try:
                    p_id = int(parts[3])
                    # Find speaker instance by device_id
                    for sb in speaker_instances.values():
                        if sb.device_id == dev_id:
                            sb._play_preset(p_id)
                            break
                except Exception: pass

        client.on_connect = on_connect
        client.on_message = on_message
        
        # Start MQTT thread
        def mqtt_thread():
            try:
                client.connect(creds["host"], creds["port"], 60)
                client.loop_forever()
            except Exception as e:
                print(f"[mqtt] loop failed: {e}")
        
        threading.Thread(target=mqtt_thread, daemon=True).start()
    else:
        print("[mqtt] broker not configured or paho-mqtt missing — MQTT features disabled")

    # Speaker Discovery
    hosts = []
    if cfg.get("bose_host"):
        hosts.append(cfg["bose_host"])
    
    if cfg.get("speakers"):
        for s in cfg["speakers"]:
            if s.get("host") and s["host"] not in hosts:
                hosts.append(s["host"])
    
    if not hosts:
        print("[disco] no hosts in config — searching via SSDP...")
        hosts = discover_soundtouch_all()
        if not hosts:
            print("[disco] no speakers found. Please configure bose_host.")
            return

    print(f"[main] managing {len(hosts)} speakers: {hosts}")

    # Start Speaker Threads
    for host in hosts:
        # Merge root config with speaker-specific overrides if any
        speaker_cfg = cfg.copy()
        if cfg.get("speakers"):
            override = next((s for s in cfg["speakers"] if s.get("host") == host), None)
            if override:
                speaker_cfg.update(override)
        
        sb = SpeakerBridge(host, speaker_cfg, mqtt_pub)
        speaker_instances[host] = sb
        
        def run_with_discovery(bridge_obj):
            # Wait for MQTT to connect and discovery
            for _ in range(10):
                if mqtt_pub._client:
                    try:
                        dev_id, friendly, model = fetch_speaker_info(bridge_obj.host)
                        bridge_obj.device_id = dev_id # Set it here for MQTT lookup
                        publish_discovery(
                            mqtt_pub._client,
                            dev_id,
                            friendly,
                            model,
                            bridge_obj.presets,
                            f"bose_bridge/{dev_id}/availability"
                        )
                    except Exception: pass
                    break
                time.sleep(1)
            
            bridge_obj.run()

        threading.Thread(target=run_with_discovery, args=(sb,), daemon=True).start()

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("[main] shutting down...")


if __name__ == "__main__":
    main()
