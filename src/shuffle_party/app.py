"""Shuffle Partey — autonomous DJ rotation system.

Two states cycling forever:
  DJ_SET -> (timer expires) -> SHUFFLE -> (track ends) -> DJ_SET
"""

from enum import Enum, auto

from shuffle_party.mixer import Mixer
from shuffle_party.lighting import Lighting
from shuffle_party.display import Display
from shuffle_party.track_picker import TrackPicker


# Configuration — tweak these values at the top of the file
CONFIG = {
    "set_duration_seconds": 15 * 60,  # 15 minutes per DJ set
    "dj_channel": 1,                  # XR12 channel for DJ input
    "xr12_host": "192.168.1.100",
    "xr12_port": 10023,
    "qlc_host": "127.0.0.1",
    "qlc_port": 7700,
    "tracks_dir": "./tracks/",
    "fade_duration_seconds": 3.0,
}


class State(Enum):
    DJ_SET = auto()
    SHUFFLE = auto()


class ShuffleParty:
    """Main controller: a two-state machine coordinating audio, lights, and display."""

    def __init__(self) -> None:
        self.state = State.DJ_SET
        self.mixer = Mixer(
            host=CONFIG["xr12_host"],
            port=CONFIG["xr12_port"],
            channel=CONFIG["dj_channel"],
            fade_duration=CONFIG["fade_duration_seconds"],
        )
        self.lighting = Lighting(
            host=CONFIG["qlc_host"],
            port=CONFIG["qlc_port"],
        )
        self.display = Display(set_duration=CONFIG["set_duration_seconds"])
        self.track_picker = TrackPicker(CONFIG["tracks_dir"])

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
