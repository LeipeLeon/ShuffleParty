"""QLC+ lighting control via OSC.

Triggers pre-built QLC+ scenes for DJ Set and Shuffle states.
"""

import logging

from pythonosc.udp_client import SimpleUDPClient

logger = logging.getLogger(__name__)


class Lighting:
    """Sends OSC triggers to QLC+ to switch between lighting scenes."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._client = None
        self._target_dj = 255
        self._target_shuffle = 0
        self._connect()

    def _connect(self) -> None:
        """Attempt to connect to QLC+ OSC. Warn and continue if unreachable."""
        try:
            self._client = SimpleUDPClient(self.host, self.port)
        except Exception as e:
            print(f"Warning: QLC+ unreachable at {self.host}:{self.port} — {e}")
            print("Continuing without lighting control.")

    def activate_dj_set(self) -> None:
        """Start crossfade to DJ Set lighting (FX on, pin spots off)."""
        logger.info("Lighting: activate DJ Set")
        self._target_dj = 255
        self._target_shuffle = 0
        self._send(self._target_dj, self._target_shuffle)

    def activate_shuffle(self) -> None:
        """Start crossfade to Shuffle lighting (FX off, pin spots on)."""
        logger.info("Lighting: activate Shuffle")
        self._target_dj = 0
        self._target_shuffle = 255
        self._send(self._target_dj, self._target_shuffle)

    def update(self, fade_t: float) -> None:
        """Send interpolated lighting values during crossfade.

        fade_t: 0.0 = transition just started, 1.0 = complete.
        Call this each frame while crossfading.
        """
        if self._client is None:
            return
        dj_val = int(self._target_dj * fade_t + (255 - self._target_dj) * (1.0 - fade_t))
        shuffle_val = int(self._target_shuffle * fade_t + (255 - self._target_shuffle) * (1.0 - fade_t))
        self._send(dj_val, shuffle_val)

    def _send(self, dj_val: int, shuffle_val: int) -> None:
        """Send OSC values to QLC+."""
        if self._client is None:
            return
        logger.debug("Lighting OSC: /1=%d, /2=%d", dj_val, shuffle_val)
        self._client.send_message("/1", dj_val)
        self._client.send_message("/2", shuffle_val)
