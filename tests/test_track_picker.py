"""Tests for shuffle track selection."""

import os
import pytest
from unittest.mock import patch

from track_picker import TrackPicker


@pytest.fixture
def tracks_dir(tmp_path):
    """Create a temp directory with some MP3 files."""
    for name in ["track_a.mp3", "track_b.mp3", "track_c.mp3"]:
        (tmp_path / name).write_text("fake mp3")
    return str(tmp_path)


class TestTrackPicker:

    def test_raises_on_empty_directory(self, tmp_path):
        with pytest.raises(RuntimeError, match="No tracks found"):
            TrackPicker(str(tmp_path))

    def test_raises_on_missing_directory(self, tmp_path):
        with pytest.raises(RuntimeError, match="No tracks found"):
            TrackPicker(str(tmp_path / "nonexistent"))

    def test_picks_a_track(self, tracks_dir):
        picker = TrackPicker(tracks_dir)
        track = picker.pick()
        assert track.endswith(".mp3")
        assert os.path.dirname(track) == tracks_dir

    def test_no_repeats_until_all_played(self, tracks_dir):
        picker = TrackPicker(tracks_dir)
        picked = [picker.pick() for _ in range(3)]
        assert len(set(picked)) == 3, "All 3 tracks should be unique"

    def test_reshuffles_after_all_played(self, tracks_dir):
        picker = TrackPicker(tracks_dir)
        # Play through all 3
        first_round = [picker.pick() for _ in range(3)]
        # Pick one more — should work (reshuffled)
        track = picker.pick()
        assert track.endswith(".mp3")

    def test_ignores_non_mp3_files(self, tmp_path):
        (tmp_path / "readme.txt").write_text("not audio")
        (tmp_path / "track.mp3").write_text("fake mp3")
        (tmp_path / "image.png").write_bytes(b"\x89PNG")
        picker = TrackPicker(str(tmp_path))
        assert len(picker._all_tracks) == 1

    def test_case_insensitive_mp3_extension(self, tmp_path):
        (tmp_path / "track.MP3").write_text("fake")
        (tmp_path / "other.Mp3").write_text("fake")
        picker = TrackPicker(str(tmp_path))
        assert len(picker._all_tracks) == 2
