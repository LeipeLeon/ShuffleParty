"""Tests for control panel functionality."""

from unittest.mock import MagicMock

from shuffle_party.display import Display
from shuffle_party.mixer import Mixer


class TestDisplayDurationChange:

    def test_change_duration_updates_remaining_when_longer(self):
        display = Display(set_duration=600)
        for _ in range(100):
            display.tick()
        # 500 remaining, change to 900 total — remaining becomes 800
        display.change_duration(900)
        assert display.set_duration == 900
        assert display.remaining_seconds == 800

    def test_change_duration_updates_remaining_when_shorter(self):
        display = Display(set_duration=900)
        for _ in range(100):
            display.tick()
        # 800 remaining, change to 600 total — remaining becomes 500
        display.change_duration(600)
        assert display.remaining_seconds == 500

    def test_change_duration_clamps_remaining_to_zero(self):
        display = Display(set_duration=900)
        for _ in range(850):
            display.tick()
        # 50 remaining, change to 30 — elapsed (850) > new duration, clamp to 0
        display.change_duration(30)
        assert display.remaining_seconds == 0

    def test_change_duration_resets_on_next_start(self):
        display = Display(set_duration=600)
        display.change_duration(900)
        display.start_timer()
        assert display.remaining_seconds == 900


class TestMasterVolume:

    def _make_mixer(self):
        backend = MagicMock()
        mixer = Mixer(
            backend=backend,
            dj_channels=[1, 2], shuffle_channels=[3, 4],
            fade_duration=1.0,
        )
        return mixer, backend

    def test_set_master_volume(self):
        mixer, backend = self._make_mixer()
        mixer.set_master_volume(0.75)
        backend.send_master_fader.assert_called_with(0.75)

    def test_set_master_volume_with_null_backend(self):
        """Should not raise with a no-op backend."""
        from shuffle_party.mixer import NullBackend
        mixer = Mixer(
            backend=NullBackend(),
            dj_channels=[1, 2], shuffle_channels=[3, 4],
            fade_duration=1.0,
        )
        mixer.set_master_volume(0.5)
