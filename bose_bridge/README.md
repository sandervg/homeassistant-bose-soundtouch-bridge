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

## Usage & Integrations

### Using Presets as Generic Triggers (e.g., Music Assistant)
Since version 1.8.1, the bridge always reports button presses to Home Assistant, even if no `preset_N_url` is configured. This allows you to use physical buttons on your Bose speaker to trigger any automation.

**Example: Play Music Assistant Playlist on Preset 1**
1. Leave `preset_1_url` empty in the Add-on configuration.
2. Create an automation in Home Assistant:

```yaml
alias: "Bose Button 1 -> Music Assistant"
trigger:
  - platform: state
    entity_id: sensor.bose_soundtouch_last_preset # Adjust to your sensor entity
    to: "1"
action:
  - service: mass.play_media
    target:
      entity_id: media_player.bose_soundtouch_ma # Your speaker in Music Assistant
    data:
      media_id: "library://playlist/12"
      media_type: playlist
```

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
