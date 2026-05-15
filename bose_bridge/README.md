# Bose SoundTouch Bridge

Release 1.7.0 adds internal refactors and improved reliability while
keeping the same physical preset support.

Brings the **physical preset buttons** on Bose SoundTouch speakers back
to life after the **Bose cloud retirement (2026)**.

## What this fixes

When the Bose cloud was retired, every preset that relied on it stopped
working — TuneIn presets, the SoundTouch app, and the
`LOCAL_INTERNET_RADIO` source all return errors. Spotify and AUX still
work, but the six physical buttons on top of the speaker are mostly dead.

This add-on revives them. It listens to the speaker's local WebSocket
notification stream and, whenever you press a preset button, pushes the
URL you configured for that slot via UPnP — using the local
`SetAVTransportURI` / `Play` calls that are still fully functional in
the firmware.

## What you get

- Press preset 1 → plays whatever stream URL you put in slot 1
- Press preset 2 → slot 2
- … and so on, all six buttons
- Configurable per-preset URLs in the add-on's **Configuration** tab
- Supports multiple speakers from a single add-on instance (v1.6+)
- Works with any plain HTTP/MP3 internet-radio stream (icecast, etc.)
- No Bose cloud, no app, no rooting — pure local network

## Requirements

- One or more Bose SoundTouch speakers (any model with the SoundTouch firmware) on
  the same network as Home Assistant
- Home Assistant OS or Supervised (the add-on runs as a Docker container
  managed by the Supervisor)

## Setup

1. Install this add-on (see *Install* below).
2. Open the add-on → **Configuration**.
3. Configure speakers:
   - Multi-speaker (recommended): fill in `speakers:` with one entry per speaker
     (see example below).
   - Single-speaker (legacy): use `bose_host` + `preset_1_url` … `preset_6_url`.
4. Leave `sync_presets_on_startup` enabled (default). On startup, the
   add-on writes each configured URL into the speaker's matching preset
   slot — required so physical button presses emit the WebSocket event
   the bridge listens for. Skip-when-equal makes restarts cheap.
5. **Save** → **Start** → check the **Log** tab; it should print
   ```
   [upnp] speaker: ...
   [upnp] description: http://...
   [ws] ... connected to ws://...:8080
   ```

Press a preset button on the speaker and the radio should kick in.

### Multi-speaker configuration example

```yaml
speakers:
  - host: 192.168.1.20
    name: Jadalnia Bose
    sync_presets_on_startup: true
    preset_1_url: http://live.r357.eu
    preset_2_url: http://mp3.polskieradio.pl:8904/
  - host: 192.168.1.90
    name: Sypialnia Bose
    sync_presets_on_startup: true
    preset_1_url: http://live.r357.eu
    preset_2_url: http://mp3.polskieradio.pl:8904/
```

For HA control: with the Mosquitto Broker add-on running and the MQTT
integration configured in HA Core, six `button.bose_<id>_preset_N`
entities auto-appear via MQTT discovery. Pressing one in HA UI /
automations / scripts plays the same URL the physical button would.

## Example URLs (Belgian / Flemish radio)

| Preset | Station | URL |
|---|---|---|
| 1 | VRT Radio 1 | `http://icecast.vrtcdn.be/radio1-high.mp3` |
| 2 | VRT Radio 2 OVL | `http://icecast.vrtcdn.be/ra2ovl-high.mp3` |
| 3 | VRT Radio 1 Classics | `http://icecast.vrtcdn.be/radio1_classics-high.mp3` |
| 4 | VRT Studio Brussel | `http://icecast.vrtcdn.be/stubru-high.mp3` |
| 6 | VRT Nieuwsbrief | `http://progressive-audio.vrtcdn.be/content/fixed/11_11niws-snip_hi.mp3` |

For other stations, look up the direct stream URL on the broadcaster's
website (search for `icecast`, `mp3`, or `aac`). Some commercial stations
hide their URL behind authenticated tokens — those won't work without an
extra proxy and are out of scope for this add-on.

## Install

1. In Home Assistant: **Settings → Add-ons → App Store → ⋮ → Repositories**
2. Add this repository's GitHub URL
3. The "Bose SoundTouch Bridge" add-on appears in the store — click
   **Install** → **Start**

## How it works

- Bose's stock firmware exposes a WebSocket notification stream on
  `ws://<speaker>:8080` (subprotocol `gabbo`). It emits an event for
  every preset button press:
  `<nowSelectionUpdated><preset id="N">…`
- The same firmware exposes a UPnP `MediaRenderer` on port 8091 with a
  fully working `AVTransport` service (the very same one the SoundTouch
  app uses for "play this URL").
- The add-on stitches them together: catch the button event, push the
  URL via UPnP. No cloud needed.

## Limitations

- Only **plain HTTP audio streams** (no token-protected commercial
  streams without an extra proxy)
- The speaker's display still shows whatever the original preset is set
  to — buttons trigger the bridge regardless. If you want the right name
  to show up, store any UPnP placeholder as the preset on the speaker.
- Multi-speaker mode treats each speaker independently (no grouping / sync playback).

## License

MIT
