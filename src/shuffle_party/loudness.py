"""Loudness measurement for audio normalization.

Reads the LUFS ID3 tag if present (written by auto_fadeout.py), otherwise
falls back to measuring with ffmpeg's loudnorm filter. Computes a linear
gain factor to normalize tracks to a target loudness.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)

_TARGET_LUFS = -16.0


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


def gain_for_target(measured_lufs: float, target_lufs: float = _TARGET_LUFS) -> float:
    """Compute a linear gain factor to reach the target loudness.

    Returns a value between 0.0 and 1.0 (never boosts above unity).
    """
    diff_db = target_lufs - measured_lufs
    linear = 10 ** (diff_db / 20.0)
    return min(1.0, max(0.0, linear))
