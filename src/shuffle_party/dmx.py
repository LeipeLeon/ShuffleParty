"""Enttec DMX USB Pro driver.

Sends DMX frames over serial using the Enttec Pro packet protocol.
Auto-detects the device on macOS and Linux.
"""

import logging

import serial
import serial.tools.list_ports

logger = logging.getLogger(__name__)

ENTTEC_START = 0x7E
ENTTEC_END = 0xE7
ENTTEC_SEND_DMX = 6
DMX_CHANNELS = 512


class DmxOutput:
    """Sends DMX frames via an Enttec DMX USB Pro (or compatible)."""

    def __init__(self, port: str | None = None) -> None:
        self._serial: serial.Serial | None = None
        self._dmx = bytearray(DMX_CHANNELS)
        self._connect(port)

    def _connect(self, port: str | None) -> None:
        if port is None:
            port = self._find_device()
        if port is None:
            logger.warning("No Enttec DMX USB Pro found. Continuing without DMX output.")
            return
        try:
            self._serial = serial.Serial(port, baudrate=57600, timeout=1)
            logger.info("DMX output on %s", port)
        except Exception as e:
            logger.warning(f"Could not open DMX device {port} — {e!r}")

    def _find_device(self) -> str | None:
        for p in serial.tools.list_ports.comports():
            if "usbserial" in (p.device or "").lower() or "ttyUSB" in (p.device or ""):
                logger.info("Auto-detected DMX device: %s (%s)", p.device, p.description)
                return p.device
        return None

    @property
    def available(self) -> bool:
        return self._serial is not None

    def set_channel(self, channel: int, value: int) -> None:
        """Set a single DMX channel (1-indexed) to a value (0–255)."""
        if 1 <= channel <= DMX_CHANNELS:
            self._dmx[channel - 1] = max(0, min(255, value))

    def set_channels(self, start: int, values: list[int]) -> None:
        """Set multiple consecutive channels starting at start (1-indexed)."""
        for i, v in enumerate(values):
            self.set_channel(start + i, v)

    def blackout(self) -> None:
        """Set all channels to 0."""
        self._dmx = bytearray(DMX_CHANNELS)

    def flush(self) -> None:
        """Send the current DMX frame to the device."""
        if self._serial is None:
            return
        # Enttec Pro packet: start, label, length_lsb, length_msb, [start_code + data], end
        data = b"\x00" + bytes(self._dmx)  # start code 0x00 + 512 channels
        length = len(data)
        packet = bytes([
            ENTTEC_START,
            ENTTEC_SEND_DMX,
            length & 0xFF,
            (length >> 8) & 0xFF,
        ]) + data + bytes([ENTTEC_END])
        try:
            self._serial.write(packet)
        except Exception as e:
            logger.warning(f"DMX write error — {e!r}")

    def close(self) -> None:
        if self._serial is not None:
            self.blackout()
            self.flush()
            self._serial.close()
            self._serial = None
