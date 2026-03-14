"""Tests for XR12 mixer control."""

import pytest
from unittest.mock import patch, MagicMock, call

from shuffle_party.mixer import Mixer


class TestMixer:

    def _make_mixer(self, mock_xair=None):
        """Create a Mixer with mocked xair_api."""
        with patch.dict("sys.modules", {"xair_api": mock_xair or MagicMock()}):
            with patch("shuffle_party.mixer.time"):
                return Mixer(
                    host="192.168.1.100", port=10023,
                    dj_channels=[1, 2], shuffle_channel=3,
                    fade_duration=3.0,
                )

    def _calls_for_channel(self, mock_client, channel_num):
        """Extract OSC calls for a specific channel."""
        addr = f"/ch/{channel_num:02d}/mix/fader"
        return [c for c in mock_client.send.call_args_list if c.args[0] == addr]

    def test_fade_out_dj_decreases(self):
        mock_xair = MagicMock()
        mock_client = MagicMock()
        mock_xair.connect.return_value = mock_client
        mixer = self._make_mixer(mock_xair)

        with patch("shuffle_party.mixer.time"):
            mixer.fade_out()

        values = [c.args[1] for c in self._calls_for_channel(mock_client, 1)]
        assert values[0] == pytest.approx(1.0)
        assert values[-1] == pytest.approx(0.0)
        for i in range(1, len(values)):
            assert values[i] <= values[i - 1]

    def test_fade_out_shuffle_increases(self):
        mock_xair = MagicMock()
        mock_client = MagicMock()
        mock_xair.connect.return_value = mock_client
        mixer = self._make_mixer(mock_xair)

        with patch("shuffle_party.mixer.time"):
            mixer.fade_out()

        values = [c.args[1] for c in self._calls_for_channel(mock_client, 3)]
        assert values[0] == pytest.approx(0.0)
        assert values[-1] == pytest.approx(1.0)
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1]

    def test_fade_in_dj_increases(self):
        mock_xair = MagicMock()
        mock_client = MagicMock()
        mock_xair.connect.return_value = mock_client
        mixer = self._make_mixer(mock_xair)

        with patch("shuffle_party.mixer.time"):
            mixer.fade_in()

        values = [c.args[1] for c in self._calls_for_channel(mock_client, 1)]
        assert values[0] == pytest.approx(0.0)
        assert values[-1] == pytest.approx(1.0)

    def test_fade_in_shuffle_decreases(self):
        mock_xair = MagicMock()
        mock_client = MagicMock()
        mock_xair.connect.return_value = mock_client
        mixer = self._make_mixer(mock_xair)

        with patch("shuffle_party.mixer.time"):
            mixer.fade_in()

        values = [c.args[1] for c in self._calls_for_channel(mock_client, 3)]
        assert values[0] == pytest.approx(1.0)
        assert values[-1] == pytest.approx(0.0)

    def test_fade_sends_to_all_three_channels(self):
        mock_xair = MagicMock()
        mock_client = MagicMock()
        mock_xair.connect.return_value = mock_client
        mixer = self._make_mixer(mock_xair)

        with patch("shuffle_party.mixer.time"):
            mixer.fade_out()

        addresses = set(c.args[0] for c in mock_client.send.call_args_list)
        assert addresses == {"/ch/01/mix/fader", "/ch/02/mix/fader", "/ch/03/mix/fader"}

    def test_channel_numbers_are_zero_padded(self):
        mock_xair = MagicMock()
        mock_client = MagicMock()
        mock_xair.connect.return_value = mock_client

        with patch.dict("sys.modules", {"xair_api": mock_xair}):
            with patch("shuffle_party.mixer.time"):
                mixer = Mixer(
                    host="x", port=1,
                    dj_channels=[5, 6], shuffle_channel=9,
                    fade_duration=1.0,
                )
                mixer.fade_out()

        addresses = set(c.args[0] for c in mock_client.send.call_args_list)
        assert addresses == {"/ch/05/mix/fader", "/ch/06/mix/fader", "/ch/09/mix/fader"}

    def test_graceful_degradation_when_xr12_unreachable(self):
        """Mixer should not crash when XR12 is unreachable."""
        mock_xair = MagicMock()
        mock_xair.connect.side_effect = ConnectionError("unreachable")

        with patch.dict("sys.modules", {"xair_api": mock_xair}):
            mixer = Mixer(
                host="x", port=1,
                dj_channels=[1, 2], shuffle_channel=3,
                fade_duration=1.0,
            )

        # Should not raise
        mixer.fade_out()
        mixer.fade_in()
