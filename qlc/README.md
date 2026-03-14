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

Scene fade times are set to 0 — the Python app handles crossfading by sending intermediate float values every frame.

## OSC Control

The Python app sends OSC **float** messages (0.0–1.0) to QLC+ on port 7700 (configurable via `QLC_PORT` in `.env`):

| OSC Address | Value | Effect                  |
|-------------|-------|-------------------------|
| `/dj`       | 1.0   | DJ Set scene full       |
| `/dj`       | 0.0   | DJ Set scene off        |
| `/shuffle`  | 1.0   | Shuffle scene full      |
| `/shuffle`  | 0.0   | Shuffle scene off       |

During crossfades, intermediate float values (e.g. 0.5) are sent every frame for smooth lighting transitions.

**Note:** The OSC paths `/dj` and `/shuffle` are intentionally different lengths to avoid a [known Qt6 hash collision bug on macOS](https://www.qlcplus.org/forum/viewtopic.php?p=81950) where same-length paths map to the same channel.

**Important:** QLC+ OSC plugin only accepts OSC float (`f`) type values. Integer values are ignored.

## How QLC+ Maps OSC Paths

QLC+ does **not** use the OSC path directly as a channel number. It computes a CRC16-CCITT hash of the path string:

| OSC Path   | CRC16 Hash | QLC+ Channel |
|------------|-----------|--------------|
| `/dj`      | 27753     | 27753        |
| `/shuffle` | 34360     | 34360        |

The input profile (`ShuffleParty-OSC.qxi`) and workspace (`ShuffleParty.qxw`) already contain the correct hash values. If you change the OSC paths in the Python code, you must recalculate the hashes.

## Setup

1. Install QLC+: `sudo apt install qlcplus` (Raspberry Pi) or download from [qlcplus.org](https://www.qlcplus.org/)
2. Copy `ShuffleParty-OSC.qxi` to your QLC+ input profiles directory:
   - Linux: `~/.qlcplus/inputprofiles/`
   - macOS: `~/Library/Application Support/QLC+/inputprofiles/`
3. Open `ShuffleParty.qxw` in QLC+
4. In QLC+ Input/Output settings, verify the OSC plugin is assigned to Universe 1 input on port 7700
5. Verify the "Shuffle Partey OSC Control" input profile is selected
6. Switch to **Operate** mode

## Verifying OSC Reception

Send a test message from the command line:

```bash
uv run python -c "
from pythonosc.udp_client import SimpleUDPClient
c = SimpleUDPClient('127.0.0.1', 7700)
c.send_message('/dj', 1.0)
print('Sent /dj = 1.0')
"
```

In QLC+, check the Input/Output Monitor to see if the message arrives on channel 27753.

## Customizing

This workspace uses generic single-channel dimmers as placeholders. Replace them with your actual fixtures:

1. In QLC+ Design mode, remove the generic fixtures
2. Add your real fixtures (par cans, pin spots, moving heads, etc.)
3. Edit the "DJ Set" and "Shuffle" scenes to set the desired channel values for your fixtures
4. The OSC triggers from the Python app will continue to work — they control the virtual console sliders, not the fixtures directly
