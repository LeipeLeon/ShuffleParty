"""Behringer X-TOUCH EXTENDER MIDI controller support.

Uses all 8 faders via the Mackie Control Universal (MCU) protocol:
faders 1–7 (channels 0–6) control XR12 channel volumes, and fader 8
(channel 7) controls master volume. Motorized faders send/receive
pitchbend messages on MIDI channels 0–7.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# MCU pitchbend range
_FADER_MAX = 16383


def _find_port(names: list[str], hint: str, keyword: str) -> str | None:
    """Find a MIDI port matching the hint string, or auto-detect by keyword."""
    if hint:
        for name in names:
            if hint.lower() in name.lower():
                return name
    for name in names:
        if keyword in name.lower():
            return name
    return None


def _open_ports(
    port_name: str, keyword: str, label: str,
) -> tuple[Any, Any, Any]:
    """Open MIDI input/output ports. Returns (mido_module, inport, outport) or Nones."""
    try:
        import mido  # type: ignore[import-untyped]
    except ImportError:
        logger.info("mido not installed — %s disabled.", label)
        return None, None, None

    in_names = mido.get_input_names()
    out_names = mido.get_output_names()
    logger.debug("MIDI inputs: %s", in_names)
    logger.debug("MIDI outputs: %s", out_names)

    in_port = _find_port(in_names, port_name, keyword)
    out_port = _find_port(out_names, port_name, keyword)

    if not in_port:
        logger.info("No %s MIDI input found.", label)
        return mido, None, None

    inport = None
    outport = None
    try:
        inport = mido.open_input(in_port)
        logger.info("%s MIDI input: %s", label, in_port)
    except Exception as e:
        logger.warning("Could not open MIDI input %s — %r", in_port, e)
        return mido, None, None

    if out_port:
        try:
            outport = mido.open_output(out_port)
            logger.info("%s MIDI output: %s (motorized fader feedback)", label, out_port)
        except Exception as e:
            logger.warning("Could not open MIDI output %s — %r", out_port, e)

    return mido, inport, outport


_MASTER_FADER = 7  # MCU channel index for master volume (fader 8)


def build_channel_map(
    dj_channels: list[int],
    shuffle_channels: list[int],
    total_channels: int = 12,
) -> list[list[int]]:
    """Build a fader-to-XR12-channel map, combining stereo pairs.

    Returns a list of up to 7 entries (faders 1–7), each a list of XR12
    channel numbers controlled by that fader. Fader 8 is reserved for master
    volume. Configured stereo pairs (DJ L+R, Shuffle L+R) share a single
    fader; remaining channels get one each.

    Channels are ordered numerically, pairs sorted by their lowest channel.
    """
    pairs: dict[int, list[int]] = {}  # lowest_channel -> [channels]
    paired: set[int] = set()

    for pair in (shuffle_channels, dj_channels):
        if len(pair) == 2 and pair[0] != pair[1]:
            key = min(pair)
            pairs[key] = sorted(pair)
            paired.update(pair)

    result: list[list[int]] = []
    for ch in range(1, total_channels + 1):
        if ch in paired:
            if ch in pairs:
                result.append(pairs[ch])
        else:
            result.append([ch])
        if len(result) >= _MASTER_FADER:
            break

    return result


class MidiExtender:
    """Non-blocking reader for the X-TOUCH EXTENDER (8 faders) via MIDI.

    Faders 1–7 (channels 0–6) map to XR12 channels. Fader 8 (channel 7)
    controls master volume. Configured stereo pairs (DJ L+R and Shuffle L+R)
    are combined onto a single fader.
    """

    def __init__(
        self,
        port_name: str,
        channel_map: list[list[int]],
    ) -> None:
        self._mido = None
        self._inport = None
        self._outport = None
        self._available = False
        self._channel_map = channel_map
        self._last_sent: dict[int, int] = {}  # fader_index -> last raw value sent
        self._levels: list[float] = [0.0] * len(channel_map)
        self._master_last_sent: int | None = None

        mido, inport, outport = _open_ports(port_name, "x-touch-ext", "X-TOUCH EXTENDER")
        if inport is None:
            return
        self._mido = mido
        self._inport = inport
        self._outport = outport
        self._available = True

    @property
    def available(self) -> bool:
        return self._available

    @property
    def channel_map(self) -> list[list[int]]:
        return self._channel_map

    def poll(self) -> tuple[dict[int, float], float | None]:
        """Return ({fader_index: value}, master_value) for any faders that changed.

        master_value is the fader 8 position (0.0–1.0), or None if unchanged.
        """
        if not self._available or self._inport is None:
            return {}, None

        changed: dict[int, float] = {}
        master: float | None = None
        for msg in self._inport.iter_pending():
            if msg.type != "pitchwheel":
                continue
            raw = msg.pitch + 8192
            if msg.channel == _MASTER_FADER:
                if self._master_last_sent is not None and raw == self._master_last_sent:
                    self._master_last_sent = None
                    continue
                master = raw / _FADER_MAX
            elif 0 <= msg.channel < len(self._channel_map):
                idx = msg.channel
                if self._last_sent.get(idx) == raw:
                    del self._last_sent[idx]
                    continue
                value = raw / _FADER_MAX
                self._levels[idx] = value
                changed[idx] = value

        return changed, master

    def set_fader(self, index: int, value: float) -> None:
        """Move a motorized fader to the given position (0.0–1.0)."""
        if self._outport is None or self._mido is None:
            return
        if index < 0 or index >= len(self._channel_map):
            return
        raw = int(max(0.0, min(1.0, value)) * _FADER_MAX)
        self._last_sent[index] = raw
        pitch = raw - 8192
        self._outport.send(self._mido.Message("pitchwheel", channel=index, pitch=pitch))

    def set_master_fader(self, value: float) -> None:
        """Move the master fader (fader 8) to the given position (0.0–1.0)."""
        if self._outport is None or self._mido is None:
            return
        raw = int(max(0.0, min(1.0, value)) * _FADER_MAX)
        self._master_last_sent = raw
        pitch = raw - 8192
        self._outport.send(self._mido.Message("pitchwheel", channel=_MASTER_FADER, pitch=pitch))

    def fader_index_for_channels(self, channels: list[int]) -> int | None:
        """Find the fader index that controls the given XR12 channels."""
        target = set(channels)
        for i, mapped in enumerate(self._channel_map):
            if target & set(mapped):
                return i
        return None

    def close(self) -> None:
        if self._inport is not None:
            self._inport.close()
            self._inport = None
        if self._outport is not None:
            self._outport.close()
            self._outport = None
        self._available = False
