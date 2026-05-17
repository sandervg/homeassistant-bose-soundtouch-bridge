import re
import sys
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

AVT_SERVICE = "urn:schemas-upnp-org:service:AVTransport:1"


def clean_url(s: str) -> str:
    s = (s or "").strip().replace("`", "").strip()
    if len(s) >= 2 and s[0] in ("'", '"') and s[-1] == s[0]:
        s = s[1:-1].strip()
    return s.strip()


def normalize_url(s: str) -> str:
    return clean_url(s).rstrip("/")


def soap(host: str, action: str, body_xml: str) -> str:
    envelope = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
        's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
        "<s:Body>"
        f'<u:{action} xmlns:u="{AVT_SERVICE}">'
        f"{body_xml}"
        f"</u:{action}>"
        "</s:Body>"
        "</s:Envelope>"
    ).encode("utf-8")

    req = urllib.request.Request(
        f"http://{host}:8091/AVTransport/Control",
        data=envelope,
        headers={
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPACTION": f'"{AVT_SERVICE}#{action}"',
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.read().decode(errors="ignore")


def post_xml(host: str, path: str, xml: str) -> str:
    req = urllib.request.Request(
        f"http://{host}:8090{path}",
        data=xml.encode("utf-8"),
        headers={"Content-Type": "application/xml"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.read().decode(errors="ignore")
    except urllib.error.HTTPError as e:
        try:
            return e.read().decode(errors="ignore")
        except Exception:
            return str(e)


def store_preset(host: str, n: int, url: str, name: str):
    url = normalize_url(url)
    name = (name or "").strip()
    if not url:
        return

    content_item = (
        f'<ContentItem source="UPNP" location="{url}" sourceAccount="UPnPUserName" isPresetable="true">'
        f"<itemName>{name}</itemName>"
        "</ContentItem>"
    )
    xml = f'<?xml version="1.0" encoding="UTF-8" ?><preset id="{n}">{content_item}</preset>'
    resp = post_xml(host, "/storePreset", xml)
    if "<errors" not in resp.lower():
        return

    content_item = f'<ContentItem source="UPNP" location="{url}" sourceAccount="UPnPUserName" isPresetable="true" />'
    xml = f'<?xml version="1.0" encoding="UTF-8" ?><preset id="{n}">{content_item}</preset>'
    resp = post_xml(host, "/storePreset", xml)
    if "<errors" in resp.lower():
        raise RuntimeError(resp.strip() or "storePreset failed")


def key(host: str, state: str, key_name: str) -> str:
    last_text = ""
    for sender in ("Gabbo", "SoundTouchApp"):
        body = f'<key state="{state}" sender="{sender}">{key_name}</key>'.encode("utf-8")
        req = urllib.request.Request(
            f"http://{host}:8090/key",
            data=body,
            headers={"Content-Type": "application/xml"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                text = r.read().decode(errors="ignore")
            last_text = text
            if "WEBSOCKET_API_NOT_REGISTERED" in text:
                continue
            if "<errors" in text:
                continue
            return text
        except Exception:
            continue
    raise RuntimeError(f"POST /key failed: {last_text or '(no response)'}")


def hold_key(host: str, key_name: str, hold_s: float = 1.2):
    key(host, "press", key_name)
    time.sleep(hold_s)
    try:
        key(host, "release_after_hold", key_name)
    except Exception:
        key(host, "release", key_name)


def get_preset_location(host: str, n: int) -> str | None:
    try:
        with urllib.request.urlopen(f"http://{host}:8090/presets", timeout=5) as r:
            xml = r.read().decode(errors="ignore")
    except Exception:
        return None
    try:
        root = ET.fromstring(xml)
    except Exception:
        m = re.search(rf'<preset id="{n}"[^>]*>.*?location="([^"]+)"', xml, re.DOTALL)
        return m.group(1) if m else None
    preset_el = next((p for p in root.iter() if p.tag.split("}")[-1] == "preset" and p.get("id") == str(n)), None)
    if preset_el is None:
        return None
    content_el = next((e for e in preset_el.iter() if e.tag.split("}")[-1].lower() == "contentitem"), None)
    return content_el.get("location") if content_el is not None else None


def save_preset(host: str, n: int, url: str):
    url = normalize_url(url)
    if not url:
        return
    stored_before = get_preset_location(host, n)
    if stored_before and normalize_url(stored_before) == url:
        print(f"preset {n}: ok ({stored_before})")
        return

    try:
        soap(host, "Stop", "<InstanceID>0</InstanceID>")
    except Exception:
        pass

    meta = ""
    soap(
        host,
        "SetAVTransportURI",
        f"<InstanceID>0</InstanceID><CurrentURI>{url}</CurrentURI><CurrentURIMetaData>{meta}</CurrentURIMetaData>",
    )
    soap(host, "Play", "<InstanceID>0</InstanceID><Speed>1</Speed>")

    time.sleep(1.5)
    try:
        store_preset(host, n, url, f"Preset {n}")
        stored = get_preset_location(host, n)
        print(f"preset {n}: {stored}")
        return
    except Exception:
        pass

    time.sleep(2.0)
    try:
        hold_key(host, f"PRESET_{n}", hold_s=1.2)
    except Exception as e:
        print(f"preset {n}: auto-save failed ({e})")
        input(f"Long-press PRESET {n} on the speaker now, then press Enter...")
    time.sleep(2.0)

    stored = get_preset_location(host, n)
    print(f"preset {n}: {stored}")


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: python set_presets.py <speaker_ip>")

    host = sys.argv[1].strip()
    presets = {
        1: "http://live.r357.eu",
        2: "http://stream3.polskieradio.pl:8904",
        3: "http://zet090-02.cdn.eurozet.pl:8404",
        4: "http://195.150.20.242:8000/rmf_fm",
        5: "http://25693.live.streamtheworld.com/CHILLIAAC.aac?dist=mytuner",
        6: "http://stream3.polskieradio.pl:8900",
    }

    for n in range(1, 7):
        save_preset(host, n, presets.get(n, ""))


if __name__ == "__main__":
    main()
