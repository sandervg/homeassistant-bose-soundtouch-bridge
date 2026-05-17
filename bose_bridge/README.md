# Bose SoundTouch Bridge — Modular Package

This directory contains the core logic for the Bose SoundTouch Bridge. Starting with version 1.8.0, the project has been refactored into a modular structure.

## Project Structure

- `bridge.py` — Main entry point. Manages `SpeakerBridge` threads and central MQTT communication.
- `config.py` — Handles configuration loading from Home Assistant Supervisor (`options.json`) or environment variables.
- `constants.py` — Centralized constants (timeouts, SSDP addresses, XML namespaces, etc.).
- `discovery.py` — SSDP-based speaker discovery and `/info` metadata retrieval.
- `helpers.py` — URL sanitization, XML parsing, and UPnP DIDL-Lite metadata generation.
- `metadata.py` — Station name and favicon lookup via [radio-browser.info](https://radio-browser.info).
- `mqtt.py` — MQTT connectivity and Home Assistant discovery configuration.
- `preset_sync.py` — Logic for writing stream URLs directly to speaker preset slots.
- `error_handler.py` — Global exception handling and logging.

## Core Components

### SpeakerBridge
Each speaker is managed by an instance of `SpeakerBridge`. This class:
1. Connects to the speaker's local WebSocket (`ws://<host>:8080`).
2. Listens for `nowSelectionUpdated` events (physical button presses).
3. Triggers playback via UPnP (`AVTransport:SetAVTransportURI`).
4. Updates Home Assistant sensors via MQTT.

### Configuration
The bridge can be configured in two ways:
1. **Home Assistant Add-on**: Via the `Configuration` tab in the HA UI.
2. **Standalone Docker**: Using environment variables like `BOSE_HOST`, `PRESET_1_URL`, etc.

## Developer Info

### Running Tests
Unit tests use the standard `unittest` library. Run them from the project root:
```bash
python -m unittest discover -s tests
```

### Local Development
To run the bridge locally (requires environment variables):
```bash
export BOSE_HOST="192.168.1.x"
python bridge.py
```
