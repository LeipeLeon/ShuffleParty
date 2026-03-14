# Shuffle Partey!

![](de-shuffle.jpg)

A concept conceived by [De Perifeer](https://perifeer.org/) & [Wendbaar.nl](https://www.wendbaar.nl/)

## What Is It?

A DJ rotation party where each DJ gets a fixed time slot (e.g. 20 minutes). When time's up, the system automatically takes over: it fades out the DJ, plays a random "shuffle" transition track with its own light show, and then hands the stage to the next DJ. No MC needed, no operator needed — the system runs fully autonomously once started. Every DJ gets the same cycle, first to last.

## The Experience

**Startup:** The system starts in idle mode, displaying the Shuffle logo. An operator clicks "Start DJ Set" in the control panel (or presses Cmd+F) to begin.

**During a DJ set:** The audience sees a countdown timer on screen. The DJ plays their set. Lighting effects respond to the music. The mirrorball pin spots are off. The next shuffle track is pre-loaded and visible in the control panel.

**When time runs out (the "Shuffle" moment):** The DJ's audio fades out automatically via the mixer crossfade. A random shuffle track starts playing (skipping to its fade-in cue if set). The screen crossfades from the timer to the Shuffle logo. Lighting shifts — music-reactive effects go dark, mirrorball pin spots come on. This is the moment the next DJ takes position.

**When the shuffle track ends (or its fadeout cue is reached):** The shuffle track audio fades out. The DJ's audio channel opens back up. The timer resets after the crossfade completes and starts counting down again. Lighting returns to music-reactive mode. The next DJ is live.

## The State Machine

```mermaid
flowchart LR
   Idle -- "Start DJ Set" --> DJ_Set
   DJ_Set -- "timer hits 00:00" --> Shuffle_Transition -- "track ends or fadeout cue reached" --> DJ_Set
```

The system has three states:

| | **Idle** | **DJ Set** | **Shuffle Transition** |
|---|---|---|---|
| **Audio** | Silent | DJ channel open, shuffle muted | DJ faded out, shuffle playing |
| **Screen** | Shuffle logo | Countdown timer | Shuffle logo |
| **Lighting** | Off | Music-reactive FX on, pin spots off | FX off, pin spots on |
| **Trigger to exit** | "Start DJ Set" button / Cmd+F | Timer reaches `00:00` or "End DJ Set Now" | Track ends or fadeout cue reached |

## Control Panel

A second pygame window provides real-time controls:

- **Status bar** — current state (IDLE / DJ SET / SHUFFLE) and countdown timer
- **Start / Fade button** — starts the DJ set from idle, or triggers early fadeout
- **Set Duration slider** — adjust DJ set length (30s–20min, in 30s steps)
- **Track info** — cover art, artist/title, time remaining, fade-in/out cue times
- **Waveform** — visual waveform with playhead, fade-in (green) and fade-out (orange) cue markers. Click to seek.
- **Pause/Play** — pause the shuffle track (only during shuffle)
- **Skip Track** — load a different random track (only during DJ set)
- **Vertical faders** — master volume (draggable) + DJ L/R and Shuffle L/R channel levels

**Keyboard shortcut:** Cmd+F triggers the same action as the main button from either window.

## Fade Cue Points

Tracks can have ID3 tags that control playback boundaries:

- **`TXXX:FADEIN_MS`** — skip the intro, start playback here
- **`TXXX:FADEOUT_MS`** — trigger automatic fadeout at this position instead of waiting for track end

### Auto-detection

The `scripts/auto_fadeout.py` script analyzes audio levels to detect fade points automatically:

```bash
# Preview detection without writing tags
uv run python scripts/auto_fadeout.py tracks/*.mp3 --dry-run

# Write tags and generate verification images
uv run python scripts/auto_fadeout.py tracks/*.mp3

# Adjust sensitivity (higher = earlier cue, default 6 dB)
uv run python scripts/auto_fadeout.py tracks/*.mp3 --drop 10
```

Preview images are saved to `fadeout_preview/` with green (fade-in) and orange (fade-out) markers.

### Manual editing

```bash
# Show current cues
uv run python scripts/set_fadeout.py tracks/song.mp3

# Set fadeout at 3:30
uv run python scripts/set_fadeout.py tracks/song.mp3 3:30

# Remove fadeout cue
uv run python scripts/set_fadeout.py tracks/song.mp3 --remove
```

Or use [Kid3](https://kid3.kde.org/) to edit `TXXX:FADEIN_MS` / `TXXX:FADEOUT_MS` tags directly.

## Signal Routing

![doc/shuffle-timing.json](doc/shuffle-timing.png)

The system coordinates four output channels, driven by two state signals (`TIMER_STATE` and `TRACK_STATE`) and two pulse events (`TIMER_DONE` and `TRACK_DONE`):

- **Audio — DJ channel:** Controlled via OSC on a digital mixer (e.g. Behringer XR12). OSC over WiFi/Ethernet (UDP port 10023) — no USB MIDI interface needed.
- **Audio — Shuffle track:** pygame.mixer plays an MP3 routed to a separate mixer channel. A random track is selected and pre-loaded during the DJ set, triggered by timer expiry.
- **DMX — FX lights:** Music-reactive lighting. On during DJ set, off during shuffle. Controlled by [QLC+](https://www.qlcplus.org/), triggered via OSC from the Python process.
- **DMX — Pin spots:** Mirrorball spots. Off during DJ set, on during shuffle. Also driven by QLC+ scenes.
- **Screen:** A display/beamer showing either the countdown timer or the shuffle logo.

![](doc/shuffle-setup.png)

## Setup

Install [uv](https://docs.astral.sh/uv/) and set up the project:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync --group dev
```

Run with:

```bash
uv run python -m shuffle_party
```

Or use the startup script:

```bash
./start.sh
```

Put your shuffle transition MP3s in `./tracks/` before starting.

## Development Commands

| Task | Command |
|---|---|
| Sync dependencies | `uv sync --group dev` |
| Run app | `uv run python -m shuffle_party` |
| Run tests | `uv run pytest` |
| Lint | `uv run ruff check src/ tests/` |
| Lint (auto-fix) | `uv run ruff check --fix src/ tests/` |
| Type check | `uv run mypy src/` |
| Add dependency | `uv add package-name` |
| Add dev dependency | `uv add --group dev package-name` |

## Project Structure

```
ShuffleParty/
  ├── src/
  │   └── shuffle_party/
  │       ├── __init__.py
  │       ├── __main__.py        (pygame dual-window event loop + display rendering)
  │       ├── app.py              (state machine: IDLE → DJ_SET ↔ SHUFFLE)
  │       ├── config.py           (settings with .env overrides)
  │       ├── control_panel.py    (pygame control window: buttons, sliders, waveform)
  │       ├── mixer.py            (XR12 OSC crossfade)
  │       ├── lighting.py         (QLC+ OSC scenes)
  │       ├── display.py          (countdown timer logic)
  │       └── track_picker.py     (random MP3 selection)
  ├── scripts/
  │   ├── auto_fadeout.py         (detect fade-in/out cues, write tags, generate previews)
  │   └── set_fadeout.py          (CLI tool to set/show/remove FADEOUT_MS tags)
  ├── tests/
  ├── tracks/                     (shuffle transition MP3s)
  ├── pyproject.toml
  ├── start.sh
  └── README.md
```

## Alternatives

| | Python | Node.js + Chromium | openFrameworks | TouchDesigner | DragonRuby |
|---|---|---|---|---|---|
| **Audio** | pygame.mixer | Web Audio / mpv | Built-in | Built-in | Needs external lib |
| **XR12 control** | `xair-api` (OSC) | `osc.js` | `ofxOsc` | OSC nodes | No OSC support |
| **DMX** | OLA | `node-dmx` | `ofxDmx` | Plugins/OSC | Serial/USB adapter |
| **Visuals** | Basic (pygame) | Excellent (HTML/CSS) | Excellent (OpenGL) | Excellent | Good (game engine) |
| **Runs on Pi** | Yes | Yes (heavy) | Yes | No | Yes |
| **Complexity** | Low | Medium | High | Low | Medium |
| **Best for** | This project | Polished screen output | Future visual upgrades | Quick prototyping | Embedded Ruby |

**Python wins** because [`xair-api`](https://pypi.org/project/xair-api/) gives direct fader control over the XR12 via WiFi, [QLC+](https://www.qlcplus.org/) handles all DMX fixture management and light show design (triggered via OSC), and `pygame` handles audio, display, and the control panel in a single process.

