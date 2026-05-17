import json
import os
from typing import Any

from bose_bridge.constants import OPTIONS_PATH, SUPERVISOR_TOKEN, SUPERVISOR_URL
from bose_bridge.helpers import _clean_url, _sanitize_cfg_urls

def _env_bool(name: str, default: str = "true") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def load_options() -> dict[str, Any]:
    """Read config for Supervisor or standalone Docker."""
    cfg: dict[str, Any] = {
        "bose_host": os.environ.get("BOSE_HOST", "").strip(),
        "sync_presets_on_startup": _env_bool("SYNC_PRESETS_ON_STARTUP", "true"),
        "mqtt_host": os.environ.get("MQTT_HOST", "").strip(),
        "mqtt_port": int(os.environ.get("MQTT_PORT", "1883")),
        "mqtt_username": os.environ.get("MQTT_USERNAME", "").strip(),
        "mqtt_password": os.environ.get("MQTT_PASSWORD", "").strip(),
        "speakers": [],
    }
    
    # Root presets from env
    for n in range(1, 7):
        cfg[f"preset_{n}_url"] = _clean_url(os.environ.get(f"PRESET_{n}_URL", ""))
        cfg[f"preset_{n}_name"] = os.environ.get(f"PRESET_{n}_NAME", "").strip()
        cfg[f"preset_{n}_favicon"] = os.environ.get(f"PRESET_{n}_FAVICON", "").strip()

    # Load from options.json if exists (Supervisor)
    if os.path.exists(OPTIONS_PATH):
        try:
            with open(OPTIONS_PATH, encoding="utf-8") as f:
                supervisor_cfg = json.load(f)
            if isinstance(supervisor_cfg, dict):
                cfg.update(supervisor_cfg)
        except Exception as e:
            print(f"[cfg] failed to load {OPTIONS_PATH}: {e}")

    # Speakers list from env
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

    # Sanitize all URLs
    _sanitize_cfg_urls(cfg)
    
    return cfg
