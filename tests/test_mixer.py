"""Tests for XR12 mixer control."""

import pytest
from unittest.mock import patch, MagicMock

from shuffle_party.mixer import Mixer


class TestMixer:

    def _make_mixer(self, mock_xair=None, **kwargs):
        """Create a Mixer with mocked xair_api and time."""
        with patch.dict("sys.modules", {"xair_api": mock_xair or MagicMock()}):
            return Mixer(
                host=kwargs.get("host", "192.168.1.100"),
                port=kwargs.get("port", 10023),
                dj_channels=kwargs.get("dj_channels", [1, 2]),
                shuffle_channels=kwargs.get("shuffle_channels", [3, 4]),
                fade_duration=kwargs.get("fade_duration", 3.0),
            )

    def _run_fade_to_completion(self, mixer, mock_time):
        """Simulate time passing to complete a fade."""
        # Start at t=0, then jump past fade_duration
        mock_time.monotonic.return_value = 0.0
        mixer.tick()
        mock_time.monotonic.return_value = mixer.fade_duration + 0.1
        mixer.tick()

    def _calls_for_channel(self, mock_client, channel_num):
        """Extract OSC calls for a specific channel."""
        addr = f"/ch/{channel_num:02d}/mix/fader"
        return [c for c in mock_client.send.call_args_list if c.args[0] == addr]

    def test_fade_out_starts_and_completes(self):
        mock_xair = MagicMock()
        mock_client = MagicMock()
        mock_xair.connect.return_value = mock_client
        mixer = self._make_mixer(mock_xair)

        with patch("shuffle_party.mixer.time") as mock_time:
            mock_time.monotonic.return_value = 0.0
            mixer.fade_out()
            assert mixer.is_fading
            assert mixer.dj_level == pytest.approx(1.0)
            assert mixer.shuffle_level == pytest.approx(0.0)

            mock_time.monotonic.return_value = mixer.fade_duration + 0.1
            mixer.tick()
            assert not mixer.is_fading
            assert mixer.dj_level == pytest.approx(0.0)
            assert mixer.shuffle_level == pytest.approx(1.0)

    def test_fade_in_starts_and_completes(self):
        mock_xair = MagicMock()
        mock_client = MagicMock()
        mock_xair.connect.return_value = mock_client
        mixer = self._make_mixer(mock_xair)

        with patch("shuffle_party.mixer.time") as mock_time:
            mock_time.monotonic.return_value = 0.0
            mixer.fade_in()
            assert mixer.dj_level == pytest.approx(0.0)
            assert mixer.shuffle_level == pytest.approx(1.0)

            mock_time.monotonic.return_value = mixer.fade_duration + 0.1
            mixer.tick()
            assert mixer.dj_level == pytest.approx(1.0)
            assert mixer.shuffle_level == pytest.approx(0.0)

    def test_fade_midpoint_has_intermediate_values(self):
        mock_xair = MagicMock()
        mock_client = MagicMock()
        mock_xair.connect.return_value = mock_client
        mixer = self._make_mixer(mock_xair)

        with patch("shuffle_party.mixer.time") as mock_time:
            mock_time.monotonic.return_value = 0.0
            mixer.fade_out()

            mock_time.monotonic.return_value = mixer.fade_duration / 2
            mixer.tick()
            assert mixer.dj_level == pytest.approx(0.5)
            assert mixer.shuffle_level == pytest.approx(0.5)

    def test_fade_sends_to_all_four_channels(self):
        mock_xair = MagicMock()
        mock_client = MagicMock()
        mock_xair.connect.return_value = mock_client
        mixer = self._make_mixer(mock_xair)

        with patch("shuffle_party.mixer.time") as mock_time:
            mock_time.monotonic.return_value = 0.0
            mixer.fade_out()

        addresses = set(c.args[0] for c in mock_client.send.call_args_list)
        assert addresses == {
            "/ch/01/mix/fader", "/ch/02/mix/fader",
            "/ch/03/mix/fader", "/ch/04/mix/fader",
        }

    def test_channel_numbers_are_zero_padded(self):
        mock_xair = MagicMock()
        mock_client = MagicMock()
        mock_xair.connect.return_value = mock_client
        mixer = self._make_mixer(mock_xair, dj_channels=[5, 6], shuffle_channels=[9, 10])

        with patch("shuffle_party.mixer.time") as mock_time:
            mock_time.monotonic.return_value = 0.0
            mixer.fade_out()

        addresses = set(c.args[0] for c in mock_client.send.call_args_list)
        assert addresses == {
            "/ch/05/mix/fader", "/ch/06/mix/fader",
            "/ch/09/mix/fader", "/ch/10/mix/fader",
        }

    def test_graceful_degradation_when_xr12_unreachable(self):
        """Mixer should not crash when XR12 is unreachable."""
        mock_xair = MagicMock()
        mock_xair.connect.side_effect = ConnectionError("unreachable")

        with patch.dict("sys.modules", {"xair_api": mock_xair}):
            mixer = Mixer(
                host="x", port=1,
                dj_channels=[1, 2], shuffle_channels=[3, 4],
                fade_duration=1.0,
            )

        with patch("shuffle_party.mixer.time") as mock_time:
            mock_time.monotonic.return_value = 0.0
            mixer.fade_out()
            mock_time.monotonic.return_value = 2.0
            mixer.tick()
            mixer.fade_in()
            mock_time.monotonic.return_value = 4.0
            mixer.tick()

    def test_tick_does_nothing_when_not_fading(self):
        mixer = self._make_mixer()
        mixer.tick()  # should not raise
        assert not mixer.is_fading
