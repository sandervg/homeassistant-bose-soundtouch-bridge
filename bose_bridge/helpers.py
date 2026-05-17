from bose_bridge.constants import *
import re
import xml.etree.ElementTree as ET
import urllib.request
import time

_mime_cache = {}

def _clean_url(url: str | None) -> str:
    """Clean and validate a URL (strips quotes, backticks, and whitespace)."""
    if not url:
        return ""
    if not isinstance(url, str):
        url = str(url)
    url = url.strip()
    url = re.sub(r"[\"'\`]+", "", url)
    url = url.strip()
    if url and not url.startswith("http://") and not url.startswith("https://"):
        url = "http://" + url
    return url

# Alias for backward compatibility
clean_url = _clean_url

def _sanitize_cfg_urls(cfg: dict):
    """Sanitize all preset URLs in the config."""
    for n in range(1, 7):
        key = f"preset_{n}_url"
        if key in cfg:
            cfg[key] = _clean_url(cfg[key])
    
    if "speakers" in cfg and isinstance(cfg["speakers"], list):
        for s in cfg["speakers"]:
            for n in range(1, 7):
                k = f"preset_{n}_url"
                if k in s:
                    s[k] = _clean_url(s[k])

def _parse_xml(xml_str: str) -> ET.Element | None:
    """Safely parse XML string."""
    if not xml_str:
        return None
    try:
        return ET.fromstring(xml_str)
    except Exception:
        return None

def _find_first_text(root: ET.Element, tag: str) -> str | None:
    """Find the text content of the first element with the given tag (ignoring namespace)."""
    for el in root.iter():
        if el.tag.split("}")[-1] == tag:
            return el.text
    return None

def _parse_ws_preset_id(xml_str: str) -> int | None:
    """Extract preset ID from WebSocket message (nowSelectionUpdated)."""
    root = _parse_xml(xml_str)
    if root is not None:
        # Look for <nowSelectionUpdated><preset id="N" /></nowSelectionUpdated>
        # Note: some messages have namespaces
        for update in root.iter():
            if update.tag.split("}")[-1] == "nowSelectionUpdated":
                preset = next((e for e in update.iter() if e.tag.split("}")[-1] == "preset"), None)
                if preset is not None and preset.get("id"):
                    try:
                        pid = int(preset.get("id"))
                        if pid > 0: return pid
                    except ValueError:
                        pass
    
    # Fallback to regex for tricky messages
    m = re.search(r'<nowSelectionUpdated>.*?<preset id="([1-6])"', xml_str, re.DOTALL)
    if m:
        return int(m.group(1))
    return None

def _infer_mime_type(url: str) -> str:
    """Infer MIME type from URL extension or HTTP sniff (cached, 2s limit)."""
    if url in _mime_cache:
        return _mime_cache[url]

    # 1. Extension check
    path = url.split("?")[0].split("#")[0]
    ext = path.split(".")[-1].lower() if "." in path else ""
    
    mapping = {
        "mp3": "audio/mpeg",
        "m4a": "audio/aac",
        "aac": "audio/aac",
        "flac": "audio/flac",
        "ogg": "audio/ogg",
        "oga": "audio/ogg",
        "wav": "audio/wav",
        "wma": "audio/x-ms-wma",
    }
    if ext in mapping:
        return mapping[ext]

    # 2. HTTP Sniff (HEAD + Range fallback, 2s deadline)
    deadline = time.time() + 2.0
    try:
        # Try HEAD first
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=max(0.1, deadline - time.time())) as r:
            mime = r.headers.get("Content-Type")
            if mime and "audio/" in mime:
                _mime_cache[url] = mime
                return mime
    except Exception:
        pass

    # Fallback to default
    return "audio/mpeg"

def build_didl(url: str, meta: dict) -> str:
    """Build DIDL-Lite XML for UPnP SetAVTransportURI."""
    title = meta.get("name") or "SoundTouch Stream"
    icon = meta.get("favicon") or ""
    mime = _infer_mime_type(url)
    
    protocol_info = f"http-get:*:{mime}:*"
    
    # Manual escaping for simplicity and compatibility
    def esc(s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    xml = (
        '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
        '<item id="0" parentID="-1" restricted="1">'
        f'<dc:title>{esc(title)}</dc:title>'
        '<upnp:class>object.item.audioItem.audioBroadcast</upnp:class>'
        f'<upnp:albumArtURI>{esc(icon)}</upnp:albumArtURI>'
        f'<res protocolInfo="{protocol_info}">{esc(url)}</res>'
        '</item>'
        '</DIDL-Lite>'
    )
    return xml

def apply_preset_meta_overrides(cfg: dict, n: int, meta: dict) -> dict:
    """Override metadata with manual values from config if present."""
    res = meta.copy()
    name_key = f"preset_{n}_name"
    icon_key = f"preset_{n}_favicon"
    if cfg.get(name_key):
        res["name"] = cfg[name_key]
    if cfg.get(icon_key):
        res["favicon"] = cfg[icon_key]
    return res