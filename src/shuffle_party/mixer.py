"""XR12 mixer control via OSC.

Wraps the Behringer XR12 fader control for DJ and shuffle channel crossfading.
"""

import time


class Mixer:
    """Controls DJ and shuffle channel faders on the Behringer XR12 via OSC."""

    def __init__(
        self,
        host: str,
        port: int,
        dj_channels: list[int],
        shuffle_channel: int,
        fade_duration: float,
    ) -> None:
        self.host = host
        self.port = port
        self.dj_channels = dj_channels
        self.shuffle_channel = shuffle_channel
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
        """Crossfade: DJ channels down, shuffle channel up."""
        self._crossfade(dj_start=1.0, dj_end=0.0, shuffle_start=0.0, shuffle_end=1.0)

    def fade_in(self) -> None:
        """Crossfade: shuffle channel down, DJ channels up."""
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
        if self._client is None:
            return
        step_time = self.fade_duration / steps
        for i in range(steps + 1):
            t = i / steps
            dj_value = dj_start + (dj_end - dj_start) * t
            shuffle_value = shuffle_start + (shuffle_end - shuffle_start) * t
            for ch in self.dj_channels:
                self._client.send(f"/ch/{ch:02d}/mix/fader", dj_value)
            self._client.send(f"/ch/{self.shuffle_channel:02d}/mix/fader", shuffle_value)
            if i < steps:
                time.sleep(step_time)
