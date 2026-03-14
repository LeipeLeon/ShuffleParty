"""Shuffle Partey configuration.

Defaults are defined below. Override any value by setting the
corresponding environment variable in a .env file (sourced by start.sh).
"""

import os

# DJ set timing
SET_DURATION_SECONDS = int(os.environ.get("SET_DURATION_SECONDS", 15 * 60))
FADE_DURATION_SECONDS = float(os.environ.get("FADE_DURATION_SECONDS", 3.0))
CROSSFADE_DURATION_SECONDS = float(os.environ.get("CROSSFADE_DURATION_SECONDS", 3.0))

# Behringer XR12 mixer (OSC over WiFi/Ethernet)
XR12_HOST = os.environ.get("XR12_HOST", "192.168.1.100")
XR12_PORT = int(os.environ.get("XR12_PORT", 10023))
DJ_CHANNEL_L = int(os.environ.get("DJ_CHANNEL_L", 3))
DJ_CHANNEL_R = int(os.environ.get("DJ_CHANNEL_R", 4))
SHUFFLE_CHANNEL_L = int(os.environ.get("SHUFFLE_CHANNEL_L", 1))
SHUFFLE_CHANNEL_R = int(os.environ.get("SHUFFLE_CHANNEL_R", 2))

# OLA DMX lighting (HTTP API)
OLA_URL = os.environ.get("OLA_URL", "http://localhost:9090")
DMX_UNIVERSE = int(os.environ.get("DMX_UNIVERSE", 1))
DMX_DJ_CHANNEL = int(os.environ.get("DMX_DJ_CHANNEL", 1))
DMX_SHUFFLE_CHANNEL = int(os.environ.get("DMX_SHUFFLE_CHANNEL", 2))

# reTerminal buttons (evdev)
BUTTON_DEVICE = os.environ.get("BUTTON_DEVICE", "/dev/input/event0")
VOLUME_STEP = float(os.environ.get("VOLUME_STEP", 0.05))

# Shuffle tracks
TRACKS_DIR = os.environ.get("TRACKS_DIR", "./tracks/")
