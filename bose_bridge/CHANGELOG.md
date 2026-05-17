# Changelog

## 1.8.1

- **Generic Preset Triggers**: Improved button reporting logic. Presets are now always reported to Home Assistant as `last_preset`, even if no stream URL is configured. This allows using Bose physical buttons to trigger any HA automation (e.g., Music Assistant playlists).

## 1.8.0

- **Modular Refactor**: Completely restructured the project into a proper Python package for better maintainability and testability.
- **Improved Multi-speaker Support**: Each speaker now runs in its own thread with dedicated WebSocket and UPnP handling, coordinated by a central bridge.
- **Centralized Configuration**: All constants and default values moved to `constants.py`.
- **Unified Config Loading**: Simplified `config.py` to handle both Home Assistant Supervisor and standalone Docker environments seamlessly.
- **Robust MQTT Command Handling**: New centralized MQTT message dispatcher for reliable cross-speaker preset triggering.
- **Enhanced URL Sanitization**: Improved cleaning of stream URLs (stripping backticks, quotes, and whitespace) across all config entry points.
- **Code Quality**: Applied PEP8 formatting, improved error handling, and updated unit tests to cover the new modular structure.

## 1.7.7

- Cap MIME detection network overhead to 2 seconds total per URL (shared deadline across HEAD + Range fallback; cached).

## 1.7.6

- Improve DIDL-Lite MIME inference: use URL path extension first, then fall back to a lightweight HTTP HEAD/Range request (cached) when extension is missing.

## 1.7.5

- Remove deprecated `build.yaml` and move base image selection into Dockerfile (uses `BUILD_ARCH`).

## 1.7.4

- Improve DIDL-Lite `protocolInfo` inference by using the URL path (handles query strings correctly) and fix extension matching for AAC/MP3.
- Update radio-browser `User-Agent` header to a stable value (no hard-coded old version).
- Simplify preset sync API: `sync_presets(host, presets)` no longer requires unused UPnP service arguments.

## 1.7.3

- Add automatic retry with exponential backoff for critical network operations:
  - SSDP speaker discovery
  - `/info` endpoint for speaker details
  - `/presets` endpoint for preset state
  - `storePreset` endpoint for preset synchronization
- Extend audio format support in DIDL-Lite metadata:
  - AAC (m4a, m4b)
  - Ogg Vorbis (ogg, oga)
  - FLAC (flac)
  - WAV (wav)
  - WMA (wma)
  - MP3 (mp3, mp2, mpga) — still default
- Document HTTPS limitation: SoundTouch firmware requires plain HTTP URLs; HTTPS is not supported.

## 1.7.2

- Fix runtime error when playing presets: import `build_didl` into the bridge module.

## 1.7.1

- Fix add-on Docker build by correcting build context copy paths in Dockerfiles.

## 1.7.0

- Bump add-on version to 1.7.0.
- Refactor bridge logic into modular Python packages and improve runtime test coverage.
- Add unit tests for config loading, discovery, metadata lookup, MQTT discovery, and preset synchronization.

## 1.6.11

- Change preset sync to use the local `POST /storePreset` endpoint (deterministic, no `/key` long-press dependency).

## 1.6.10

- Sanitize URLs loaded from Home Assistant options (strip backticks/quotes), and force preset re-sync if a device has “dirty” stored URLs (backticks/leading/trailing spaces).

## 1.6.9

- Improve URL cleaning (strip backticks anywhere) and broaden WS debug logging to show message type when preset events are missing.

## 1.6.8

- Improve WebSocket preset parsing: select the last non-zero preset id within `nowSelectionUpdated` and avoid treating id=0 as “unparsed”.

## 1.6.7

- Fix WebSocket preset detection: prefer the preset id inside `nowSelectionUpdated` (avoids incorrectly picking the wrong preset id when other `<preset>` tags appear in the message).

## 1.6.6

- Harden URL parsing (strip backticks/quotes) and add WebSocket debug logging for unparsed preset events.

## 1.6.5

- Revert `preset_N_use_icy` flag. Sending empty DIDL-Lite metadata to Bose SoundTouch via UPnP results in a blank screen and does not fallback to parsing stream ICY metadata.

## 1.6.4

- Add optional per-preset `preset_N_use_icy` flag to prefer ICY “StreamTitle” metadata on the speaker (sends empty UPnP metadata instead of DIDL).

## 1.6.3

- Add Home Assistant MQTT-discovery sensors per speaker: WebSocket connectivity, last played preset + timestamp, and last error.

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
