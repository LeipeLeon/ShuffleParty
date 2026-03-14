"""Shuffle Partey — autonomous DJ rotation system.

Two states cycling forever:
  DJ_SET -> (timer expires) -> SHUFFLE -> (track ends) -> DJ_SET
"""

from enum import Enum, auto

from shuffle_party import config
from shuffle_party.display import Display
from shuffle_party.lighting import Lighting
from shuffle_party.mixer import Mixer
from shuffle_party.track_picker import TrackPicker


class State(Enum):
    IDLE = auto()
    DJ_SET = auto()
    SHUFFLE = auto()


class ShuffleParty:
    """Main controller: a two-state machine coordinating audio, lights, and display."""

    def __init__(self) -> None:
        self.state = State.IDLE
        self.mixer = Mixer(
            host=config.XR12_HOST,
            port=config.XR12_PORT,
            dj_channels=[config.DJ_CHANNEL_L, config.DJ_CHANNEL_R],
            shuffle_channels=[config.SHUFFLE_CHANNEL_L, config.SHUFFLE_CHANNEL_R],
            fade_duration=config.FADE_DURATION_SECONDS,
        )
        self.lighting = Lighting(
            universe=config.DMX_UNIVERSE,
            dj_channel=config.DMX_DJ_CHANNEL,
            shuffle_channel=config.DMX_SHUFFLE_CHANNEL,
        )
        self.display = Display(set_duration=config.SET_DURATION_SECONDS)
        self.track_picker = TrackPicker(config.TRACKS_DIR)
        self.pending_track: str | None = None

    def reset(self) -> None:
        """Reset to IDLE state, cancelling any active fades."""
        self.state = State.IDLE
        self.mixer.reset()
        self.display.remaining_seconds = self.display.set_duration

    def start_dj_set(self) -> None:
        """Transition from IDLE to DJ_SET. Timer starts after crossfade completes."""
        if self.state != State.IDLE:
            return
        self.state = State.DJ_SET
        self.mixer.fade_in()
        self.lighting.activate_dj_set()

    def on_timer_expired(self) -> None:
        """Called when the DJ set countdown reaches 00:00."""
        if self.state != State.DJ_SET:
            return
        self.state = State.SHUFFLE
        self.mixer.fade_out()
        self.lighting.activate_shuffle()

    def on_shuffle_track_ended(self) -> None:
        """Called when the shuffle track finishes playing. Timer starts after crossfade."""
        if self.state != State.SHUFFLE:
            return
        self.state = State.DJ_SET
        self.mixer.fade_in()
        self.lighting.activate_dj_set()
