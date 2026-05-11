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
    }
    for n in range(1, 7):
        cfg[f"preset_{n}_url"] = os.environ.get(f"PRESET_{n}_URL", "").strip()
    return cfg


# ---------- Bose discovery -------------------------------------------------


def discover_soundtouch() -> str | None:
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
                return addr[0]
    except socket.timeout:
        return None
    finally:
        s.close()


def fetch_speaker_info(host: str) -> tuple[str, str, str]:
    """Return (device_id, friendly_name, model) by hitting /info."""
    with urllib.request.urlopen(f"http://{host}:8090/info", timeout=5) as r:
        info = r.read().decode()
    device_id = re.search(r'deviceID="([0-9A-F]+)"', info).group(1)
    name = re.search(r"<name>([^<]+)</name>", info)
    model = re.search(r"<type>([^<]+)</type>", info)
    return device_id, (name.group(1) if name else "SoundTouch"), (model.group(1) if model else "SoundTouch")


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

    saved_vol = int(rc.GetVolume(InstanceID=0, Channel="Master")["CurrentVolume"])
    rc.SetMute(InstanceID=0, Channel="Master", DesiredMute="1")
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
        rc.SetMute(InstanceID=0, Channel="Master", DesiredMute="0")
        print(f"[sync] unmuted, volume {saved_vol}")


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


def publish_discovery(client: mqtt.Client, device_id: str, friendly: str, model: str, presets: dict):
    """Publish Home Assistant MQTT-discovery configs for the 6 preset buttons."""
    device = {
        "identifiers": [f"bose_soundtouch_{device_id}"],
        "name": f"Bose {friendly}",
        "manufacturer": "Bose",
        "model": model,
    }
    cmd_base = f"bose_bridge/{device_id}/preset"
    for n in range(1, 7):
        meta = presets.get(n, {})
        url = meta.get("url", "")
        label = meta.get("name") or (f"Preset {n}" if not url else f"Preset {n}")
        unique = f"bose_{device_id}_preset_{n}"
        cfg = {
            "name": f"Preset {n}: {label}" if url else f"Preset {n}",
            "unique_id": unique,
            "object_id": unique,
            "command_topic": f"{cmd_base}/{n}/command",
            "icon": "mdi:radio",
            "device": device,
            "availability_topic": f"bose_bridge/{device_id}/status",
            "payload_available": "online",
            "payload_not_available": "offline",
        }
        topic = f"homeassistant/button/{unique}/config"
        client.publish(topic, json.dumps(cfg), qos=1, retain=True)
    print(f"[mqtt] published HA discovery for 6 buttons (device {device_id})")


# ---------- main loop ------------------------------------------------------


def main():
    cfg = load_options()
    host = (cfg.get("bose_host") or "").strip()
    if not host:
        print("[cfg] bose_host blank — auto-discovering via SSDP...")
        host = discover_soundtouch()
        if not host:
            raise SystemExit(
                "no SoundTouch found on the network. Set bose_host in the addon "
                "Configuration tab and restart."
            )
        print(f"[cfg] discovered SoundTouch at {host}")

    device_id, friendly, model = fetch_speaker_info(host)
    print(f"[upnp] speaker: {friendly} ({model}) — id {device_id}")

    presets = {}
    for n in range(1, 7):
        url = (cfg.get(f"preset_{n}_url") or "").strip()
        if not url:
            continue
        meta = lookup_station(url)
        presets[n] = {"url": url, **meta}
        print(f"[meta] preset {n}: {url} -> {meta or '(no metadata found)'}")

    av, rc = get_upnp_services(host, device_id)

    if cfg.get("sync_presets_on_startup", True):
        try:
            sync_presets(host, av, rc, presets)
        except Exception as e:
            print(f"[sync] failed: {e}")

    def play_preset(n: int):
        entry = presets.get(n)
        if not entry:
            print(f"[play] preset {n} not configured")
            return
        url = entry["url"]
        didl = build_didl(url, entry)
        print(f"[play] preset {n} -> {url}")
        try:
            try:
                av.Stop(InstanceID=0)
            except Exception:
                pass
            av.SetAVTransportURI(InstanceID=0, CurrentURI=url, CurrentURIMetaData=didl)
            av.Play(InstanceID=0, Speed="1")
        except Exception as e:
            print(f"[play] failed: {e}")

    # MQTT --------------------------------------------------------------
    mqtt_client = None
    creds = fetch_mqtt_creds()
    status_topic = f"bose_bridge/{device_id}/status"
    if creds:
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"bose_bridge_{device_id}",
        )
        if creds.get("username"):
            client.username_pw_set(creds["username"], creds.get("password", ""))
        client.will_set(status_topic, "offline", qos=1, retain=True)

        def on_connect(c, _u, _f, rc, _p=None):
            print(f"[mqtt] connected (rc={rc})")
            publish_discovery(c, device_id, friendly, model, presets)
            c.publish(status_topic, "online", qos=1, retain=True)
            c.subscribe(f"bose_bridge/{device_id}/preset/+/command")

        def on_message(_c, _u, msg):
            m = re.search(r"/preset/(\d+)/command$", msg.topic)
            if not m:
                return
            n = int(m.group(1))
            print(f"[mqtt] preset {n} requested via HA")
            play_preset(n)

        client.on_connect = on_connect
        client.on_message = on_message
        try:
            client.connect(creds["host"], int(creds.get("port", 1883)), keepalive=60)
            client.loop_start()
            mqtt_client = client
        except Exception as e:
            print(f"[mqtt] connect failed, continuing without HA control: {e}")
    else:
        print("[mqtt] no Supervisor MQTT credentials — HA buttons disabled")

    # WebSocket loop ----------------------------------------------------
    def on_message(_ws, msg):
        m = PRESET_RE.search(msg)
        if not m:
            return
        n = int(m.group(1))
        if n == 0:
            return
        print(f"[ws] physical preset {n} press")
        play_preset(n)

    def on_open(_ws):
        print(f"[ws] connected to ws://{host}:8080")

    def on_error(_ws, e):
        print(f"[ws] error: {e}")

    def on_close(_ws, code, reason):
        print(f"[ws] closed: {code} {reason}")

    while True:
        ws = websocket.WebSocketApp(
            f"ws://{host}:8080",
            subprotocols=["gabbo"],
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        ws.run_forever(ping_interval=30, ping_timeout=10)
        print("[ws] reconnecting in 5s")
        time.sleep(5)


if __name__ == "__main__":
    main()
