# AGENTS.md — Bose SoundTouch Bridge

## What this is

Home Assistant add-on that revives physical preset buttons on Bose SoundTouch speakers (post-2026 cloud retirement). Listens to the speaker's local WebSocket (`ws://<host>:8080`, subprotocol `gabbo`), and on button press pushes the configured URL via UPnP `SetAVTransportURI`/`Play`. MQTT discovery creates HA button entities per preset.

## Project structure

- `bose_bridge/` — Python package (not installable via pip; no `setup.py`/`pyproject.toml`)
- `bridge.py` — entrypoint (`python3 -u /bridge.py` inside container, `python3 -u bridge.py` locally)
- `bose_bridge/config.py` — reads `/data/options.json` (Supervisor) or env vars (standalone). Includes `get_version()` which reads from `config.yaml`.
- `bose_bridge/helpers.py` — URL cleaning, DIDL-Lite XML, MIME inference, WebSocket XML parsing
- `bose_bridge/discovery.py` — SSDP speaker discovery, `/info` parsing, UPnP service lookup
- `bose_bridge/preset_sync.py` — writes preset URLs to speaker's `/storePreset` endpoint
- `bose_bridge/mqtt.py` — MQTT publisher + HA discovery configs
- `bose_bridge/metadata.py` — station name/favicon lookup via radio-browser.info
- `bose_bridge/constants.py` — centralized constants and custom exceptions (`BoseError`, `BoseConnectionError`, `NoURLAvailable`)
- `bose_bridge/config.yaml` — HA add-on configuration schema (v1.8.2)
- `run.sh` — Supervisor container entrypoint (executes `/bridge.py`)
- `Dockerfile` — Supervisor deployment (uses `ghcr.io/home-assistant/${BUILD_ARCH}-base:latest`)
- `Dockerfile.standalone` — standalone Docker (published to GHCR)
- `tests/` — unit tests (stdlib `unittest`)
- `set_presets.py`, `select_test.py` — ad-hoc utilities (not part of the bridge)

## Tests

```powershell
python -m unittest discover -s tests
```

Tests use `unittest` (not pytest), standard mocking (`unittest.mock`), no test runner config. Each test file has a `__main__` guard so you can run a single file:

```powershell
python -m unittest tests.test_helpers
python -m unittest tests.test_helpers.TestHelpers.test_clean_url_strips_quotes_and_backticks
```

No integration test suite — tests are pure unit tests with no speaker hardware.

## Dependencies (declared only in Dockerfiles)

- `upnpclient==1.0.3`
- `websocket-client==1.9.0`
- `paho-mqtt==2.1.0`
- System: `python3`, `py3-pip`, `py3-lxml` (Supervisor); `python:3.12-alpine` with `libxml2`, `libxslt` (standalone)

No `requirements.txt`, `pyproject.toml`, or lockfile. Install locally:

```powershell
pip install upnpclient==1.0.3 websocket-client==1.9.0 paho-mqtt==2.1.0 py3-lxml
```

## Running locally

```powershell
$env:BOSE_HOST="192.168.1.x"
$env:PRESET_1_URL="http://stream.example/radio.mp3"
python -m bose_bridge.bridge
```

Or from repo root:

```powershell
python bose_bridge/bridge.py
```

## Config modes

- **Supervisor**: reads `/data/options.json` (written by HA add-on UI)
- **Standalone Docker / local**: environment variables (`BOSE_HOST`, `PRESET_1_URL`…`PRESET_6_URL`, `SYNC_PRESETS_ON_STARTUP`, `MQTT_HOST`/`PORT`/`USERNAME`/`PASSWORD`, `SPEAKERS_JSON`)
- Multi-speaker via `speakers:` list (config.yaml) or `SPEAKERS_JSON` env var

## CI

`.github/workflows/docker.yml` — on tag `v*` or `workflow_dispatch`, builds & pushes standalone image to `ghcr.io/<owner>/bose-soundtouch-bridge` (multi-arch amd64 + arm64).

## Important constraints

- **SoundTouch firmware requires plain HTTP URLs** — HTTPS will fail silently. All stream URLs must use `http://`.
- **Host networking is required** in Docker (`network_mode: host`) for SSDP multicast and UPnP.
- **Generic Preset Triggers**: Button events are always reported to HA via MQTT (`last_preset`), even if no URL is configured for that preset. This allows external handling via Music Assistant or other HA automations.
- **Preset State Reset**: `last_preset` state is reset to an empty string 1s after each update to ensure consecutive presses of the same button trigger HA automations correctly.
- The speaker's UPnP description URL follows the pattern `http://<host>:8091/XD/BO5EBO5E-F00D-F00D-FEED-{deviceID}.xml`.
- All critical network operations have built-in retry with exponential backoff (0.5s→1s→2s, 3 attempts max).

## Coding conventions

- **Single Source of Truth**: Version is maintained in `bose_bridge/config.yaml` and read dynamically via `config.get_version()`.
- **Type Annotations**: Use Python 3.10+ type hints (e.g., `dict[str, Any]`, `str | None`).
- **Error Handling**: Use custom exceptions from `constants.py` (`BoseError`, etc.) instead of generic `ValueError`.
- **Logging**: Use `print(f"[tag] ...")` for consistency.
- Tests use `unittest.TestCase`, mocks via `unittest.mock.patch`.
