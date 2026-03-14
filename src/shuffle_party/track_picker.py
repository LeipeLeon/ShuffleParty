"""Shuffle track selection — random, no repeats until all played."""

import os
import random


class TrackPicker:
    """Picks shuffle tracks from a directory, no repeats until all have played."""

    def __init__(self, tracks_dir: str) -> None:
        self.tracks_dir = tracks_dir
        all_tracks = self._scan_tracks()
        if not all_tracks:
            raise RuntimeError(f"No tracks found in {tracks_dir}")
        self._all_tracks = all_tracks
        self._remaining: list[str] = []
        self._reshuffle()

    def _scan_tracks(self) -> list[str]:
        """Find all MP3 files in the tracks directory."""
        if not os.path.isdir(self.tracks_dir):
            return []
        return sorted(
            os.path.join(self.tracks_dir, f)
            for f in os.listdir(self.tracks_dir)
            if f.lower().endswith(".mp3")
        )

    def _reshuffle(self) -> None:
        """Refill and shuffle the remaining tracks list."""
        self._remaining = list(self._all_tracks)
        random.shuffle(self._remaining)

    def pick(self) -> str:
        """Pick the next shuffle track. Reshuffles when all have been played."""
        if not self._remaining:
            self._reshuffle()
        return self._remaining.pop()
