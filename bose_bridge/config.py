import json
import os
from typing import Any

from bose_bridge.helpers import _clean_url, _sanitize_cfg_urls

OPTIONS_PATH = "/data/options.json"
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN")
SUPERVISOR_URL = "http://supervisor"


def _env_bool(name: str, default: str = "true") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def load_options() -> dict[str, Any]:
    """Read config for Supervisor or standalone Docker."""
    if os.path.exists(OPTIONS_PATH):
        with open(OPTIONS_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        if isinstance(cfg, dict):
            _sanitize_cfg_urls(cfg)
        return cfg

    print("[cfg] /data/options.json not found — reading config from environment")
    cfg: dict[str, Any] = {
        "bose_host": os.environ.get("BOSE_HOST", "").strip(),
        "sync_presets_on_startup": _env_bool("SYNC_PRESETS_ON_STARTUP", "true"),
        "speakers": [],
    }
    for n in range(1, 7):
        cfg[f"preset_{n}_url"] = _clean_url(os.environ.get(f"PRESET_{n}_URL", ""))
        cfg[f"preset_{n}_name"] = os.environ.get(f"PRESET_{n}_NAME", "").strip()
        cfg[f"preset_{n}_favicon"] = os.environ.get(f"PRESET_{n}_FAVICON", "").strip()

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
