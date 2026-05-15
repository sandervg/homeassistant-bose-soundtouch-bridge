import html
import re
import urllib.parse
import xml.etree.ElementTree as _ET

RADIO_BROWSER_BASES = [
    "https://de1.api.radio-browser.info",
    "https://nl1.api.radio-browser.info",
    "https://at1.api.radio-browser.info",
]
PRESET_RE = re.compile(r'<nowSelectionUpdated>\s*<preset id="(\d+)"')


def _clean_url(v) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if "`" in s:
        s = s.replace("`", "").strip()
    if len(s) >= 2 and s[0] in ("'", '"') and s[-1] == s[0]:
        s = s[1:-1].strip()
    return s


def _ws_kind(msg: str) -> str:
    m = re.search(r"<updates\b[^>]*>\s*<([A-Za-z0-9_:.-]+)", msg)
    if m:
        return m.group(1)
    return "unknown"


def _sanitize_cfg_urls(cfg: dict):
    for n in range(1, 7):
        k = f"preset_{n}_url"
        if k in cfg:
            cfg[k] = _clean_url(cfg.get(k))
        k = f"preset_{n}_favicon"
        if k in cfg:
            cfg[k] = _clean_url(cfg.get(k))
    speakers = cfg.get("speakers")
    if isinstance(speakers, list):
        for s in speakers:
            if isinstance(s, dict):
                for n in range(1, 7):
                    k = f"preset_{n}_url"
                    if k in s:
                        s[k] = _clean_url(s.get(k))
                    k = f"preset_{n}_favicon"
                    if k in s:
                        s[k] = _clean_url(s.get(k))


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
    if "nowSelectionUpdated" in msg:
        root = _parse_xml(msg)
        if root is not None:
            ids: list[int] = []
            for node in (e for e in root.iter() if e.tag.split("}")[-1] == "nowSelectionUpdated"):
                for preset_el in (
                    e
                    for e in node.iter()
                    if e.tag.split("}")[-1] == "preset" and e.get("id")
                ):
                    try:
                        ids.append(int(preset_el.get("id")))
                    except Exception:
                        continue
            for v in reversed(ids):
                if 1 <= v <= 6:
                    return v
            if ids:
                return ids[-1]

    m = PRESET_RE.search(msg)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def build_didl(url: str, meta: dict) -> str:
    """Build DIDL-Lite metadata XML for UPnP playback.
    
    Supports:
    - audio/mpeg (MP3)
    - audio/aac (AAC, m4a)
    - audio/ogg (Ogg Vorbis)
    - audio/flac (FLAC)
    - audio/wav (WAV)
    - audio/x-ms-wma (WMA)
    - application/ogg (Ogg container)
    """
    title = html.escape(meta.get("name") or "Internet Radio")
    art = html.escape(meta.get("favicon") or "")
    art_tag = f"<upnp:albumArtURI>{art}</upnp:albumArtURI>" if art else ""
    
    # Infer protocol info from URL extension
    url_lower = url.lower()
    protocol_info = "http-get:*:audio/mpeg:*"
    if url_lower.endswith(("m4a", ".m4b")):
        protocol_info = "http-get:*:audio/aac:*"
    elif url_lower.endswith(".ogg") or url_lower.endswith(".oga"):
        protocol_info = "http-get:*:audio/ogg:*"
    elif url_lower.endswith(".flac"):
        protocol_info = "http-get:*:audio/flac:*"
    elif url_lower.endswith(".wav"):
        protocol_info = "http-get:*:audio/wav:*"
    elif url_lower.endswith(".wma"):
        protocol_info = "http-get:*:audio/x-ms-wma:*"
    elif url_lower.endswith(("mp3", ".mp2", ".mpga")):
        protocol_info = "http-get:*:audio/mpeg:*"
    else:
        # Default to mpeg for unknown extensions; SoundTouch usually tries to play anyway
        protocol_info = "http-get:*:audio/mpeg:*"
    
    return (
        '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
        '<item id="0" parentID="-1" restricted="1">'
        f"<dc:title>{title}</dc:title>"
        "<upnp:class>object.item.audioItem.audioBroadcast</upnp:class>"
        f"{art_tag}"
        f'<res protocolInfo="{protocol_info}">{html.escape(url)}</res>'
        "</item></DIDL-Lite>"
    )


def apply_preset_meta_overrides(cfg: dict, n: int, meta: dict) -> dict:
    name = (cfg.get(f"preset_{n}_name") or "").strip()
    if name:
        meta["name"] = name
    favicon = _clean_url(cfg.get(f"preset_{n}_favicon"))
    if favicon:
        meta["favicon"] = favicon
    return meta
