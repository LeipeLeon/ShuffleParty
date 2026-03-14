"""XR12 mixer control via OSC.

Wraps the Behringer XR12 fader control for DJ and shuffle channel crossfading.
Non-blocking: call tick() each frame to advance any active crossfade.
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
        self.dj_level = 1.0
        self.shuffle_level = 0.0
        self._fade = None  # active fade state
        self._connect()

    def _connect(self) -> None:
        """Attempt to connect to the XR12. Warn and continue if unreachable."""
        try:
            import xair_api

            self._client = xair_api.connect(self.host, self.port)
        except Exception as e:
            logger.warning(f"XR12 unreachable at {self.host}:{self.port} — {e!r}")
            logger.warning("Continuing without mixer control.")

    def fade_out(self) -> None:
        """Start crossfade: DJ channels down, shuffle channels up."""
        logger.info("Fade out: DJ 1.0→0.0, Shuffle 0.0→1.0 over %.1fs",
                     self.fade_duration)
        self._start_fade(dj_start=1.0, dj_end=0.0, shuffle_start=0.0, shuffle_end=1.0)

    def fade_in(self) -> None:
        """Start crossfade: shuffle channels down, DJ channels up."""
        logger.info("Fade in: DJ 0.0→1.0, Shuffle 1.0→0.0 over %.1fs",
                     self.fade_duration)
        self._start_fade(dj_start=0.0, dj_end=1.0, shuffle_start=1.0, shuffle_end=0.0)

    def _start_fade(
        self,
        dj_start: float,
        dj_end: float,
        shuffle_start: float,
        shuffle_end: float,
    ) -> None:
        """Begin a non-blocking crossfade. Call tick() each frame to advance."""
        self._fade = {
            "dj_start": dj_start,
            "dj_end": dj_end,
            "shuffle_start": shuffle_start,
            "shuffle_end": shuffle_end,
            "start_time": time.monotonic(),
        }
        # Set initial values immediately
        self._apply_fade(0.0)

    @property
    def is_fading(self) -> bool:
        return self._fade is not None

    def tick(self) -> None:
        """Advance the active crossfade. Call this every frame."""
        if self._fade is None:
            return
        elapsed = time.monotonic() - self._fade["start_time"]
        t = min(1.0, elapsed / self.fade_duration)
        self._apply_fade(t)
        if t >= 1.0:
            logger.info("Fade complete")
            self._fade = None

    def _apply_fade(self, t: float) -> None:
        """Apply fader values for progress t (0.0–1.0)."""
        f = self._fade
        dj_value = f["dj_start"] + (f["dj_end"] - f["dj_start"]) * t
        shuffle_value = f["shuffle_start"] + (f["shuffle_end"] - f["shuffle_start"]) * t
        self.dj_level = dj_value
        self.shuffle_level = shuffle_value
        if self._client is not None:
            for ch in self.dj_channels:
                self._client.send(f"/ch/{ch:02d}/mix/fader", dj_value)
            for ch in self.shuffle_channels:
                self._client.send(f"/ch/{ch:02d}/mix/fader", shuffle_value)
        logger.debug("DJ ch%s=%.3f, Shuffle ch%s=%.3f (t=%.2f)",
                     self.dj_channels, dj_value,
                     self.shuffle_channels, shuffle_value, t)

    def set_master_volume(self, value: float) -> None:
        """Set the main LR fader (0.0–1.0)."""
        if self._client is None:
            return
        self._client.send("/lr/mix/fader", value)
