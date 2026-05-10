# Home Assistant: Bose SoundTouch Bridge

A Home Assistant add-on repository that revives the **physical preset
buttons** on Bose SoundTouch speakers after the **Bose cloud retirement
(2026)** broke TuneIn presets, the SoundTouch app, and most cloud
sources.

The add-on listens to the speaker's local WebSocket and, when you press
a preset button, plays the URL you configured for that slot via local
UPnP — no Bose cloud needed.

See [`bose_bridge/README.md`](bose_bridge/README.md) for full docs and
configuration.

## Add to Home Assistant

1. **Settings → Add-ons → App Store → ⋮ → Repositories**
2. Paste this repository's URL and click **Add**
3. The "Bose SoundTouch Bridge" add-on appears in the App Store —
   **Install** → **Start**.

[![Open your Home Assistant instance and show the add add-on repository dialog with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fsandervg%2Fhomeassistant-bose-soundtouch-bridge)

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
