"""DMX lighting control via OLA (Open Lighting Architecture).

Sends DMX values to two channels — one for DJ FX lights, one for
mirrorball pin spots — through OLA's HTTP API on localhost:9090.
Works on both macOS (brew install ola) and Pi (apt install ola).

No Python bindings needed — uses the REST API directly.
"""

import logging
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)


class Lighting:
    """Controls DJ FX and pin spot lighting via OLA DMX."""

    def __init__(
        self,
        universe: int = 1,
        dj_channel: int = 1,
        shuffle_channel: int = 2,
        ola_url: str = "http://localhost:9090",
    ) -> None:
        self.universe = universe
        self.dj_channel = dj_channel
        self.shuffle_channel = shuffle_channel
        self._ola_url = ola_url
        self._available = False
        self._target_dj = 1.0
        self._target_shuffle = 0.0
        self._check_connection()

    def _check_connection(self) -> None:
        try:
            req = urllib.request.urlopen(f"{self._ola_url}/get_dmx?u={self.universe}", timeout=1)
            req.read()
            self._available = True
            logger.info("OLA connected (universe %d, DJ ch%d, shuffle ch%d)",
                        self.universe, self.dj_channel, self.shuffle_channel)
        except Exception as e:
            logger.warning(f"OLA not available at {self._ola_url} — {e!r}")
            logger.warning("Continuing without lighting control. "
                           "Start olad and create universe %d.", self.universe)

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
        if not self._available:
            return
        dj_val = self._target_dj * fade_t + (1.0 - self._target_dj) * (1.0 - fade_t)
        shuffle_val = self._target_shuffle * fade_t + (1.0 - self._target_shuffle) * (1.0 - fade_t)
        self._send(dj_val, shuffle_val)

    def _send(self, dj_val: float, shuffle_val: float) -> None:
        """Send DMX values (converted from 0.0–1.0 to 0–255) via OLA HTTP API."""
        if not self._available:
            return
        max_ch = max(self.dj_channel, self.shuffle_channel)
        dmx = [0] * max_ch
        dmx[self.dj_channel - 1] = int(dj_val * 255)
        dmx[self.shuffle_channel - 1] = int(shuffle_val * 255)
        dmx_str = ",".join(str(v) for v in dmx)
        logger.debug("DMX: ch%d=%d, ch%d=%d",
                     self.dj_channel, dmx[self.dj_channel - 1],
                     self.shuffle_channel, dmx[self.shuffle_channel - 1])
        try:
            data = urllib.parse.urlencode({"u": self.universe, "d": dmx_str}).encode()
            req = urllib.request.urlopen(f"{self._ola_url}/set_dmx", data, timeout=0.1)
            req.read()
        except Exception:
            pass  # don't let lighting errors interrupt the main loop
