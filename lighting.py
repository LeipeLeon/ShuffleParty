"""QLC+ lighting control via OSC.

Triggers pre-built QLC+ scenes for DJ Set and Shuffle states.
"""


class Lighting:
    """Sends OSC triggers to QLC+ to switch between lighting scenes."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self._client = None
        self._connect()

    def _connect(self) -> None:
        """Attempt to connect to QLC+ OSC. Warn and continue if unreachable."""
        try:
            from pythonosc.udp_client import SimpleUDPClient

            self._client = SimpleUDPClient(self.host, self.port)
        except Exception as e:
            print(f"Warning: QLC+ unreachable at {self.host}:{self.port} — {e}")
            print("Continuing without lighting control.")

    def activate_dj_set(self) -> None:
        """Turn on FX lights, turn off pin spots."""
        if self._client is None:
            return
        self._client.send_message("/qlc/scene/dj_set", 1.0)

    def activate_shuffle(self) -> None:
        """Turn off FX lights, turn on pin spots."""
        if self._client is None:
            return
        self._client.send_message("/qlc/scene/shuffle", 1.0)
