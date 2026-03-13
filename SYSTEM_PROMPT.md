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
| **FX lights** | OSC trigger to QLC+ | `python-osc` |
| **Mirrorball pin spots** | OSC trigger to QLC+ | `python-osc` |
| **Screen / beamer** | Fullscreen pygame display: countdown timer or shuffle logo | `pygame.display` |

## Tech Stack

- **Python 3** on **Raspberry Pi**
- **pygame** — audio playback (MP3, fade, end-event detection) and fullscreen display (timer + logo)
- **xair-api** — OSC control of Behringer XR12 faders. Preferred over MIDI because it needs no USB interface, just a network connection
- **QLC+** — DMX lighting control. Runs as a companion application handling all fixture management, scenes, and chases. The Python process triggers QLC+ scenes via OSC. This keeps lighting design in a proper lighting tool and out of the Python code
- **python-osc** — sends OSC messages to QLC+ (and can also be used for XR12 if not using `xair-api`)
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
- If QLC+ is not running or unreachable via OSC, print a warning and continue — same logic.
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
- `player_dmx.rbx` + `vendor/rdmx/` — DMX lighting via USB serial (Enttec protocol). Now replaced by QLC+ with OSC triggers.
- `control_with_serial/control_with_serial.ino` — Arduino controlling MCP42010 digital potentiometer for analog crossfader. No longer needed — the XR12 handles fading digitally via OSC.
- `CountDownToNextDJ.qtz` — Quartz Composer countdown timer. Now replaced by pygame fullscreen display.
- `Shuffle.nml` — Traktor playlist file. The new system just reads MP3s from a directory.

## Testing

**Write tests first, run them, then write the implementation.**

Use `pytest`. All hardware I/O (XR12, QLC+, pygame) must be behind thin wrappers so tests can run without real hardware.

**What to test:**
- **State machine transitions** — timer expiry triggers `DJ_SET` → `SHUFFLE`, track end triggers `SHUFFLE` → `DJ_SET`
- **Shuffle track selection** — random, no repeats until all tracks played, reshuffles when exhausted
- **Fade sequences** — correct OSC values sent in order (mock the OSC client)
- **Timer countdown** — ticks correctly, fires event at `00:00`
- **Graceful degradation** — system continues when XR12 or QLC+ is unreachable

**What not to test:**
- pygame rendering (visual output)
- Actual OSC/network communication
- QLC+ or XR12 behavior

**Structure:**
- Tests live in `tests/` with files mirroring the source: `tests/test_state_machine.py`, `tests/test_mixer.py`, etc.
- Use `unittest.mock.patch` to replace hardware clients with mocks
- Tests must run fast (no `sleep`, no network, no audio) and pass without any hardware connected

**Workflow:** Before writing any production code for a feature, write a failing test that describes the expected behavior. Make it pass. Then move on.

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

## QLC+ / DMX Details

QLC+ handles all DMX fixture management, scenes, and effects. The Python process does **not** send raw DMX — it triggers pre-built QLC+ scenes via OSC.

- **QLC+ OSC plugin:** Enable the OSC input plugin in QLC+. By default it listens on UDP port `7700`.
- **Scene design:** Create two scenes in QLC+:
  - **"DJ Set"** — FX lights on, pin spots off
  - **"Shuffle"** — FX lights off, pin spots on
- **OSC triggers:** Map each scene to an OSC address in QLC+ (via Input Profile or the Virtual Console). The Python process sends a single OSC message to switch between them.
- **Example from Python:**
  ```python
  from pythonosc.udp_client import SimpleUDPClient
  qlc = SimpleUDPClient("127.0.0.1", 7700)
  qlc.send_message("/qlc/scene/dj_set", 1.0)   # activate DJ Set scene
  qlc.send_message("/qlc/scene/shuffle", 1.0)   # activate Shuffle scene
  ```
- The exact OSC addresses depend on how you configure QLC+'s Virtual Console widgets. Map buttons to scenes, then assign OSC input to those buttons.
- QLC+ runs on Raspberry Pi (available via `apt install qlcplus`). It can run headless with `-w` (web interface) or with its own GUI.
- All fixture patching, DMX channel mapping, and light show design stays in QLC+ — the Python code only needs to say "activate this scene."
