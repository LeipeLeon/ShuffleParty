"""Shuffle Partey — autonomous DJ rotation system.

Two states cycling forever:
  DJ_SET -> (timer expires) -> SHUFFLE -> (track ends) -> DJ_SET
"""

from enum import Enum, auto

from shuffle_party import config
from shuffle_party.mixer import Mixer
from shuffle_party.lighting import Lighting
from shuffle_party.display import Display
from shuffle_party.track_picker import TrackPicker


class State(Enum):
    DJ_SET = auto()
    SHUFFLE = auto()


class ShuffleParty:
    """Main controller: a two-state machine coordinating audio, lights, and display."""

    def __init__(self) -> None:
        self.state = State.DJ_SET
        self.mixer = Mixer(
            host=config.XR12_HOST,
            port=config.XR12_PORT,
            dj_channels=[config.DJ_CHANNEL_L, config.DJ_CHANNEL_R],
            shuffle_channels=[config.SHUFFLE_CHANNEL_L, config.SHUFFLE_CHANNEL_R],
            fade_duration=config.FADE_DURATION_SECONDS,
        )
        self.lighting = Lighting(
            host=config.QLC_HOST,
            port=config.QLC_PORT,
        )
        self.display = Display(set_duration=config.SET_DURATION_SECONDS)
        self.track_picker = TrackPicker(config.TRACKS_DIR)

    def on_timer_expired(self) -> str | None:
        """Called when the DJ set countdown reaches 00:00. Returns the track to play."""
        if self.state != State.DJ_SET:
            return None
        self.state = State.SHUFFLE
        self.mixer.fade_out()
        track = self.track_picker.pick()
        self.display.show_shuffle_logo()
        self.lighting.activate_shuffle()
        return track

    def on_shuffle_track_ended(self) -> None:
        """Called when the shuffle track finishes playing."""
        if self.state != State.SHUFFLE:
            return
        self.state = State.DJ_SET
        self.mixer.fade_in()
        self.lighting.activate_dj_set()
        self.display.start_timer()
