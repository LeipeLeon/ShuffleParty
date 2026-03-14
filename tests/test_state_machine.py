"""Tests for the DJ rotation state machine."""

from unittest.mock import patch

from shuffle_party.app import ShuffleParty, State


class TestStateMachine:
    """State machine transitions: DJ_SET <-> SHUFFLE."""

    def setup_method(self):
        """Create a ShuffleParty instance with all hardware mocked out."""
        with patch("shuffle_party.app.Mixer"), \
             patch("shuffle_party.app.Lighting"), \
             patch("shuffle_party.app.Display"), \
             patch("shuffle_party.app.TrackPicker"):
            self.party = ShuffleParty()

    def test_initial_state_is_dj_set(self):
        assert self.party.state == State.DJ_SET

    def test_timer_expiry_transitions_to_shuffle(self):
        self.party.on_timer_expired()
        assert self.party.state == State.SHUFFLE

    def test_track_end_transitions_to_dj_set(self):
        self.party.on_timer_expired()  # go to SHUFFLE first
        self.party.on_shuffle_track_ended()
        assert self.party.state == State.DJ_SET

    def test_track_end_ignored_during_dj_set(self):
        """Track end events during DJ_SET should not change state."""
        self.party.on_shuffle_track_ended()
        assert self.party.state == State.DJ_SET

    def test_timer_expiry_ignored_during_shuffle(self):
        """Timer events during SHUFFLE should not change state."""
        self.party.on_timer_expired()
        self.party.on_timer_expired()
        assert self.party.state == State.SHUFFLE

    def test_transition_to_shuffle_fades_dj_out(self):
        self.party.on_timer_expired()
        self.party.mixer.fade_out.assert_called_once()

    def test_transition_to_shuffle_activates_shuffle_lights(self):
        self.party.on_timer_expired()
        self.party.lighting.activate_shuffle.assert_called_once()

    def test_transition_to_dj_set_fades_dj_in(self):
        self.party.on_timer_expired()
        self.party.on_shuffle_track_ended()
        self.party.mixer.fade_in.assert_called_once()

    def test_transition_to_dj_set_activates_dj_lights(self):
        self.party.on_timer_expired()
        self.party.on_shuffle_track_ended()
        self.party.lighting.activate_dj_set.assert_called_once()

    def test_transition_to_dj_set_resets_timer(self):
        self.party.on_timer_expired()
        self.party.on_shuffle_track_ended()
        self.party.display.start_timer.assert_called()
