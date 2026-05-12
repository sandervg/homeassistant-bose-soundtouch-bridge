# Changelog

## 1.6.2

- Allow configuring manual preset metadata (`preset_N_name`, `preset_N_favicon`) to override radio-browser results.

## 1.6.1

- Fix add-on options validation when using only `speakers` (root preset fields are now truly optional).

## 1.6.0

- Multi-speaker support via a `speakers` list in add-on configuration (one WebSocket thread per speaker).
- MQTT command handling now supports multiple devices.

## 1.5.1

- More robust XML parsing for speaker info and preset state (with regex fallback).
- Sync now restores previous mute/volume state after writing presets.
- Pinned Python dependency versions in Docker images for reproducible builds.

## 1.5.0

- **Standalone Docker image** for Home Assistant Container / plain
  Docker / NAS / Pi deployments where the Supervisor isn't available.
  Published at `ghcr.io/sandervg/bose-soundtouch-bridge:latest`
  (multi-arch: amd64 + arm64). See `docker-compose.example.yml` and the
  repo README.
- `bridge.py` now reads config from environment variables
  (`BOSE_HOST`, `PRESET_1_URL` … `PRESET_6_URL`,
  `SYNC_PRESETS_ON_STARTUP`, `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`,
  `MQTT_PASSWORD`) when `/data/options.json` isn't present, so the
  same code runs inside Supervisor and standalone.
- GitHub Actions workflow builds and publishes the standalone image to
  GHCR on every version tag.

## 1.4.0

- **Auto-sync presets to the speaker on startup.** New
  `sync_presets_on_startup` option (default `true`). The add-on writes
  each configured URL onto the speaker's preset slot so physical button
  presses always emit a `nowSelectionUpdated` event for the bridge to
  intercept. Without this, factory-reset speakers leave preset slots
  empty and physical button presses become silent no-ops.
- The sync skips slots that already match the configured URL, mutes the
  speaker during the write to hide the audio blip, and verifies each
  save took effect.
- IMPORTANT firmware quirk: the SoundTouch firmware refuses to save
  preset items that carry DIDL-Lite metadata (it sets
  `isPresetable="false"`). The sync therefore writes presets without
  metadata; runtime playback still applies full DIDL via
  `SetAVTransportURI` so the speaker shows the station name and logo.

## 1.3.1

- Stop the speaker before each SetAVTransportURI so the DIDL-Lite
  metadata (station name + favicon) lands cleanly in `now_playing` even
  when the press came from a physical preset button that started
  loading a stale on-device source first (TuneIn / cached UPnP item).

## 1.3.0

- **Speaker now displays the station name and logo.** Each `Play` call
  carries DIDL-Lite metadata (`dc:title`, `upnp:albumArtURI`,
  `audioBroadcast` class). Station name + favicon are auto-fetched from
  [radio-browser.info](https://www.radio-browser.info/) by stream URL
  at startup and cached for the session.
- **Trigger presets from Home Assistant.** The add-on connects to the
  Supervisor-provided MQTT broker (Mosquitto add-on) and publishes Home
  Assistant MQTT-discovery configs so each preset auto-appears as a
  `button.bose_<id>_preset_N` entity. Press the entity in HA → bridge
  plays the same URL it would play on a physical button press.
  Requires the Mosquitto Broker add-on running and the MQTT integration
  configured in HA (the standard auto-discovery setup).
- The add-on declares `services: ["mqtt:need"]` so the Supervisor
  injects MQTT credentials automatically — no manual configuration.
  Falls back gracefully if MQTT is unavailable (logs a warning, only
  physical buttons keep working).

## 1.2.1

- Fix multi-architecture build. The `1.2.0` Dockerfile only pulled the
  amd64 base image and failed on aarch64 (ARM64) Home Assistant
  installations. Re-added `build.yaml` mapping each supported
  architecture to its correct base image.
- Dropped deprecated `armv7`, `armhf`, `i386` from `arch` (modern
  Supervisor flags these). Supported architectures are now `amd64` and
  `aarch64`.

## 1.2.0

- Polished release for public use.
- Auto-discovers the SoundTouch via SSDP if `bose_host` is left blank.
- Auto-derives the UPnP description URL from the speaker's `/info`
  endpoint — works on any SoundTouch model out of the box.
- Removed deprecated `build.yaml` (FROM image inlined into Dockerfile).
- Default config is now empty so first-time users can paste their own
  URLs.

## 1.1.0

- Added 6 configurable preset URL fields and a `bose_host` field via the
  add-on **Configuration** tab.

## 1.0.0

- Initial WebSocket → UPnP bridge with hardcoded URL map.
