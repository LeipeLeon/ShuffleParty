"""Loudness measurement for audio normalization.

Uses ffmpeg's loudnorm filter to measure integrated LUFS and computes
a linear gain factor to normalize tracks to a target loudness.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)

_TARGET_LUFS = -16.0


def measure_lufs(path: str) -> float | None:
    """Measure the integrated loudness (LUFS) of an audio file.

    Returns the integrated loudness in LUFS, or None if measurement fails.
    Requires ffmpeg on PATH.
    """
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
        # The JSON is in stderr, after the last '{'
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
