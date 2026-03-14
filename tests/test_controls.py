"""Tests for control panel functionality."""

from unittest.mock import MagicMock, patch

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

    def _make_mixer(self, mock_xair):
        mock_client = MagicMock()
        mock_xair.connect.return_value = mock_client
        with patch.dict("sys.modules", {"xair_api": mock_xair}):
            with patch("shuffle_party.mixer.time"):
                mixer = Mixer(
                    host="x", port=1,
                    dj_channels=[1, 2], shuffle_channels=[3, 4],
                    fade_duration=1.0,
                )
        return mixer, mock_client

    def test_set_master_volume(self):
        mock_xair = MagicMock()
        mixer, client = self._make_mixer(mock_xair)
        mixer.set_master_volume(0.75)
        client.send.assert_called_with("/lr/mix/fader", 0.75)

    def test_set_master_volume_without_connection(self):
        mock_xair = MagicMock()
        mock_xair.connect.side_effect = ConnectionError()
        with patch.dict("sys.modules", {"xair_api": mock_xair}):
            mixer = Mixer(
                host="x", port=1,
                dj_channels=[1, 2], shuffle_channels=[3, 4],
                fade_duration=1.0,
            )
        # Should not raise
        mixer.set_master_volume(0.5)
