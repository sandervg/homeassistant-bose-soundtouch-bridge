import html
import re
import time
import urllib.request
from functools import wraps

from bose_bridge.helpers import _clean_url, _parse_xml


def _retry(max_attempts: int = 3, backoff_sec: float = 0.5):
    """Decorator for retrying operations with exponential backoff."""
    def decorator(fn):
        @wraps(fn)
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


def _store_preset(host: str, n: int, url: str, name: str | None) -> bool:
    url = _clean_url(url)
    if not url:
        return False
    label = (name or "").strip() or f"Preset {n}"
    body = (
        '<?xml version="1.0" encoding="UTF-8" ?>'
        f'<preset id="{n}">'
        f'<ContentItem source="UPNP" location="{html.escape(url, quote=True)}" '
        'sourceAccount="UPnPUserName" isPresetable="true">'
        f"<itemName>{html.escape(label)}</itemName>"
        "</ContentItem>"
        "</preset>"
    ).encode("utf-8")
    req = urllib.request.Request(
        f"http://{host}:8090/storePreset",
        data=body,
        headers={"Content-Type": "application/xml"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=5).read()
        return True
    except Exception as e:
        print(f"[sync] failed to store preset {n} on {host}: {e}")
        return False


@_retry(max_attempts=3, backoff_sec=0.5)
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
        if preset_el.get("location"):
            return preset_el.get("location")

    m = re.search(rf'<preset id="{n}"[^>]*>(.*?)</preset>', xml, re.DOTALL)
    if not m:
        return None
    loc = re.search(r'location="([^"]+)"', m.group(1))
    return loc.group(1) if loc else None


def sync_presets(host: str, presets: dict):
    """Save each configured preset onto the speaker so physical button presses
    fire the WebSocket event the bridge listens for. Skips slots already in
    the right state."""
    targets = {n: {"url": _clean_url(e["url"]), "name": e.get("name")} for n, e in presets.items() if e.get("url")}
    needed: dict[int, dict] = {}
    for n, entry in targets.items():
        u = entry["url"]
        current_raw = _current_preset_url(host, n)
        if current_raw is None:
            needed[n] = entry
            continue
        current_clean = _clean_url(current_raw)
        if current_clean != u:
            needed[n] = entry
            continue
        if current_raw != current_clean:
            needed[n] = entry
    if not needed:
        print("[sync] all configured presets already match the device — skipping")
        return
    print(f"[sync] {len(needed)}/{len(targets)} presets need writing: {sorted(needed)}")

    for n, entry in needed.items():
        url = entry["url"]
        name = entry.get("name")
        ok = _store_preset(host, n, url, name)
        time.sleep(0.2)
        stored = _current_preset_url(host, n)
        stored_clean = _clean_url(stored) if stored is not None else None
        if ok and stored_clean == url:
            print(f"[sync]  preset {n} -> {url}")
        else:
            print(f"[sync]  preset {n} did not stick (now: {stored})")
