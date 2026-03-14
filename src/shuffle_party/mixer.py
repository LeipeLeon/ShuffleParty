"""XR12 mixer control via OSC.

Wraps the Behringer XR12 fader control for DJ audio fade in/out.
"""

import time


class Mixer:
    """Controls DJ channel fader on the Behringer XR12 via OSC."""

    def __init__(self, host: str, port: int, channels: list[int], fade_duration: float) -> None:
        self.host = host
        self.port = port
        self.channels = channels
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
        """Gradually fade the DJ channel from unity to silence over fade_duration."""
        self._fade(start=1.0, end=0.0)

    def fade_in(self) -> None:
        """Gradually fade the DJ channel from silence to unity over fade_duration."""
        self._fade(start=0.0, end=1.0)

    def _fade(self, start: float, end: float, steps: int = 30) -> None:
        """Ramp the fader from start to end over self.fade_duration seconds."""
        if self._client is None:
            return
        step_time = self.fade_duration / steps
        for i in range(steps + 1):
            value = start + (end - start) * (i / steps)
            for ch in self.channels:
                self._client.send(f"/ch/{ch:02d}/mix/fader", value)
            if i < steps:
                time.sleep(step_time)
