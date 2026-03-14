# QLC+ Configuration

Pre-built QLC+ workspace for Shuffle Partey.

## Fixtures

| DMX Channel | Fixture      | Purpose                          |
|-------------|-------------|----------------------------------|
| 1–4         | FX Light 1–4 | Music-reactive par cans (DJ set) |
| 5–6         | Pin Spot 1–2 | Mirrorball spots (shuffle)       |

## Scenes

| Scene     | FX Lights | Pin Spots | Triggered by        |
|-----------|-----------|-----------|---------------------|
| **DJ Set**    | ON (255)  | OFF (0)   | Start of DJ set     |
| **Shuffle**   | OFF (0)   | ON (255)  | Start of shuffle    |

Both scenes have a 1-second fade in/out built into QLC+. The Python app also crossfades the lighting gradually during transitions.

## OSC Control

The Python app sends OSC **float** messages (0.0–1.0) to QLC+ on port 7700 (configurable via `QLC_PORT` in `.env`):

| OSC Address | Value | Effect                  |
|-------------|-------|-------------------------|
| `/1`        | 1.0   | Activate DJ Set scene   |
| `/1`        | 0.0   | Deactivate DJ Set scene |
| `/2`        | 1.0   | Activate Shuffle scene  |
| `/2`        | 0.0   | Deactivate Shuffle scene|

During crossfades, intermediate float values (e.g. 0.5) are sent every frame for smooth lighting transitions.

**Important:** QLC+ OSC plugin only accepts OSC float (`f`) type values. Integer values are ignored.

## Setup

1. Install QLC+: `sudo apt install qlcplus` (Raspberry Pi) or download from [qlcplus.org](https://www.qlcplus.org/)
2. Copy `ShuffleParty-OSC.qxi` to your QLC+ input profiles directory:
   - Linux: `~/.qlcplus/inputprofiles/`
   - macOS: `~/Library/Application Support/QLC+/inputprofiles/`
3. Open `ShuffleParty.qxw` in QLC+
4. In QLC+ Input/Output settings, assign the OSC plugin to Universe 1 input, port 7700
5. Select the "Shuffle Partey OSC Control" input profile
6. Switch to Operate mode

## Customizing

This workspace uses generic single-channel dimmers as placeholders. Replace them with your actual fixtures:

1. In QLC+ Design mode, remove the generic fixtures
2. Add your real fixtures (par cans, pin spots, moving heads, etc.)
3. Edit the "DJ Set" and "Shuffle" scenes to set the desired channel values for your fixtures
4. The OSC triggers from the Python app will continue to work — they control the virtual console buttons, not the fixtures directly
