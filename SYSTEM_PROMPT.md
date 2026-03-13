# Shuffle Partey — AI Coding Assistant

You are building **Shuffle Partey**: an autonomous DJ rotation system that runs on a Raspberry Pi. It manages transitions between DJ sets at a party — fading audio, playing shuffle tracks, switching lights, and displaying a countdown timer — all without human intervention.

## The System

Two states, cycling forever:

**DJ Set** — Timer counts down on screen. DJ audio channel is open. Music-reactive FX lights are on. Mirrorball pin spots are off.

**Shuffle Transition** — Triggered when the timer hits `00:00`. DJ audio fades out via the mixer. A random shuffle track plays. Screen shows the shuffle logo. FX lights go off, pin spots come on. Ends when the shuffle track finishes (or hits a cue point), then the next DJ Set begins.

```
DJ_Set --[timer expires]--> Shuffle_Transition --[track ends]--> DJ_Set
```

## Output Channels

The system coordinates five outputs, all from a single Python process:

| Output | How | Library |
|---|---|---|
| **DJ audio fader** | OSC to Behringer XR12 mixer over WiFi/Ethernet (UDP port 10023) | `xair-api` |
| **Shuffle track audio** | Local MP3 playback, routed to a separate mixer channel | `pygame.mixer` |
| **FX lights** | DMX via OLA daemon | `ola` Python client |
| **Mirrorball pin spots** | DMX via OLA daemon (separate channels) | `ola` Python client |
| **Screen / beamer** | Fullscreen pygame display: countdown timer or shuffle logo | `pygame.display` |

## Tech Stack

- **Python 3** on **Raspberry Pi**
- **pygame** — audio playback (MP3, fade, end-event detection) and fullscreen display (timer + logo)
- **xair-api** — OSC control of Behringer XR12 faders. Preferred over MIDI because it needs no USB interface, just a network connection
- **OLA (Open Lighting Architecture)** — DMX output. Runs as a system daemon (`olad`), controlled via Python API. Supports Enttec USB DMX Pro, Art-Net, sACN
- No web server, no database, no frameworks. This is a single-file state machine with hardware I/O

## Architecture Guidance

**Keep it simple.** This is a ~200-line state machine with I/O callbacks, not a web app. Resist the urge to over-abstract.

- Two states: `DJ_SET` and `SHUFFLE`. Use an enum or string, not a state machine library.
- One main loop driving pygame display + event handling. Use pygame's event system for timing (e.g. `USEREVENT` for timer ticks, `MUSIC_END` for track completion).
- Fades are time-based sequences that send OSC values to the mixer over ~3 seconds. They do not need to be frame-accurate — smooth enough that the audience doesn't notice a hard cut.
- Shuffle tracks live in a directory (e.g. `./tracks/`). On each transition, pick one at random. Do not repeat until all have been played.
- The timer duration and mixer channel numbers should be configurable at the top of the file or via a simple config dict. No config files, no CLI argument parsing, no YAML.
- Audio playback and mixer fading are separate concerns: `pygame.mixer` plays the shuffle track locally; `xair-api` controls which mixer channel the audience hears.

**Error handling:**
- If the XR12 is unreachable at startup, print a warning and continue — the system should still run the timer, display, and audio even without mixer control.
- If OLA is not running, print a warning and continue — same logic.
- If the shuffle track directory is empty, raise an error at startup. This is not recoverable.
- Do not retry connections in a loop. Fail fast, log clearly.

**What not to build:**
- No web UI, REST API, or WebSocket server
- No operator controls (pause, skip, extend) — the system is fully autonomous
- No DJ queue or set list management — every cycle is identical
- No audio analysis or beat detection
- No configuration hot-reloading

## Legacy Code (Reference Only)

The repo contains a previous implementation in Ruby/JRuby + Arduino + Quartz Composer. This is **reference only** — do not port it, do not maintain compatibility. But it shows how the system worked before:

- `player_midi.rbx` — MIDI-based fade control with Traktor. Shows the fade-in/fade-out sequence, CC mappings, and serial-to-Arduino fader control. The fade logic (gradual CC value ramp over ~3 seconds) is the pattern to replicate via OSC.
- `player_dmx.rbx` + `vendor/rdmx/` — DMX lighting via USB serial (Enttec protocol). Now replaced by OLA.
- `control_with_serial/control_with_serial.ino` — Arduino controlling MCP42010 digital potentiometer for analog crossfader. No longer needed — the XR12 handles fading digitally via OSC.
- `CountDownToNextDJ.qtz` — Quartz Composer countdown timer. Now replaced by pygame fullscreen display.
- `Shuffle.nml` — Traktor playlist file. The new system just reads MP3s from a directory.

## Code Style

- Write clear, readable Python. Use type hints for function signatures.
- Flat is better than nested. Avoid deep class hierarchies.
- Name things after what they do in the domain: `fade_dj_out()`, `play_shuffle_track()`, `start_timer()` — not `handle_state_change()` or `process_event()`.
- Comments should explain *why*, not *what*. The code should be obvious enough that *what* is clear.
- One file is fine until it exceeds ~300 lines. Then split by concern: `main.py`, `mixer.py`, `dmx.py`, `display.py`.

## XR12 OSC Details

The Behringer XR12 (X Air series) uses a custom OSC protocol:

- **Endpoint:** UDP, default port `10023`
- **Fader control:** `/ch/01/mix/fader` with a float value `0.0` (off) to `1.0` (unity/0dB). Channel numbers are zero-padded two digits: `01`–`12`.
- **Mute control:** `/ch/01/mix/on` with int `0` (muted) or `1` (unmuted)
- The `xair-api` Python package wraps this. Use it rather than raw OSC — it handles connection keepalive (the XR12 requires periodic `/xremote` messages to stay subscribed).

## OLA / DMX Details

- OLA runs as a daemon (`olad`) and exposes a Python API via `ola.ClientWrapper` and `ola.OlaClient`.
- Send DMX frames as a `array.array('B', [ch1, ch2, ...])` to a universe number.
- For this project, you likely need two DMX channels: one for FX lights (0 = off, 255 = on) and one for pin spots (0 = off, 255 = on). The exact channel mapping depends on the fixtures.
- Wrap DMX in a simple function: `set_dmx(fx_level, spot_level)`. That's it.
