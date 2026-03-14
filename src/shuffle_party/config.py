"""Shuffle Partey configuration.

Defaults are defined below. Override any value by setting the
corresponding environment variable in a .env file (sourced by start.sh).
"""

import os

# DJ set timing
SET_DURATION_SECONDS = int(os.environ.get("SET_DURATION_SECONDS", 15 * 60))
FADE_DURATION_SECONDS = float(os.environ.get("FADE_DURATION_SECONDS", 3.0))

# Behringer XR12 mixer (OSC over WiFi/Ethernet)
XR12_HOST = os.environ.get("XR12_HOST", "192.168.1.100")
XR12_PORT = int(os.environ.get("XR12_PORT", 10023))
DJ_CHANNEL_L = int(os.environ.get("DJ_CHANNEL_L", 1))  # DJ left channel
DJ_CHANNEL_R = int(os.environ.get("DJ_CHANNEL_R", 2))  # DJ right channel
SHUFFLE_CHANNEL_L = int(os.environ.get("SHUFFLE_CHANNEL_L", 3))  # shuffle left channel
SHUFFLE_CHANNEL_R = int(os.environ.get("SHUFFLE_CHANNEL_R", 4))  # shuffle right channel

# QLC+ lighting (OSC)
QLC_HOST = os.environ.get("QLC_HOST", "127.0.0.1")
QLC_PORT = int(os.environ.get("QLC_PORT", 7700))

# Shuffle tracks
TRACKS_DIR = os.environ.get("TRACKS_DIR", "./tracks/")
