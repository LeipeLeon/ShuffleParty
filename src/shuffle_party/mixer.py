"""XR12 mixer control via OSC.

Wraps the Behringer XR12 fader control for DJ and shuffle channel crossfading.
"""

import logging
import time

logger = logging.getLogger(__name__)


class Mixer:
    """Controls DJ and shuffle channel faders on the Behringer XR12 via OSC."""

    def __init__(
        self,
        host: str,
        port: int,
        dj_channels: list[int],
        shuffle_channels: list[int],
        fade_duration: float,
    ) -> None:
        self.host = host
        self.port = port
        self.dj_channels = dj_channels
        self.shuffle_channels = shuffle_channels
        self.fade_duration = fade_duration
        self._client = None
        self._connect()

    def _connect(self) -> None:
        """Attempt to connect to the XR12. Warn and continue if unreachable."""
        try:
            import xair_api

            self._client = xair_api.connect(self.host, self.port)
        except Exception as e:
            print(f"Warning: XR12 unreachable at {self.host}:{self.port} — {e}")
            print("Continuing without mixer control.")

    def fade_out(self) -> None:
        """Crossfade: DJ channels down, shuffle channels up."""
        logger.info("Fade out: DJ %.1f→%.1f, Shuffle %.1f→%.1f over %.1fs",
                     1.0, 0.0, 0.0, 1.0, self.fade_duration)
        self._crossfade(dj_start=1.0, dj_end=0.0, shuffle_start=0.0, shuffle_end=1.0)

    def fade_in(self) -> None:
        """Crossfade: shuffle channels down, DJ channels up."""
        logger.info("Fade in: DJ %.1f→%.1f, Shuffle %.1f→%.1f over %.1fs",
                     0.0, 1.0, 1.0, 0.0, self.fade_duration)
        self._crossfade(dj_start=0.0, dj_end=1.0, shuffle_start=1.0, shuffle_end=0.0)

    def _crossfade(
        self,
        dj_start: float,
        dj_end: float,
        shuffle_start: float,
        shuffle_end: float,
        steps: int = 30,
    ) -> None:
        """Ramp DJ and shuffle faders simultaneously over fade_duration."""
        step_time = self.fade_duration / steps
        for i in range(steps + 1):
            t = i / steps
            dj_value = dj_start + (dj_end - dj_start) * t
            shuffle_value = shuffle_start + (shuffle_end - shuffle_start) * t
            if self._client is not None:
                for ch in self.dj_channels:
                    self._client.send(f"/ch/{ch:02d}/mix/fader", dj_value)
                for ch in self.shuffle_channels:
                    self._client.send(f"/ch/{ch:02d}/mix/fader", shuffle_value)
            if i % 10 == 0:
                logger.info("  step %d/%d — DJ ch%s=%.3f, Shuffle ch%s=%.3f",
                             i, steps, self.dj_channels, dj_value,
                             self.shuffle_channels, shuffle_value)
            if i < steps:
                time.sleep(step_time)
        logger.info("Fade complete")

    def set_master_volume(self, value: float) -> None:
        """Set the main LR fader (0.0–1.0)."""
        if self._client is None:
            return
        self._client.send("/lr/mix/fader", value)
