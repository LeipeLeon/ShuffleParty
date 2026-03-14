"""DMX lighting control via OLA (Open Lighting Architecture).

Sends DMX values to two channels — one for DJ FX lights, one for
mirrorball pin spots — through the OLA daemon running on the Pi.
Falls back gracefully if OLA is not installed or olad is not running.

Install on Raspberry Pi:
    sudo apt install ola ola-python
"""

import array
import logging

logger = logging.getLogger(__name__)


class Lighting:
    """Controls DJ FX and pin spot lighting via OLA DMX."""

    def __init__(
        self,
        universe: int = 1,
        dj_channel: int = 1,
        shuffle_channel: int = 2,
    ) -> None:
        self.universe = universe
        self.dj_channel = dj_channel
        self.shuffle_channel = shuffle_channel
        self._client = None
        self._target_dj = 1.0
        self._target_shuffle = 0.0
        self._connect()

    def _connect(self) -> None:
        try:
            from ola.ClientWrapper import ClientWrapper

            self._wrapper = ClientWrapper()
            self._client = self._wrapper.Client()
            logger.info("OLA connected (universe %d, DJ ch%d, shuffle ch%d)",
                        self.universe, self.dj_channel, self.shuffle_channel)
        except ImportError:
            logger.warning("ola-python not installed — lighting disabled. "
                           "Install with: sudo apt install ola ola-python")
        except Exception as e:
            logger.warning(f"Could not connect to OLA daemon — {e!r}")
            logger.warning("Is olad running? Start with: sudo systemctl start olad")

    def activate_dj_set(self) -> None:
        """Start crossfade to DJ Set lighting (FX on, pin spots off)."""
        logger.info("Lighting: activate DJ Set")
        self._target_dj = 1.0
        self._target_shuffle = 0.0
        self._send(self._target_dj, self._target_shuffle)

    def activate_shuffle(self) -> None:
        """Start crossfade to Shuffle lighting (FX off, pin spots on)."""
        logger.info("Lighting: activate Shuffle")
        self._target_dj = 0.0
        self._target_shuffle = 1.0
        self._send(self._target_dj, self._target_shuffle)

    def update(self, fade_t: float) -> None:
        """Send interpolated lighting values during crossfade.

        fade_t: 0.0 = transition just started, 1.0 = complete.
        Call this each frame while crossfading.
        """
        if self._client is None:
            return
        dj_val = self._target_dj * fade_t + (1.0 - self._target_dj) * (1.0 - fade_t)
        shuffle_val = self._target_shuffle * fade_t + (1.0 - self._target_shuffle) * (1.0 - fade_t)
        self._send(dj_val, shuffle_val)

    def _send(self, dj_val: float, shuffle_val: float) -> None:
        """Send DMX values (converted from 0.0–1.0 to 0–255) via OLA."""
        if self._client is None:
            return
        max_ch = max(self.dj_channel, self.shuffle_channel)
        data = array.array("B", [0] * max_ch)
        data[self.dj_channel - 1] = int(dj_val * 255)
        data[self.shuffle_channel - 1] = int(shuffle_val * 255)
        logger.debug("DMX: ch%d=%d, ch%d=%d",
                     self.dj_channel, data[self.dj_channel - 1],
                     self.shuffle_channel, data[self.shuffle_channel - 1])
        self._client.SendDmx(self.universe, data)
