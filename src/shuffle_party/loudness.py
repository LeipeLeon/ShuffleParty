"""Loudness normalization for the XR12 mixer.

Reads the LUFS ID3 tag if present (written by auto_fadeout.py), otherwise
falls back to measuring with ffmpeg's loudnorm filter. Converts the
measured LUFS to an XR12 fader position using the Behringer fader law.

Target: shuffle tracks play at -10 LUFS when the fader is at 0 dB.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)

_TARGET_LUFS = -10.0

# Behringer XR12/X-Air fader law (piecewise linear in dB):
#   position 0.0    = -inf
#   position 0.0625 = -60 dB
#   position 0.25   = -30 dB
#   position 0.5    = -10 dB
#   position 0.75   =   0 dB
#   position 1.0    = +10 dB


def db_to_fader(db: float) -> float:
    """Convert a dB value to an XR12 fader position (0.0–1.0)."""
    if db <= -90:
        return 0.0
    if db <= -60:
        return (db + 90) / 480       # -90..-60 → 0.0..0.0625
    if db <= -30:
        return (db + 70) / 160       # -60..-30 → 0.0625..0.25
    if db <= -10:
        return (db + 50) / 80        # -30..-10 → 0.25..0.5
    if db <= 10:
        return (db + 30) / 40        # -10..+10 → 0.5..1.0
    return 1.0


def fader_to_db(pos: float) -> float:
    """Convert an XR12 fader position (0.0–1.0) to dB."""
    if pos <= 0.0:
        return -90.0
    if pos <= 0.0625:
        return pos * 480 - 90        # 0.0..0.0625 → -90..-60
    if pos <= 0.25:
        return pos * 160 - 70        # 0.0625..0.25 → -60..-30
    if pos <= 0.5:
        return pos * 80 - 50         # 0.25..0.5 → -30..-10
    return pos * 40 - 30             # 0.5..1.0 → -10..+10


def _read_lufs_tag(path: str) -> float | None:
    """Read the LUFS value from the ID3 TXXX:LUFS tag."""
    try:
        from mutagen.mp3 import MP3

        audio = MP3(path)
        if audio.tags is None:
            return None
        for key in audio.tags:
            if key.startswith("TXXX:") and "LUFS" in key.upper():
                raw = int(audio.tags[key].text[0])
                return raw / 10.0  # stored as int x10
    except Exception:
        pass
    return None


def measure_lufs(path: str) -> float | None:
    """Get the integrated loudness (LUFS) of an audio file.

    Reads the LUFS ID3 tag if available (instant), otherwise measures
    with ffmpeg (~5s per track). Returns LUFS or None on failure.
    """
    # Try cached tag first
    cached = _read_lufs_tag(path)
    if cached is not None:
        logger.debug("LUFS from tag: %.1f for %s", cached, path)
        return cached

    # Fall back to ffmpeg measurement
    if not shutil.which("ffmpeg"):
        logger.debug("ffmpeg not found — loudness normalization disabled.")
        return None

    try:
        result = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-nostats",
                "-i", path,
                "-af", "loudnorm=print_format=json",
                "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=30,
        )
        output = result.stderr
        json_start = output.rfind("{")
        json_end = output.rfind("}") + 1
        if json_start < 0 or json_end <= json_start:
            return None
        data = json.loads(output[json_start:json_end])
        lufs = float(data["input_i"])
        logger.debug("Measured %s: %.1f LUFS", path, lufs)
        return lufs
    except Exception as e:
        logger.debug("LUFS measurement failed for %s — %r", path, e)
        return None


def fader_for_target(measured_lufs: float, target_lufs: float = _TARGET_LUFS) -> float:
    """Compute the XR12 fader position to normalize a track to the target LUFS.

    If a track is at -14 LUFS, the fader goes to 0 dB (0.75).
    Louder tracks get a lower fader position, quieter tracks get a higher one.
    Clamped to the XR12's +10 dB maximum.
    """
    gain_db = target_lufs - measured_lufs
    return db_to_fader(gain_db)
