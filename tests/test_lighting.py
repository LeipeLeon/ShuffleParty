"""Tests for QLC+ lighting control."""

from unittest.mock import MagicMock, patch

from shuffle_party.lighting import Lighting


class TestLighting:

    def _make_lighting(self):
        """Create Lighting with mocked python-osc."""
        mock_client = MagicMock()
        with patch("shuffle_party.lighting.SimpleUDPClient", return_value=mock_client):
            lighting = Lighting(host="127.0.0.1", port=7700)
        return lighting, mock_client

    def test_activate_dj_set_sends_correct_osc(self):
        lighting, client = self._make_lighting()
        lighting.activate_dj_set()
        client.send_message.assert_any_call("/1", 1.0)
        client.send_message.assert_any_call("/2", 0.0)

    def test_activate_shuffle_sends_correct_osc(self):
        lighting, client = self._make_lighting()
        lighting.activate_shuffle()
        client.send_message.assert_any_call("/1", 0.0)
        client.send_message.assert_any_call("/2", 1.0)

    def test_update_sends_interpolated_values(self):
        lighting, client = self._make_lighting()
        lighting.activate_shuffle()  # target: /1=0.0, /2=1.0
        client.reset_mock()
        lighting.update(0.5)  # midpoint
        client.send_message.assert_any_call("/1", 0.5)
        client.send_message.assert_any_call("/2", 0.5)

    def test_update_at_completion(self):
        lighting, client = self._make_lighting()
        lighting.activate_shuffle()
        client.reset_mock()
        lighting.update(1.0)
        client.send_message.assert_any_call("/1", 0.0)
        client.send_message.assert_any_call("/2", 1.0)

    def test_graceful_degradation_when_qlc_unreachable(self):
        """Lighting should not crash when QLC+ is unreachable."""
        with patch("shuffle_party.lighting.SimpleUDPClient", side_effect=Exception("unreachable")):
            lighting = Lighting(host="x", port=1)

        # Should not raise
        lighting.activate_dj_set()
        lighting.activate_shuffle()
        lighting.update(0.5)
