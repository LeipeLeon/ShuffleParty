"""Tests for XR12 mixer control."""

import pytest
from unittest.mock import patch, MagicMock, call

from mixer import Mixer


class TestMixer:

    def _make_mixer(self, mock_xair=None):
        """Create a Mixer with mocked xair_api."""
        with patch.dict("sys.modules", {"xair_api": mock_xair or MagicMock()}):
            with patch("mixer.time"):
                return Mixer(host="192.168.1.100", port=10023, channel=1, fade_duration=3.0)

    def test_fade_out_sends_decreasing_values(self):
        mock_xair = MagicMock()
        mock_client = MagicMock()
        mock_xair.connect.return_value = mock_client
        mixer = self._make_mixer(mock_xair)

        with patch("mixer.time"):
            mixer.fade_out()

        calls = mock_client.send.call_args_list
        values = [c.args[1] for c in calls]
        assert values[0] == pytest.approx(1.0)
        assert values[-1] == pytest.approx(0.0)
        # Values should be monotonically decreasing
        for i in range(1, len(values)):
            assert values[i] <= values[i - 1]

    def test_fade_in_sends_increasing_values(self):
        mock_xair = MagicMock()
        mock_client = MagicMock()
        mock_xair.connect.return_value = mock_client
        mixer = self._make_mixer(mock_xair)

        with patch("mixer.time"):
            mixer.fade_in()

        calls = mock_client.send.call_args_list
        values = [c.args[1] for c in calls]
        assert values[0] == pytest.approx(0.0)
        assert values[-1] == pytest.approx(1.0)
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1]

    def test_fade_sends_to_correct_osc_address(self):
        mock_xair = MagicMock()
        mock_client = MagicMock()
        mock_xair.connect.return_value = mock_client
        mixer = self._make_mixer(mock_xair)

        with patch("mixer.time"):
            mixer.fade_out()

        for c in mock_client.send.call_args_list:
            assert c.args[0] == "/ch/01/mix/fader"

    def test_channel_number_is_zero_padded(self):
        mock_xair = MagicMock()
        mock_client = MagicMock()
        mock_xair.connect.return_value = mock_client

        with patch.dict("sys.modules", {"xair_api": mock_xair}):
            with patch("mixer.time"):
                mixer = Mixer(host="x", port=1, channel=5, fade_duration=1.0)
                mixer.fade_out()

        for c in mock_client.send.call_args_list:
            assert c.args[0] == "/ch/05/mix/fader"

    def test_graceful_degradation_when_xr12_unreachable(self):
        """Mixer should not crash when XR12 is unreachable."""
        mock_xair = MagicMock()
        mock_xair.connect.side_effect = ConnectionError("unreachable")

        with patch.dict("sys.modules", {"xair_api": mock_xair}):
            mixer = Mixer(host="x", port=1, channel=1, fade_duration=1.0)

        # Should not raise
        mixer.fade_out()
        mixer.fade_in()
