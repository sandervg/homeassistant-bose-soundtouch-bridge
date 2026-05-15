import re
import socket
import time
import urllib.request
import xml.etree.ElementTree as _ET

try:
    import upnpclient
except ImportError:  # pragma: no cover
    upnpclient = None

from bose_bridge.helpers import _find_first_text, _parse_xml


def _retry(max_attempts: int = 3, backoff_sec: float = 1.0):
    """Decorator for retrying operations with exponential backoff."""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    wait = backoff_sec * (2 ** attempt)
                    print(f"[retry] {fn.__name__} attempt {attempt + 1} failed: {e}; retrying in {wait}s")
                    time.sleep(wait)
        return wrapper
    return decorator

SSDP_ADDR = ("239.255.255.250", 1900)
SSDP_TARGET = "urn:schemas-upnp-org:device:MediaRenderer:1"


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
    try:
        s.sendto(msg, SSDP_ADDR)
    except Exception:
        s.close()
        return []

    found: set[str] = set()
    try:
        while True:
            data, addr = s.recvfrom(2048)
            text = data.decode(errors="ignore")
            loc = next(
                (
                    l.split(": ", 1)[1].strip()
                    for l in text.split("\r\n")
                    if l.lower().startswith("location:")
                ),
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


@_retry(max_attempts=3, backoff_sec=0.5)
def fetch_speaker_info(host: str) -> tuple[str, str, str]:
    """Return (device_id, friendly_name, model) by hitting /info with retry."""
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
    if upnpclient is None:
        raise ImportError("upnpclient is required for UPnP service discovery")
    desc_url = f"http://{host}:8091/XD/BO5EBO5E-F00D-F00D-FEED-{device_id}.xml"
    print(f"[upnp] description: {desc_url}")
    d = upnpclient.Device(desc_url)
    av = next(s for s in d.services if "AVTransport" in s.service_id)
    rc = next(s for s in d.services if "RenderingControl" in s.service_id)
    return av, rc
