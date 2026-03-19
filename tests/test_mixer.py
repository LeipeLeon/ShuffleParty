"""Tests for XR12 mixer control."""

from unittest.mock import MagicMock, patch

import pytest

from shuffle_party.mixer import Mixer, NullBackend, OscBackend


class TestMixer:

    def _make_mixer(self, backend=None, **kwargs):
        """Create a Mixer with the given backend (defaults to MagicMock)."""
        return Mixer(
            backend=backend or MagicMock(),
            dj_channels=kwargs.get("dj_channels", [1, 2]),
            shuffle_channels=kwargs.get("shuffle_channels", [3, 4]),
            fade_duration=kwargs.get("fade_duration", 3.0),
        )

    def test_fade_out_starts_and_completes(self):
        backend = MagicMock()
        mixer = self._make_mixer(backend)

        with patch("shuffle_party.mixer.time") as mock_time:
            mock_time.monotonic.return_value = 0.0
            mixer.fade_out()
            assert mixer.is_fading
            assert mixer.dj_level == pytest.approx(0.75)  # 0 dB
            assert mixer.shuffle_level == pytest.approx(0.0)

            mock_time.monotonic.return_value = mixer.fade_duration + 0.1
            mixer.tick()
            assert not mixer.is_fading
            assert mixer.dj_level == pytest.approx(0.0)
            assert mixer.shuffle_level == pytest.approx(0.75)  # shuffle_gain default

    def test_fade_in_starts_and_completes(self):
        backend = MagicMock()
        mixer = self._make_mixer(backend)

        with patch("shuffle_party.mixer.time") as mock_time:
            # First fade out so shuffle_level reaches shuffle_gain
            mock_time.monotonic.return_value = 0.0
            mixer.fade_out()
            mock_time.monotonic.return_value = mixer.fade_duration + 0.1
            mixer.tick()

            # Now fade back in
            mock_time.monotonic.return_value = 10.0
            mixer.fade_in()
            assert mixer.dj_level == pytest.approx(0.0)
            assert mixer.shuffle_level == pytest.approx(0.75)

            mock_time.monotonic.return_value = 10.0 + mixer.fade_duration + 0.1
            mixer.tick()
            assert mixer.dj_level == pytest.approx(0.75)  # 0 dB
            assert mixer.shuffle_level == pytest.approx(0.0)

    def test_fade_midpoint_has_intermediate_values(self):
        backend = MagicMock()
        mixer = self._make_mixer(backend)

        with patch("shuffle_party.mixer.time") as mock_time:
            mock_time.monotonic.return_value = 0.0
            mixer.fade_out()

            mock_time.monotonic.return_value = mixer.fade_duration / 2
            mixer.tick()
            assert mixer.dj_level == pytest.approx(0.375)   # midpoint of 0.75→0.0
            assert mixer.shuffle_level == pytest.approx(0.375)  # midpoint of 0.0→0.75

    def test_fade_sends_to_all_four_channels(self):
        backend = MagicMock()
        mixer = self._make_mixer(backend)

        with patch("shuffle_party.mixer.time") as mock_time:
            mock_time.monotonic.return_value = 0.0
            mixer.fade_out()

        channels = set(c.args[0] for c in backend.send_channel_fader.call_args_list)
        assert channels == {1, 2, 3, 4}

    def test_channel_numbers_passed_to_backend(self):
        backend = MagicMock()
        mixer = self._make_mixer(backend, dj_channels=[5, 6], shuffle_channels=[9, 10])

        with patch("shuffle_party.mixer.time") as mock_time:
            mock_time.monotonic.return_value = 0.0
            mixer.fade_out()

        channels = set(c.args[0] for c in backend.send_channel_fader.call_args_list)
        assert channels == {5, 6, 9, 10}

    def test_osc_backend_formats_channel_addresses(self):
        """OscBackend should send zero-padded /ch/NN/mix/fader addresses."""
        mock_xair = MagicMock()
        mock_client = MagicMock()
        mock_xair.connect.return_value = mock_client
        with patch.dict("sys.modules", {"xair_api": mock_xair}):
            backend = OscBackend("192.168.1.100", 10023)
        backend.send_channel_fader(5, 0.75)
        mock_client.send.assert_called_with("/ch/05/mix/fader", 0.75)

    def test_graceful_degradation_with_null_backend(self):
        """Mixer should not crash with NullBackend."""
        mixer = self._make_mixer(NullBackend())

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
