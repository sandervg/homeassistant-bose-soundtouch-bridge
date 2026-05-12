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

import html
import json
import os
import re
import socket
import threading
import time
import urllib.parse
import urllib.request

import paho.mqtt.client as mqtt
import upnpclient
import websocket

import xml.etree.ElementTree as _ET

OPTIONS_PATH = "/data/options.json"
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN")
SUPERVISOR_URL = "http://supervisor"
RADIO_BROWSER_BASES = [
    "https://de1.api.radio-browser.info",
    "https://nl1.api.radio-browser.info",
    "https://at1.api.radio-browser.info",
]
PRESET_RE = re.compile(r'<nowSelectionUpdated>\s*<preset id="(\d+)"')
SSDP_ADDR = ("239.255.255.250", 1900)
SSDP_TARGET = "urn:schemas-upnp-org:device:MediaRenderer:1"


# ---------- config ---------------------------------------------------------

def _parse_xml(text: str) -> _ET.Element | None:
    try:
        return _ET.fromstring(text.strip())
    except Exception:
        return None


def _find_first_text(root: _ET.Element, local_tag: str) -> str | None:
    for el in root.iter():
        if el.tag.split("}")[-1] == local_tag and el.text:
            return el.text
    return None


def _coerce_bool01(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return "1"
    if s in ("0", "false", "no", "off"):
        return "0"
    return None


def _parse_ws_preset_id(msg: str) -> int | None:
    root = _parse_xml(msg)
    if root is not None:
        preset_el = next(
            (e for e in root.iter() if e.tag.split("}")[-1] == "preset" and e.get("id")),
            None,
        )
        if preset_el is not None:
            try:
                return int(preset_el.get("id"))
            except Exception:
                return None
    m = PRESET_RE.search(msg)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None



def load_options() -> dict:
    """Read config. In Supervisor (HAOS / Supervised) the add-on options arrive
    as JSON at /data/options.json. In standalone Docker (HA Container, plain
    Docker, NAS, etc.) they come from environment variables."""
    if os.path.exists(OPTIONS_PATH):
        with open(OPTIONS_PATH) as f:
            return json.load(f)
    print("[cfg] /data/options.json not found — reading config from environment")
    cfg: dict = {
        "bose_host": os.environ.get("BOSE_HOST", "").strip(),
        "sync_presets_on_startup":
            os.environ.get("SYNC_PRESETS_ON_STARTUP", "true").lower() in ("1", "true", "yes", "on"),
        "speakers": [],
    }
    for n in range(1, 7):
        cfg[f"preset_{n}_url"] = os.environ.get(f"PRESET_{n}_URL", "").strip()
        cfg[f"preset_{n}_name"] = os.environ.get(f"PRESET_{n}_NAME", "").strip()
        cfg[f"preset_{n}_favicon"] = os.environ.get(f"PRESET_{n}_FAVICON", "").strip()
        cfg[f"preset_{n}_use_icy"] = os.environ.get(f"PRESET_{n}_USE_ICY", "").strip().lower() in ("1", "true", "yes", "on")
    speakers_json = os.environ.get("SPEAKERS_JSON", "").strip()
    if speakers_json:
        try:
            parsed = json.loads(speakers_json)
            if isinstance(parsed, list):
                cfg["speakers"] = parsed
            else:
                print("[cfg] SPEAKERS_JSON is not a list — ignoring")
        except Exception as e:
            print(f"[cfg] failed to parse SPEAKERS_JSON: {e}")
    return cfg


# ---------- Bose discovery -------------------------------------------------


def discover_soundtouch_all() -> list[str]:
    msg = (
        "M-SEARCH * HTTP/1.1\r\n"
        f"HOST: {SSDP_ADDR[0]}:{SSDP_ADDR[1]}\r\n"
        'MAN: "ssdp:discover"\r\n'
        "MX: 2\r\n"
        f"ST: {SSDP_TARGET}\r\n\r\n"
    ).encode()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(3)
    s.sendto(msg, SSDP_ADDR)
    found: set[str] = set()
    try:
        while True:
            data, addr = s.recvfrom(2048)
            text = data.decode(errors="ignore")
            loc = next(
                (l.split(": ", 1)[1].strip() for l in text.split("\r\n") if l.lower().startswith("location:")),
                None,
            )
            if not loc:
                continue
            try:
                desc = urllib.request.urlopen(loc, timeout=3).read().decode()
            except Exception:
                continue
            if "SoundTouch" in desc or "Bose" in desc:
                found.add(addr[0])
    except socket.timeout:
        return sorted(found)
    finally:
        s.close()


def discover_soundtouch() -> str | None:
    hosts = discover_soundtouch_all()
    return hosts[0] if hosts else None


def fetch_speaker_info(host: str) -> tuple[str, str, str]:
    """Return (device_id, friendly_name, model) by hitting /info."""
    with urllib.request.urlopen(f"http://{host}:8090/info", timeout=5) as r:
        info = r.read().decode()
    device_id = None
    friendly = "SoundTouch"
    model = "SoundTouch"

    root = _parse_xml(info)
    if root is not None:
        device_id = root.attrib.get("deviceID") or None
        friendly = _find_first_text(root, "name") or friendly
        model = _find_first_text(root, "type") or model

    if not device_id:
        m = re.search(r'deviceID="([0-9A-F]+)"', info)
        device_id = m.group(1) if m else None

    if not device_id:
        raise ValueError("unable to parse deviceID from /info response")

    return device_id, friendly, model


def get_upnp_services(host: str, device_id: str):
    """Return (av_transport, rendering_control) for the given speaker."""
    desc_url = f"http://{host}:8091/XD/BO5EBO5E-F00D-F00D-FEED-{device_id}.xml"
    print(f"[upnp] description: {desc_url}")
    d = upnpclient.Device(desc_url)
    av = next(s for s in d.services if "AVTransport" in s.service_id)
    rc = next(s for s in d.services if "RenderingControl" in s.service_id)
    return av, rc


# ---------- radio-browser.info ---------------------------------------------


def lookup_station(url: str) -> dict:
    """Return {'name': str, 'favicon': str} or empty dict if not found."""
    body = urllib.parse.urlencode({"url": url}).encode()
    for base in RADIO_BROWSER_BASES:
        try:
            req = urllib.request.Request(
                f"{base}/json/stations/byurl",
                data=body,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "homeassistant-bose-soundtouch-bridge/1.3.0",
                },
            )
            with urllib.request.urlopen(req, timeout=4) as r:
                stations = json.load(r)
            if stations:
                s = stations[0]
                return {"name": s.get("name", ""), "favicon": s.get("favicon", "")}
            return {}
        except Exception as e:
            print(f"[meta] {base} failed: {e}")
            continue
    return {}


def build_didl(url: str, meta: dict) -> str:
    title = html.escape(meta.get("name") or "Internet Radio")
    art = html.escape(meta.get("favicon") or "")
    art_tag = f"<upnp:albumArtURI>{art}</upnp:albumArtURI>" if art else ""
    return (
        '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
        '<item id="0" parentID="-1" restricted="1">'
        f"<dc:title>{title}</dc:title>"
        "<upnp:class>object.item.audioItem.audioBroadcast</upnp:class>"
        f"{art_tag}"
        f'<res protocolInfo="http-get:*:audio/mpeg:*">{html.escape(url)}</res>'
        "</item></DIDL-Lite>"
    )


def apply_preset_meta_overrides(cfg: dict, n: int, meta: dict) -> dict:
    name = (cfg.get(f"preset_{n}_name") or "").strip()
    if name:
        meta["name"] = name
    favicon = (cfg.get(f"preset_{n}_favicon") or "").strip()
    if favicon:
        meta["favicon"] = favicon
    return meta


# ---------- preset sync ----------------------------------------------------


def _key(host: str, state: str, key: str):
    """POST a key event to the SoundTouch /key endpoint."""
    body = f'<key state="{state}" sender="Gabbo">{key}</key>'.encode()
    req = urllib.request.Request(
        f"http://{host}:8090/key",
        data=body,
        headers={"Content-Type": "application/xml"},
    )
    try:
        urllib.request.urlopen(req, timeout=5).read()
    except Exception:
        pass  # release_after_hold returns an XML-parse error but still saves


def _current_preset_url(host: str, n: int) -> str | None:
    try:
        with urllib.request.urlopen(f"http://{host}:8090/presets", timeout=5) as r:
            xml = r.read().decode()
    except Exception:
        return None
    root = _parse_xml(xml)
    if root is not None:
        preset_el = next(
            (p for p in root.iter() if p.tag.split("}")[-1] == "preset" and p.get("id") == str(n)),
            None,
        )
        if preset_el is None:
            return None
        content_el = next(
            (e for e in preset_el.iter() if e.tag.split("}")[-1].lower() == "contentitem" and e.get("location")),
            None,
        )
        if content_el is not None:
            return content_el.get("location")

    m = re.search(rf'<preset id="{n}"[^>]*>(.*?)</preset>', xml, re.DOTALL)
    if not m:
        return None
    loc = re.search(r'location="([^"]+)"', m.group(1))
    return loc.group(1) if loc else None


def sync_presets(host: str, av, rc, presets: dict):
    """Save each configured preset onto the speaker so physical button presses
    fire the WebSocket event the bridge listens for. Skips slots already in
    the right state. Mutes during the operation to hide audio blips."""
    targets = {n: e["url"] for n, e in presets.items() if e.get("url")}
    needed = {n: u for n, u in targets.items() if _current_preset_url(host, n) != u}
    if not needed:
        print("[sync] all configured presets already match the device — skipping")
        return
    print(f"[sync] {len(needed)}/{len(targets)} presets need writing: {sorted(needed)}")

    saved_vol = None
    saved_mute = None
    try:
        saved_vol = int(rc.GetVolume(InstanceID=0, Channel="Master")["CurrentVolume"])
    except Exception:
        pass
    try:
        saved_mute = _coerce_bool01(rc.GetMute(InstanceID=0, Channel="Master")["CurrentMute"])
    except Exception:
        pass

    did_mute = False
    try:
        if saved_mute != "1":
            rc.SetMute(InstanceID=0, Channel="Master", DesiredMute="1")
            did_mute = True
    except Exception:
        pass
    try:
        for n, url in needed.items():
            try:
                av.Stop(InstanceID=0)
            except Exception:
                pass
            time.sleep(0.4)
            # IMPORTANT: empty CurrentURIMetaData. With DIDL, the speaker
            # marks the now-playing item as isPresetable="false" and silently
            # ignores the long-press save. The bridge applies DIDL at runtime.
            av.SetAVTransportURI(InstanceID=0, CurrentURI=url, CurrentURIMetaData="")
            av.Play(InstanceID=0, Speed="1")
            time.sleep(3.5)
            _key(host, "press", f"PRESET_{n}")
            time.sleep(0.8)
            _key(host, "release_after_hold", f"PRESET_{n}")
            time.sleep(2.0)
            stored = _current_preset_url(host, n)
            if stored == url:
                print(f"[sync]  ✓ preset {n} -> {url}")
            else:
                print(f"[sync]  ✗ preset {n} did not stick (now: {stored})")
        try:
            av.Stop(InstanceID=0)
        except Exception:
            pass
    finally:
        if did_mute:
            try:
                rc.SetMute(InstanceID=0, Channel="Master", DesiredMute=(saved_mute or "0"))
            except Exception:
                pass
        if saved_vol is not None:
            try:
                rc.SetVolume(InstanceID=0, Channel="Master", DesiredVolume=str(saved_vol))
            except Exception:
                pass
        print(f"[sync] restored audio state (mute={saved_mute}, volume={saved_vol})")


# ---------- MQTT -----------------------------------------------------------


def fetch_mqtt_creds() -> dict | None:
    """Find MQTT broker credentials.
    In Supervisor: ask the Supervisor's `/services/mqtt` endpoint (auto-wired
    when the user has the MQTT integration configured in HA Core).
    Standalone: read from MQTT_HOST / MQTT_PORT / MQTT_USERNAME / MQTT_PASSWORD
    environment variables. Returns None if neither is available."""
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
            # fall through to env vars below
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
    """Publish Home Assistant MQTT-discovery configs for the 6 preset buttons + sensors."""
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

        device_id, friendly, model = fetch_speaker_info(host)
        self.device_id = device_id
        self.friendly = self.name_override or friendly
        self.model = model

        print(f"[upnp] speaker: {self.friendly} ({self.model}) — id {self.device_id} @ {self.host}")

        self.presets: dict[int, dict] = {}
        for n in range(1, 7):
            url = (cfg.get(f"preset_{n}_url") or "").strip()
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
                sync_presets(host, self.av, self.rc, self.presets)
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
        url = entry["url"]
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
            if not n:
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
