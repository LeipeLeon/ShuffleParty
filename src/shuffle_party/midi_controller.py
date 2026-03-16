"""Behringer X-TOUCH ONE MIDI controller support.

The X-TOUCH ONE uses the Mackie Control Universal (MCU) protocol over USB MIDI.
Its motorized 100mm fader sends pitchbend messages and can receive position
feedback. This module maps the fader to the XR12 master volume.
"""

import logging

logger = logging.getLogger(__name__)

# MCU pitchbend range
_FADER_MAX = 16383


class MidiController:
    """Non-blocking reader for the X-TOUCH ONE fader via MIDI."""

    def __init__(self, port_name: str = "") -> None:
        self._inport = None
        self._outport = None
        self._available = False
        self._last_sent: int | None = None  # avoid echo loops

        try:
            import mido  # type: ignore[import-untyped]

            self._mido = mido
        except ImportError:
            logger.info("mido not installed — MIDI controller disabled.")
            return

        # Find the X-TOUCH ONE port (or use the given name)
        in_names = mido.get_input_names()
        out_names = mido.get_output_names()
        logger.debug("MIDI inputs: %s", in_names)
        logger.debug("MIDI outputs: %s", out_names)

        in_port = self._find_port(in_names, port_name)
        out_port = self._find_port(out_names, port_name)

        if not in_port:
            logger.info("No X-TOUCH ONE MIDI input found.")
            return

        try:
            self._inport = mido.open_input(in_port)
            logger.info("MIDI input: %s", in_port)
        except Exception as e:
            logger.warning("Could not open MIDI input %s — %r", in_port, e)
            return

        if out_port:
            try:
                self._outport = mido.open_output(out_port)
                logger.info("MIDI output: %s (motorized fader feedback enabled)", out_port)
            except Exception as e:
                logger.warning("Could not open MIDI output %s — %r", out_port, e)

        self._available = True

    @staticmethod
    def _find_port(names: list[str], hint: str) -> str | None:
        """Find a port matching the hint, or auto-detect X-TOUCH ONE."""
        if hint:
            for name in names:
                if hint.lower() in name.lower():
                    return name
        for name in names:
            if "x-touch" in name.lower():
                return name
        return None

    @property
    def available(self) -> bool:
        return self._available

    def poll(self) -> float | None:
        """Return the latest fader value (0.0–1.0), or None if no change.

        Drains all pending messages and returns only the most recent fader position.
        """
        if not self._available or self._inport is None:
            return None

        latest: float | None = None
        for msg in self._inport.iter_pending():
            if msg.type == "pitchwheel":
                # MCU fader: pitchwheel on channel 0, range -8192..8191
                # mido normalizes to -8192..8191; convert to 0..16383
                raw = msg.pitch + 8192
                # Skip if this is our own echo
                if self._last_sent is not None and raw == self._last_sent:
                    self._last_sent = None
                    continue
                latest = raw / _FADER_MAX

        return latest

    def set_fader(self, value: float) -> None:
        """Move the motorized fader to match the given volume (0.0–1.0)."""
        if self._outport is None:
            return
        raw = int(max(0.0, min(1.0, value)) * _FADER_MAX)
        self._last_sent = raw
        pitch = raw - 8192  # mido expects -8192..8191
        msg = self._mido.Message("pitchwheel", channel=0, pitch=pitch)
        self._outport.send(msg)

    def close(self) -> None:
        if self._inport is not None:
            self._inport.close()
            self._inport = None
        if self._outport is not None:
            self._outport.close()
            self._outport = None
        self._available = False
