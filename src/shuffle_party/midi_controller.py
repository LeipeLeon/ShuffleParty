"""Behringer X-TOUCH EXTENDER MIDI controller support.

Uses all 8 faders via the Mackie Control Universal (MCU) protocol:
faders 1–7 (channels 0–6) control XR12 channel volumes, and fader 8
(channel 7) controls master volume. Motorized faders send/receive
pitchbend messages on MIDI channels 0–7.

Supports both USB MIDI (via mido/rtmidi) and network RTP-MIDI.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# MCU pitchbend range
_FADER_MAX = 16383
_MASTER_FADER = 7  # MCU channel index for master volume (fader 8)


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


class _MidiTransport(Protocol):
    """Interface for MIDI send/receive backends."""

    def iter_pending(self) -> list[tuple[int, int, int]]:
        """Return pending MIDI messages as (status, data1, data2) tuples."""
        ...

    def send_pitchbend(self, channel: int, value_14bit: int) -> None:
        """Send a pitchbend message."""
        ...

    def close(self) -> None: ...


class _UsbTransport:
    """USB MIDI transport via mido/rtmidi."""

    def __init__(self, port_name: str) -> None:
        self._mido = None
        self._inport = None
        self._outport = None
        self.available = False

        try:
            import mido  # type: ignore[import-untyped]
        except ImportError:
            logger.info("mido not installed — USB MIDI disabled.")
            return

        in_names = mido.get_input_names()
        out_names = mido.get_output_names()
        logger.debug("MIDI inputs: %s", in_names)
        logger.debug("MIDI outputs: %s", out_names)

        in_port = _find_port(in_names, port_name, "x-touch-ext")
        out_port = _find_port(out_names, port_name, "x-touch-ext")

        if not in_port:
            logger.info("No X-TOUCH EXTENDER USB MIDI input found.")
            return

        try:
            self._inport = mido.open_input(in_port)
            logger.info("USB MIDI input: %s", in_port)
        except Exception as e:
            logger.warning("Could not open MIDI input %s — %r", in_port, e)
            return

        if out_port:
            try:
                self._outport = mido.open_output(out_port)
                logger.info("USB MIDI output: %s", out_port)
            except Exception as e:
                logger.warning("Could not open MIDI output %s — %r", out_port, e)

        self._mido = mido
        self.available = True

    def iter_pending(self) -> list[tuple[int, int, int]]:
        if self._inport is None:
            return []
        result = []
        for msg in self._inport.iter_pending():
            if msg.type == "pitchwheel":
                raw = msg.pitch + 8192
                lsb = raw & 0x7F
                msb = (raw >> 7) & 0x7F
                result.append((0xE0 | msg.channel, lsb, msb))
        return result

    def send_pitchbend(self, channel: int, value_14bit: int) -> None:
        if self._outport is None or self._mido is None:
            return
        pitch = value_14bit - 8192
        self._outport.send(self._mido.Message("pitchwheel", channel=channel, pitch=pitch))

    def close(self) -> None:
        if self._inport is not None:
            self._inport.close()
        if self._outport is not None:
            self._outport.close()


class _NetworkTransport:
    """RTP-MIDI network transport."""

    def __init__(self, host: str, port: int = 5004) -> None:
        from shuffle_party.rtpmidi import RtpMidiClient

        self.available = False
        self._client = RtpMidiClient(host, port, name="ShuffleParty")
        if self._client.connect():
            self.available = True
            logger.info("RTP-MIDI connected to %s:%d", host, port)
        else:
            logger.warning("RTP-MIDI connection to %s:%d failed.", host, port)

    def iter_pending(self) -> list[tuple[int, int, int]]:
        result = []
        for msg in self._client.recv_midi():
            if len(msg) >= 3 and (msg[0] & 0xF0) == 0xE0:
                result.append((msg[0], msg[1], msg[2]))
        return result

    def send_pitchbend(self, channel: int, value_14bit: int) -> None:
        lsb = value_14bit & 0x7F
        msb = (value_14bit >> 7) & 0x7F
        self._client.send_midi(bytes([0xE0 | channel, lsb, msb]))

    def close(self) -> None:
        self._client.close()


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

    Connects via RTP-MIDI (network) if a host is given, otherwise USB MIDI.
    """

    def __init__(
        self,
        port_name: str,
        channel_map: list[list[int]],
        *,
        network_host: str = "",
    ) -> None:
        self._transport: _UsbTransport | _NetworkTransport | None = None
        self._available = False
        self._channel_map = channel_map
        self._last_sent: dict[int, int] = {}  # fader_index -> last raw value sent
        self._levels: list[float] = [0.0] * len(channel_map)
        self._master_last_sent: int | None = None

        if network_host:
            transport = _NetworkTransport(network_host)
            if transport.available:
                self._transport = transport
                self._available = True
                return

        transport_usb = _UsbTransport(port_name)
        if transport_usb.available:
            self._transport = transport_usb
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
        if not self._available or self._transport is None:
            return {}, None

        changed: dict[int, float] = {}
        master: float | None = None
        for status, d1, d2 in self._transport.iter_pending():
            if (status & 0xF0) != 0xE0:
                continue
            channel = status & 0x0F
            raw = d1 | (d2 << 7)
            if channel == _MASTER_FADER:
                if self._master_last_sent is not None and raw == self._master_last_sent:
                    self._master_last_sent = None
                    continue
                master = raw / _FADER_MAX
            elif 0 <= channel < len(self._channel_map):
                if self._last_sent.get(channel) == raw:
                    del self._last_sent[channel]
                    continue
                value = raw / _FADER_MAX
                self._levels[channel] = value
                changed[channel] = value

        return changed, master

    def set_fader(self, index: int, value: float) -> None:
        """Move a motorized fader to the given position (0.0–1.0)."""
        if self._transport is None:
            return
        if index < 0 or index >= len(self._channel_map):
            return
        raw = int(max(0.0, min(1.0, value)) * _FADER_MAX)
        self._last_sent[index] = raw
        self._transport.send_pitchbend(index, raw)

    def set_master_fader(self, value: float) -> None:
        """Move the master fader (fader 8) to the given position (0.0–1.0)."""
        if self._transport is None:
            return
        raw = int(max(0.0, min(1.0, value)) * _FADER_MAX)
        self._master_last_sent = raw
        self._transport.send_pitchbend(_MASTER_FADER, raw)

    def fader_index_for_channels(self, channels: list[int]) -> int | None:
        """Find the fader index that controls the given XR12 channels."""
        target = set(channels)
        for i, mapped in enumerate(self._channel_map):
            if target & set(mapped):
                return i
        return None

    def close(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        self._available = False
