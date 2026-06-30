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

#### Stream URLs must be plain HTTP

SoundTouch firmware **cannot play `https://` streams** — its UPnP renderer
silently drops a TLS URI and playback fails with `402 No URI supplied`.
Always use the plain `http://` variant of a station's stream. Most
broadcasters publish an HTTP endpoint alongside the HTTPS one.

#### MQTT broker (optional)

MQTT enables the Home Assistant button entities and status sensors.

- **Mosquitto add-on**: leave the `mqtt_*` options blank. The add-on
  auto-discovers the broker from the Supervisor's MQTT service.
- **External broker (e.g. EMQX)**: set `mqtt_host` (and `mqtt_port`,
  `mqtt_username`, `mqtt_password` as needed) in the add-on Configuration
  tab. Explicit settings take precedence over the Supervisor service.
- **Standalone Docker**: use the `MQTT_HOST`, `MQTT_PORT`,
  `MQTT_USERNAME`, `MQTT_PASSWORD` environment variables.

## Usage & Integrations

### Using Presets as Generic Triggers (Simple Example)
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
  - service: music_assistant.play_media # Use music_assistant.play_media for stable MA versions
    target:
      entity_id: media_player.bose_soundtouch_ma # Your speaker in Music Assistant
    data:
      media_id: "library://playlist/12"
      media_type: playlist
```

### Advanced Usage: Full Bose Preset Control with Music Assistant
For more complex setups where you want to use all 6 preset buttons for different actions, see our complete example automation:

See [`sample_automation_ha.yaml`](sample_automation_ha.yaml) for a full example that demonstrates how to:
- Use presets 1-3 for different radio stations
- Use preset 4 for Play/Pause toggle
- Use preset 5 for Next Track
- Use preset 6 for playing a playlist with shuffle

This example requires Bose SoundTouch Bridge v1.8+ and shows how to completely control Music Assistant using physical preset buttons without configuring any stream URLs in the bridge.

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
