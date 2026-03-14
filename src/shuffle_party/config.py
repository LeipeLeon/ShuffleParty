"""Shuffle Partey configuration.

Edit these values to match your setup. All settings are plain Python
constants — no parsing, no env vars, no YAML.
"""

# DJ set timing
SET_DURATION_SECONDS = 15 * 60  # 15 minutes per DJ set
FADE_DURATION_SECONDS = 3.0    # crossfade length in seconds

# Behringer XR12 mixer (OSC over WiFi/Ethernet)
XR12_HOST = "192.168.1.100"
XR12_PORT = 10023
DJ_CHANNEL = 1  # mixer channel number for DJ input (1–12)

# QLC+ lighting (OSC)
QLC_HOST = "127.0.0.1"
QLC_PORT = 7700

# Shuffle tracks
TRACKS_DIR = "./tracks/"
