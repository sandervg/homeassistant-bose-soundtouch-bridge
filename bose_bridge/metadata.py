import json 
import urllib.parse
import urllib.request

from bose_bridge.constants import RADIO_BROWSER_BASES


def lookup_station(url: str) -> dict[str, str]:
    """Return {'name': str, 'favicon': str} or empty dict if not found."""
    body = urllib.parse.urlencode({"url": url}).encode()
    for base in RADIO_BROWSER_BASES:
        try:
            req = urllib.request.Request(
                f"{base}/json/stations/byurl",
                data=body,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "homeassistant-bose-soundtouch-bridge",
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
