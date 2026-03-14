#!/usr/bin/env python3
"""Set or show the FADEOUT_MS tag on MP3 files.

Usage:
    # Show current fadeout cue (if any)
    python scripts/set_fadeout.py tracks/song.mp3

    # Set fadeout at 3 minutes 30 seconds
    python scripts/set_fadeout.py tracks/song.mp3 3:30

    # Set fadeout at 210000 milliseconds
    python scripts/set_fadeout.py tracks/song.mp3 210000

    # Remove fadeout cue
    python scripts/set_fadeout.py tracks/song.mp3 --remove

    # Batch: show all tracks that have a fadeout cue
    python scripts/set_fadeout.py tracks/*.mp3
"""

import sys

from mutagen.id3 import ID3, TXXX
from mutagen.mp3 import MP3


def parse_time(value: str) -> int:
    """Parse a time string (mm:ss, h:mm:ss, or raw ms) into milliseconds."""
    if ":" in value:
        parts = value.split(":")
        if len(parts) == 2:
            m, s = parts
            return int(m) * 60_000 + int(float(s) * 1000)
        elif len(parts) == 3:
            h, m, s = parts
            return int(h) * 3_600_000 + int(m) * 60_000 + int(float(s) * 1000)
    return int(value)


def format_time(ms: int) -> str:
    """Format milliseconds as mm:ss.s"""
    total_s = ms / 1000
    m = int(total_s) // 60
    s = total_s - m * 60
    return f"{m}:{s:04.1f}"


def get_fadeout(tags: ID3) -> int | None:
    """Read FADEOUT_MS from TXXX tags. Returns ms or None."""
    for key in tags:
        if key.startswith("TXXX:") and "FADEOUT" in key.upper():
            try:
                return int(tags[key].text[0])
            except (ValueError, IndexError):
                pass
    return None


def show(path: str) -> None:
    """Show fadeout cue and track duration."""
    audio = MP3(path)
    duration_ms = int(audio.info.length * 1000)
    tags = audio.tags or ID3()
    fadeout = get_fadeout(tags)
    if fadeout is not None:
        print(f"{path}: fadeout at {format_time(fadeout)} (duration {format_time(duration_ms)})")
    else:
        print(f"{path}: no fadeout cue (duration {format_time(duration_ms)})")


def set_fadeout(path: str, ms: int) -> None:
    """Write FADEOUT_MS tag."""
    audio = MP3(path)
    duration_ms = int(audio.info.length * 1000)
    if ms >= duration_ms:
        print(f"Warning: {ms}ms is past track end ({format_time(duration_ms)})", file=sys.stderr)
        return
    if audio.tags is None:
        audio.add_tags()
    # Remove existing FADEOUT tags
    to_remove = [k for k in audio.tags if k.startswith("TXXX:") and "FADEOUT" in k.upper()]
    for k in to_remove:
        del audio.tags[k]
    audio.tags.add(TXXX(encoding=3, desc="FADEOUT_MS", text=[str(ms)]))
    audio.save()
    print(f"{path}: fadeout set to {format_time(ms)} (duration {format_time(duration_ms)})")


def remove_fadeout(path: str) -> None:
    """Remove FADEOUT_MS tag."""
    audio = MP3(path)
    if audio.tags is None:
        print(f"{path}: no tags")
        return
    to_remove = [k for k in audio.tags if k.startswith("TXXX:") and "FADEOUT" in k.upper()]
    if not to_remove:
        print(f"{path}: no fadeout cue to remove")
        return
    for k in to_remove:
        del audio.tags[k]
    audio.save()
    print(f"{path}: fadeout cue removed")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    args = sys.argv[1:]

    # Check for --remove flag
    remove = "--remove" in args
    if remove:
        args.remove("--remove")

    if not args:
        print("No files specified", file=sys.stderr)
        sys.exit(1)

    # If only file paths (no time argument), show mode
    # Heuristic: last non-file arg is the time value
    files = []
    time_value = None
    for arg in args:
        if arg.endswith(".mp3"):
            files.append(arg)
        else:
            time_value = arg

    if not files:
        print("No .mp3 files specified", file=sys.stderr)
        sys.exit(1)

    if remove:
        for f in files:
            remove_fadeout(f)
    elif time_value is not None:
        ms = parse_time(time_value)
        for f in files:
            set_fadeout(f, ms)
    else:
        for f in files:
            show(f)


if __name__ == "__main__":
    main()
