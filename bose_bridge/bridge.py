#!/usr/bin/env python3
"""
Bose SoundTouch preset-to-radio bridge.

- Listens to the speaker's WebSocket. When a preset button is pressed,
  pushes the configured stream URL via UPnP SetAVTransportURI + Play
  with DIDL-Lite metadata so the station name and logo show up on the
  speaker.
- Looks up station name + favicon from radio-browser.info at startup
  (cached) for each configured URL.
- Connects to the Supervisor-provided MQTT broker and publishes Home
  Assistant MQTT-discovery configs so each preset appears as a
  `button.bose_preset_N` entity. Triggering the entity (UI / automation
  / script) plays the same preset over UPnP.
"""

import re
import threading
import time

import paho.mqtt.client as mqtt
import websocket

from bose_bridge.config import load_options
from bose_bridge.discovery import (
    discover_soundtouch_all,
    fetch_speaker_info,
    get_upnp_services,
)
from bose_bridge.helpers import (
    _clean_url,
    _parse_ws_preset_id,
    _ws_kind,
    apply_preset_meta_overrides,
    build_didl,
)
from bose_bridge.metadata import lookup_station
from bose_bridge.preset_sync import sync_presets
from bose_bridge.mqtt import fetch_mqtt_creds, MqttPublisher, publish_discovery


# ---------- config ---------------------------------------------------------

# ---------- Bose discovery -------------------------------------------------


# ---------- radio-browser.info ---------------------------------------------




# ---------- MQTT -----------------------------------------------------------


# ---------- main loop ------------------------------------------------------


class SpeakerBridge:
    def __init__(self, host: str, name_override: str | None, cfg: dict, sync_default: bool, publisher: MqttPublisher):
        self.host = host
        self.name_override = (name_override or "").strip() or None
        self.lock = threading.Lock()
        self.cfg = cfg
        self.publisher = publisher
        self.ws_connected = False
        self.last_preset: str | None = None
        self.last_preset_time: str | None = None
        self.last_error: str | None = None
        self._ws_debug_last_log: float = 0.0

        device_id, friendly, model = fetch_speaker_info(host)
        self.device_id = device_id
        self.friendly = self.name_override or friendly
        self.model = model

        print(f"[upnp] speaker: {self.friendly} ({self.model}) — id {self.device_id} @ {self.host}")

        self.presets: dict[int, dict] = {}
        for n in range(1, 7):
            url = _clean_url(cfg.get(f"preset_{n}_url"))
            if not url:
                continue
            meta = lookup_station(url)
            meta = apply_preset_meta_overrides(cfg, n, meta)
            self.presets[n] = {"url": url, **meta}
            print(f"[meta] {self.device_id} preset {n}: {url} -> {meta or '(no metadata found)'}")

        self.av, self.rc = get_upnp_services(host, self.device_id)

        sync = cfg.get("sync_presets_on_startup")
        if sync is None:
            sync = sync_default
        if sync:
            try:
                sync_presets(host, self.presets)
            except Exception as e:
                print(f"[sync] {self.device_id} failed: {e}")

        self.ws_thread: threading.Thread | None = None

    def _topic(self, suffix: str) -> str:
        return f"bose_bridge/{self.device_id}/{suffix}"

    def publish_state(self):
        self.publisher.publish(self._topic("ws"), ("online" if self.ws_connected else "offline"))
        if self.last_preset is not None:
            self.publisher.publish(self._topic("last_preset"), self.last_preset)
        if self.last_preset_time is not None:
            self.publisher.publish(self._topic("last_preset_time"), self.last_preset_time)
        if self.last_error is not None:
            self.publisher.publish(self._topic("last_error"), self.last_error)

    def play_preset(self, n: int, source: str):
        entry = self.presets.get(n)
        if not entry:
            print(f"[play] {self.device_id} preset {n} not configured ({source})")
            return
        url = _clean_url(entry["url"])
        didl = build_didl(url, entry)
        with self.lock:
            print(f"[play] {self.device_id} preset {n} -> {url} ({source})")
            try:
                try:
                    self.av.Stop(InstanceID=0)
                except Exception:
                    pass
                self.av.SetAVTransportURI(InstanceID=0, CurrentURI=url, CurrentURIMetaData=didl)
                self.av.Play(InstanceID=0, Speed="1")
                label = entry.get("name") or f"Preset {n}"
                self.last_preset = f"{n}: {label}"
                self.last_preset_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                self.last_error = ""
                self.publish_state()
            except Exception as e:
                print(f"[play] {self.device_id} failed: {e}")
                self.last_error = str(e)
                self.publish_state()

    def start_ws(self):
        if self.ws_thread:
            return
        t = threading.Thread(target=self._ws_loop, name=f"ws_{self.device_id}", daemon=True)
        t.start()
        self.ws_thread = t

    def _ws_loop(self):
        def on_message(_ws, msg):
            n = _parse_ws_preset_id(msg)
            if n is None:
                if "<updates" in msg and ("Updated" in msg or "<preset" in msg or "ContentItem" in msg):
                    now = time.time()
                    if now - self._ws_debug_last_log >= 15:
                        self._ws_debug_last_log = now
                        snippet = msg.strip().replace("\r", " ").replace("\n", " ")
                        if len(snippet) > 350:
                            snippet = snippet[:350] + "…"
                        kind = _ws_kind(msg)
                        print(f"[ws] {self.device_id} unparsed ws message ({kind}): {snippet}")
                return
            if n == 0:
                return
            print(f"[ws] {self.device_id} physical preset {n}")
            self.play_preset(n, "ws")

        def on_open(_ws):
            print(f"[ws] {self.device_id} connected to ws://{self.host}:8080")
            self.ws_connected = True
            self.publish_state()

        def on_error(_ws, e):
            print(f"[ws] {self.device_id} error: {e}")
            self.last_error = str(e)
            self.publish_state()

        def on_close(_ws, code, reason):
            print(f"[ws] {self.device_id} closed: {code} {reason}")
            self.ws_connected = False
            self.publish_state()

        while True:
            ws = websocket.WebSocketApp(
                f"ws://{self.host}:8080",
                subprotocols=["gabbo"],
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            ws.run_forever(ping_interval=30, ping_timeout=10)
            print(f"[ws] {self.device_id} reconnecting in 5s")
            time.sleep(5)


def main():
    cfg = load_options()
    speaker_cfgs = cfg.get("speakers") or []
    sync_default = bool(cfg.get("sync_presets_on_startup", True))
    publisher = MqttPublisher()

    entries: list[dict] = []
    if speaker_cfgs:
        for e in speaker_cfgs:
            if isinstance(e, dict):
                entries.append(e)
            else:
                entries.append({})
    else:
        entries.append(
            {
                "host": cfg.get("bose_host", ""),
                "sync_presets_on_startup": cfg.get("sync_presets_on_startup", True),
                "preset_1_url": cfg.get("preset_1_url", ""),
                "preset_2_url": cfg.get("preset_2_url", ""),
                "preset_3_url": cfg.get("preset_3_url", ""),
                "preset_4_url": cfg.get("preset_4_url", ""),
                "preset_5_url": cfg.get("preset_5_url", ""),
                "preset_6_url": cfg.get("preset_6_url", ""),
            }
        )

    specified = {(e.get("host") or "").strip() for e in entries if (e.get("host") or "").strip()}
    unresolved = [e for e in entries if not (e.get("host") or "").strip()]
    if unresolved:
        print(f"[cfg] {len(unresolved)} speaker(s) missing host — auto-discovering via SSDP...")
        discovered = [h for h in discover_soundtouch_all() if h not in specified]
        for e in unresolved:
            if discovered:
                e["host"] = discovered.pop(0)
        unresolved = [e for e in entries if not (e.get("host") or "").strip()]
        if unresolved:
            print(f"[cfg] could not auto-assign host for {len(unresolved)} speaker(s); they will be skipped")

    speakers: list[SpeakerBridge] = []
    for e in entries:
        host = (e.get("host") or "").strip()
        if not host:
            continue
        try:
            speakers.append(SpeakerBridge(host, e.get("name"), e, sync_default, publisher))
        except Exception as ex:
            print(f"[cfg] failed to init speaker @ {host}: {ex}")

    if not speakers:
        raise SystemExit("no SoundTouch speakers configured/found")

    for s in speakers:
        s.start_ws()

    creds = fetch_mqtt_creds()
    availability_topic = "bose_bridge/status"
    speakers_by_id = {s.device_id: s for s in speakers}
    if creds:
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="bose_bridge_multi",
        )
        if creds.get("username"):
            client.username_pw_set(creds["username"], creds.get("password", ""))
        client.will_set(availability_topic, "offline", qos=1, retain=True)

        def on_connect(c, _u, _f, rc, _p=None):
            print(f"[mqtt] connected (rc={rc})")
            publisher.set_client(c)
            for s in speakers:
                publish_discovery(c, s.device_id, s.friendly, s.model, s.presets, availability_topic)
                s.publish_state()
            c.publish(availability_topic, "online", qos=1, retain=True)
            c.subscribe("bose_bridge/+/preset/+/command")

        def on_message(_c, _u, msg):
            m = re.match(r"^bose_bridge/([^/]+)/preset/(\d+)/command$", msg.topic)
            if not m:
                return
            device_id = m.group(1)
            n = int(m.group(2))
            s = speakers_by_id.get(device_id)
            if not s:
                print(f"[mqtt] preset {n} requested for unknown device {device_id}")
                return
            s.play_preset(n, "mqtt")

        client.on_connect = on_connect
        client.on_message = on_message
        try:
            client.connect(creds["host"], int(creds.get("port", 1883)), keepalive=60)
            client.loop_start()
        except Exception as e:
            print(f"[mqtt] connect failed, continuing without HA control: {e}")
    else:
        print("[mqtt] no Supervisor MQTT credentials — HA buttons disabled")

    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
