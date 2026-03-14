#!/usr/bin/env python3
"""Analyze tracks, detect fade-in and fade-out points, set tags, and generate verification images.

For each MP3, decodes audio via ffmpeg, computes RMS in 0.5s windows, and finds:
  - FADEIN_MS:  where the intro reaches normal level (scan from start forward)
  - FADEOUT_MS: where the outro drops below normal level (scan from end backward)

Usage:
    python scripts/auto_fadeout.py tracks/*.mp3
    python scripts/auto_fadeout.py tracks/*.mp3 --drop 6     # dB below typical level, default 6
    python scripts/auto_fadeout.py tracks/*.mp3 --dry-run   # preview only, don't write tags
"""

import math
import os
import struct
import subprocess
import sys

from mutagen.id3 import TXXX
from mutagen.mp3 import MP3
from PIL import Image, ImageDraw, ImageFont


# --- Audio analysis ---

SAMPLE_RATE = 16000  # mono, 16-bit
WINDOW_SEC = 0.5
WINDOW_SAMPLES = int(SAMPLE_RATE * WINDOW_SEC)


def decode_audio(path: str) -> list[int]:
    """Decode MP3 to mono 16-bit samples via ffmpeg."""
    result = subprocess.run(
        [
            "ffmpeg", "-i", path,
            "-f", "s16le", "-ac", "1", "-ar", str(SAMPLE_RATE),
            "-v", "quiet", "-",
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for {path}")
    raw = result.stdout
    return list(struct.unpack(f"<{len(raw) // 2}h", raw))


def compute_rms_windows(samples: list[int]) -> list[float]:
    """Compute RMS in dB for fixed-size windows."""
    windows = []
    for start in range(0, len(samples), WINDOW_SAMPLES):
        chunk = samples[start:start + WINDOW_SAMPLES]
        if len(chunk) < WINDOW_SAMPLES // 2:
            break
        ms = sum(s * s for s in chunk) / len(chunk)
        rms_db = 10 * math.log10(ms / (32768.0 ** 2) + 1e-10)
        windows.append(rms_db)
    return windows


def find_fadeout_point(rms_windows: list[float], drop_db: float) -> int | None:
    """Find the window index where the track starts fading out.

    Computes the track's typical loudness, then scans from the end backwards
    to find where the level drops below (typical - drop_db) and stays there.
    Returns the window index where the fadeout begins, or None.

    drop_db is a positive number (e.g. 6 means "6 dB below normal").
    """
    n = len(rms_windows)
    if n < 10:
        return None

    # Compute the track's typical level: median of the top 60% of windows
    # (ignoring quiet intros/breaks)
    sorted_rms = sorted(rms_windows, reverse=True)
    top_count = max(1, int(n * 0.6))
    typical_db = sorted_rms[top_count // 2]

    threshold = typical_db - abs(drop_db)

    # Smooth RMS with a 5-window moving average to ignore brief dips
    smoothed = []
    half_w = 2
    for i in range(n):
        lo = max(0, i - half_w)
        hi = min(n, i + half_w + 1)
        smoothed.append(sum(rms_windows[lo:hi]) / (hi - lo))

    # Scan from the end backwards: find the last window that's at or above threshold
    last_loud = None
    for i in range(n - 1, -1, -1):
        if smoothed[i] >= threshold:
            last_loud = i
            break

    if last_loud is None:
        return None

    # The fadeout cue goes at last_loud (where the track is still at normal level)
    # Don't set a cue in the first 50% of the track
    min_window = int(n * 0.5)
    if last_loud < min_window:
        return None

    # Don't bother if the "fadeout" is less than 1.5 seconds (just a hard ending)
    tail_windows = n - last_loud
    if tail_windows < 3:  # 3 * 0.5s = 1.5s
        return None

    return last_loud


def find_fadein_point(rms_windows: list[float], drop_db: float) -> int | None:
    """Find the window index where the track's intro reaches normal level.

    Mirror of find_fadeout_point: scans from the start forward to find the
    first window where the smoothed level reaches (typical - drop_db).
    Returns the window index, or None if no intro detected.

    drop_db is a positive number (e.g. 6 means "6 dB below normal").
    """
    n = len(rms_windows)
    if n < 10:
        return None

    # Compute the track's typical level (same as fadeout)
    sorted_rms = sorted(rms_windows, reverse=True)
    top_count = max(1, int(n * 0.6))
    typical_db = sorted_rms[top_count // 2]

    threshold = typical_db - abs(drop_db)

    # Smooth RMS with a 5-window moving average
    smoothed = []
    half_w = 2
    for i in range(n):
        lo = max(0, i - half_w)
        hi = min(n, i + half_w + 1)
        smoothed.append(sum(rms_windows[lo:hi]) / (hi - lo))

    # Scan from start: find the first window at or above threshold
    first_loud = None
    for i in range(n):
        if smoothed[i] >= threshold:
            first_loud = i
            break

    if first_loud is None:
        return None

    # Don't set a cue past 50% of the track
    if first_loud > int(n * 0.5):
        return None

    # Don't bother if the "intro" is less than 1.5 seconds
    if first_loud < 3:  # 3 * 0.5s = 1.5s
        return None

    return first_loud


# --- Image generation ---

IMG_WIDTH = 1200
IMG_HEIGHT = 200
BG_COLOR = (26, 26, 46)
WAVE_COLOR = (74, 158, 255)
FADEOUT_COLOR = (255, 136, 0)
FADEIN_COLOR = (0, 200, 120)
THRESHOLD_COLOR = (80, 80, 100)
TEXT_COLOR = (200, 200, 200)


def generate_image(
    path: str,
    rms_windows: list[float],
    fadein_window: int | None,
    fadeout_window: int | None,
    drop_db: float,
    out_path: str,
) -> None:
    """Draw a waveform with RMS levels, threshold line, and cue markers."""
    img = Image.new("RGB", (IMG_WIDTH, IMG_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    n = len(rms_windows)
    if n == 0:
        img.save(out_path)
        return

    # Map dB range to pixel height. Typical range: -60 dB to 0 dB
    db_floor = -60.0
    db_ceil = 0.0
    bar_w = IMG_WIDTH / n
    margin_top = 24
    margin_bottom = 4
    plot_h = IMG_HEIGHT - margin_top - margin_bottom

    def db_to_y(db: float) -> int:
        clamped = max(db_floor, min(db_ceil, db))
        frac = (clamped - db_floor) / (db_ceil - db_floor)
        return int(margin_top + plot_h * (1.0 - frac))

    # Draw threshold line (typical level - drop_db)
    sorted_rms = sorted(rms_windows, reverse=True)
    top_count = max(1, int(n * 0.6))
    typical_db = sorted_rms[top_count // 2]
    thresh_y = db_to_y(typical_db - abs(drop_db))
    draw.line([(0, thresh_y), (IMG_WIDTH, thresh_y)], fill=THRESHOLD_COLOR, width=1)

    # Draw RMS bars (dim bars outside fadein..fadeout range)
    for i, db in enumerate(rms_windows):
        x0 = int(i * bar_w)
        x1 = int((i + 1) * bar_w) - 1
        y = db_to_y(db)
        bottom = db_to_y(db_floor)
        dimmed = False
        if fadein_window is not None and i < fadein_window:
            dimmed = True
        if fadeout_window is not None and i >= fadeout_window:
            dimmed = True
        color = (60, 100, 160) if dimmed else WAVE_COLOR
        draw.rectangle([x0, y, x1, bottom], fill=color)

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 13)
    except Exception:
        font = ImageFont.load_default()

    # Draw fadein cue marker
    if fadein_window is not None:
        cue_x = int(fadein_window * bar_w)
        draw.line([(cue_x, 0), (cue_x, IMG_HEIGHT)], fill=FADEIN_COLOR, width=2)
        cue_sec = fadein_window * WINDOW_SEC
        cue_label = f"{int(cue_sec) // 60}:{int(cue_sec) % 60:02d}"
        draw.text((cue_x + 4, 2), cue_label, fill=FADEIN_COLOR, font=font)

    # Draw fadeout cue marker
    if fadeout_window is not None:
        cue_x = int(fadeout_window * bar_w)
        draw.line([(cue_x, 0), (cue_x, IMG_HEIGHT)], fill=FADEOUT_COLOR, width=2)
        cue_sec = fadeout_window * WINDOW_SEC
        cue_label = f"{int(cue_sec) // 60}:{int(cue_sec) % 60:02d}"
        draw.text((cue_x + 4, 2), cue_label, fill=FADEOUT_COLOR, font=font)

    # Title
    title = os.path.basename(path)
    try:
        title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
    except Exception:
        title_font = ImageFont.load_default()
    draw.text((4, 2), title, fill=TEXT_COLOR, font=title_font)

    img.save(out_path)


# --- Tag writing ---

def set_cue_tag(path: str, desc: str, ms: int) -> None:
    """Write a TXXX cue tag (FADEIN_MS or FADEOUT_MS)."""
    audio = MP3(path)
    if audio.tags is None:
        audio.add_tags()
    to_remove = [k for k in audio.tags if k.startswith("TXXX:") and k.upper().endswith(desc)]
    for k in to_remove:
        del audio.tags[k]
    audio.tags.add(TXXX(encoding=3, desc=desc, text=[str(ms)]))
    audio.save()


# --- Main ---

def main() -> None:
    args = sys.argv[1:]

    drop_db = 6.0
    dry_run = False
    files = []

    i = 0
    while i < len(args):
        if args[i] == "--drop" and i + 1 < len(args):
            drop_db = float(args[i + 1])
            i += 2
        elif args[i] == "--dry-run":
            dry_run = True
            i += 1
        elif args[i].endswith(".mp3"):
            files.append(args[i])
            i += 1
        else:
            i += 1

    if not files:
        print(__doc__)
        sys.exit(1)

    out_dir = "fadeout_preview"
    os.makedirs(out_dir, exist_ok=True)

    for path in sorted(files):
        name = os.path.basename(path)
        audio = MP3(path)
        duration_ms = int(audio.info.length * 1000)

        try:
            samples = decode_audio(path)
        except RuntimeError as e:
            print(f"SKIP {name}: {e}")
            continue

        rms = compute_rms_windows(samples)
        fadein_idx = find_fadein_point(rms, drop_db)
        fadeout_idx = find_fadeout_point(rms, drop_db)

        dur_str = f"{duration_ms // 60000}:{(duration_ms // 1000) % 60:02d}"
        parts = []

        if fadein_idx is not None:
            in_ms = int(fadein_idx * WINDOW_SEC * 1000)
            in_str = f"{in_ms // 60000}:{(in_ms // 1000) % 60:02d}"
            parts.append(f"fadein at {in_str}")
            if not dry_run:
                set_cue_tag(path, "FADEIN_MS", in_ms)

        if fadeout_idx is not None:
            out_ms = int(fadeout_idx * WINDOW_SEC * 1000)
            out_str = f"{out_ms // 60000}:{(out_ms // 1000) % 60:02d}"
            parts.append(f"fadeout at {out_str}")
            if not dry_run:
                set_cue_tag(path, "FADEOUT_MS", out_ms)

        if parts:
            print(f"{name}: {', '.join(parts)} / {dur_str}")
        else:
            print(f"{name}: no cues detected, skipping")

        img_name = os.path.splitext(name)[0] + ".png"
        img_path = os.path.join(out_dir, img_name)
        generate_image(path, rms, fadein_idx, fadeout_idx, drop_db, img_path)

    print(f"\nPreview images saved to {out_dir}/")


if __name__ == "__main__":
    main()
