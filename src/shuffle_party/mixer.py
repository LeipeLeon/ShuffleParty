"""XR12 mixer control with pluggable backends (OSC or MIDI).

Wraps the Behringer XR12 fader control for DJ and shuffle channel crossfading.
Non-blocking: call tick() each frame to advance any active crossfade.

The Mixer class handles crossfade logic and level tracking. Actual
communication with the XR12 is delegated to a backend (OSC or MIDI).
"""

from __future__ import annotations

import logging
import time
from typing import Protocol

logger = logging.getLogger(__name__)


class MixerBackend(Protocol):
    """Interface for sending fader commands to the XR12."""

    def send_channel_fader(self, channel: int, value: float) -> None:
        """Set an input channel fader (1-based channel, 0.0–1.0)."""
        ...

    def send_master_fader(self, value: float) -> None:
        """Set the main LR fader (0.0–1.0)."""
        ...


class OscBackend:
    """XR12 control via OSC over WiFi/Ethernet (xair_api).

    Automatically reconnects when the XR12 becomes unreachable.
    """

    _RECONNECT_INTERVAL = 5.0  # seconds between reconnection attempts

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._client = None
        self._last_reconnect = 0.0
        self._connect()

    def _connect(self) -> None:
        """Attempt to create the xair_api client."""
        self._client = None
        try:
            import xair_api  # type: ignore[import-untyped]

            self._client = xair_api.connect("XR12", ip=self._host, port=self._port)
            logger.info("XR12 OSC backend connected at %s:%d", self._host, self._port)
        except Exception as e:
            logger.warning("XR12 unreachable at %s:%d — %r", self._host, self._port, e)

    def _reconnect_if_needed(self) -> None:
        """Try to reconnect if client is down and enough time has passed."""
        if self._client is not None:
            return
        now = time.monotonic()
        if now - self._last_reconnect < self._RECONNECT_INTERVAL:
            return
        self._last_reconnect = now
        logger.info("Attempting XR12 reconnect...")
        self._connect()

    def _send(self, address: str, value: float) -> None:
        """Send an OSC message, reconnecting on failure."""
        self._reconnect_if_needed()
        if self._client is None:
            return
        try:
            self._client.send(address, value)
        except Exception:
            logger.warning("XR12 send failed — will reconnect.")
            self._client = None

    def send_channel_fader(self, channel: int, value: float) -> None:
        self._send(f"/ch/{channel:02d}/mix/fader", value)

    def send_master_fader(self, value: float) -> None:
        self._send("/lr/mix/fader", value)


class MidiBackend:
    """XR12 control via MIDI CC over a USB-to-DIN adapter.

    XR12 MIDI CC mapping (from Behringer wiki):
      Faders:  MIDI ch 1, CC 0–15 → input channels 1–16, CC 31 → Main LR
      Mutes:   MIDI ch 2, same CC numbers (0=unmuted, 127=muted)
      Pan:     MIDI ch 3, same CC numbers (64=center)

    Values are 0–127 (linear). We map 0.0–1.0 float to 0–127 int.
    """

    # MIDI channel (0-indexed for mido)
    _FADER_CHANNEL = 0  # MIDI ch 1
    _MAIN_LR_CC = 31

    def __init__(self, port_name: str = "") -> None:
        self._outport = None
        self._mido = None

        try:
            import mido  # type: ignore[import-untyped]

            self._mido = mido
        except ImportError:
            logger.warning("mido not installed — MIDI mixer backend disabled.")
            return

        out_names = mido.get_output_names()
        logger.debug("MIDI outputs for mixer: %s", out_names)

        port = self._find_port(out_names, port_name)
        if not port:
            logger.warning("No MIDI output found for XR12 mixer backend.")
            return

        try:
            self._outport = mido.open_output(port)
            logger.info("XR12 MIDI backend on %s", port)
        except Exception as e:
            logger.warning("Could not open MIDI output %s — %r", port, e)

    @staticmethod
    def _find_port(names: list[str], hint: str) -> str | None:
        if hint:
            for name in names:
                if hint.lower() in name.lower():
                    return name
        # Auto-detect: skip X-TOUCH ports, pick the first remaining one
        for name in names:
            if "x-touch" not in name.lower():
                return name
        return None

    def _send_cc(self, cc: int, value_float: float) -> None:
        if self._outport is None or self._mido is None:
            return
        cc_value = max(0, min(127, int(value_float * 127)))
        msg = self._mido.Message(
            "control_change", channel=self._FADER_CHANNEL, control=cc, value=cc_value,
        )
        self._outport.send(msg)

    def send_channel_fader(self, channel: int, value: float) -> None:
        # XR12: CC number = channel - 1 (zero-indexed)
        cc = channel - 1
        if 0 <= cc <= 15:
            self._send_cc(cc, value)

    def send_master_fader(self, value: float) -> None:
        self._send_cc(self._MAIN_LR_CC, value)


class NullBackend:
    """No-op backend when no mixer connection is configured."""

    def send_channel_fader(self, channel: int, value: float) -> None:
        pass

    def send_master_fader(self, value: float) -> None:
        pass


class Mixer:
    """Controls DJ and shuffle channel faders on the Behringer XR12.

    Crossfade logic is backend-agnostic. Pass an OscBackend, MidiBackend,
    or any object implementing the MixerBackend protocol.
    """

    def __init__(
        self,
        backend: MixerBackend,
        dj_channels: list[int],
        shuffle_channels: list[int],
        fade_duration: float,
    ) -> None:
        self._backend = backend
        self.dj_channels = dj_channels
        self.shuffle_channels = shuffle_channels
        self.fade_duration = fade_duration
        self.dj_level = 1.0
        self.shuffle_level = 0.0
        self._fade: dict[str, float] | None = None

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
        assert f is not None
        dj_value = f["dj_start"] + (f["dj_end"] - f["dj_start"]) * t
        shuffle_value = f["shuffle_start"] + (f["shuffle_end"] - f["shuffle_start"]) * t
        self.dj_level = dj_value
        self.shuffle_level = shuffle_value
        for ch in self.dj_channels:
            self._backend.send_channel_fader(ch, dj_value)
        for ch in self.shuffle_channels:
            self._backend.send_channel_fader(ch, shuffle_value)
        logger.debug("DJ ch%s=%.3f, Shuffle ch%s=%.3f (t=%.2f)",
                     self.dj_channels, dj_value,
                     self.shuffle_channels, shuffle_value, t)

    def reset(self) -> None:
        """Cancel any active fade and reset levels to initial state."""
        self._fade = None
        self.dj_level = 1.0
        self.shuffle_level = 0.0

    def set_channel_volume(self, channels: list[int], value: float) -> None:
        """Set the fader for one or more XR12 channels (0.0–1.0).

        Also updates dj_level / shuffle_level if the channels match.
        """
        for ch in channels:
            self._backend.send_channel_fader(ch, value)
        if set(channels) == set(self.dj_channels):
            self.dj_level = value
        elif set(channels) == set(self.shuffle_channels):
            self.shuffle_level = value

    def set_master_volume(self, value: float) -> None:
        """Set the main LR fader (0.0–1.0)."""
        self._backend.send_master_fader(value)
