# Home Assistant: Bose SoundTouch Bridge

Latest release: **1.7.0**

A Home Assistant add-on repository that revives the **physical preset
buttons** on Bose SoundTouch speakers after the **Bose cloud retirement
(2026)** broke TuneIn presets, the SoundTouch app, and most cloud
sources.

The add-on listens to the speaker's local WebSocket and, when you press
a preset button, plays the URL you configured for that slot via local
UPnP — no Bose cloud needed.

See [`bose_bridge/README.md`](bose_bridge/README.md) for full docs and
configuration.

## Multi-speaker

Version 1.6+ supports multiple speakers from a single add-on instance.
Configure a `speakers:` list in the add-on Configuration tab (one entry per
SoundTouch).

## Install paths

Two install paths depending on how you run Home Assistant:

### Home Assistant OS or Supervised (Supervisor present) — recommended

1. **Settings → Add-ons → App Store → ⋮ → Repositories**
2. Paste this repository's URL and click **Add**
3. The "Bose SoundTouch Bridge" add-on appears in the App Store —
   **Install** → **Start**.

MQTT credentials are auto-wired by the Supervisor when you have the
Mosquitto Broker add-on installed and the MQTT integration set up in
HA Core.

### Home Assistant Container / plain Docker / NAS / Pi (no Supervisor)

Run the standalone Docker image alongside your HA instance.

```bash
curl -O https://raw.githubusercontent.com/kom101/homeassistant-bose-soundtouch-bridge/main/docker-compose.example.yml
mv docker-compose.example.yml docker-compose.yml
# edit the preset URLs and MQTT host/credentials, then:
docker compose up -d
```

The image is published as `ghcr.io/kom101/bose-soundtouch-bridge:latest`
(multi-arch: amd64 + arm64).

Config is via environment variables — same options as the add-on, in
UPPER_SNAKE form: `BOSE_HOST`, `PRESET_1_URL` … `PRESET_6_URL`,
`SYNC_PRESETS_ON_STARTUP`, `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`,
`MQTT_PASSWORD`.

Multi-speaker in standalone mode is available via `SPEAKERS_JSON` (a JSON
array of speaker objects containing `host`, `preset_1_url`…`preset_6_url`,
etc.). `network_mode: host` is required so the bridge can receive SSDP
multicast and reach the speaker's UPnP port.

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fkom101%2Fhomeassistant-bose-soundtouch-bridge)

## What works / what doesn't

| Source | Status after Bose cloud retirement | This add-on |
|---|---|---|
| Spotify Connect | ✅ still works | not needed |
| AUX in | ✅ still works | not needed |
| TuneIn presets | ❌ broken | ✅ replaced by URL push |
| SoundTouch app `LOCAL_INTERNET_RADIO` | ❌ broken | ✅ replaced |
| Plain HTTP icecast/MP3 streams | ✅ via local UPnP | ✅ used |
| Token-protected streams (some commercial radios) | ❌ | ⚠️ needs your own proxy |

## License

MIT — see [`LICENSE`](LICENSE).
