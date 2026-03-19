"""Minimal RTP-MIDI (AppleMIDI) client for the Behringer X-TOUCH EXTENDER.

Implements the AppleMIDI session protocol (invitation, sync) and RTP-MIDI
data transport over UDP. This allows bidirectional MIDI communication with
the EXTENDER over Ethernet, without relying on macOS Audio MIDI Setup.

Automatically reconnects when the session is lost (device power cycle,
network interruption, or BYE from remote).

References:
  - RFC 6295 (RTP-MIDI)
  - Apple MIDI Network Driver Protocol
"""

from __future__ import annotations

import logging
import random
import socket
import struct
import threading
import time
from collections import deque

logger = logging.getLogger(__name__)

# AppleMIDI signature (0xFFFF) + command codes
_SIGNATURE = 0xFFFF
_CMD_IN = b"IN"  # Invitation
_CMD_OK = b"OK"  # Accept
_CMD_NO = b"NO"  # Reject
_CMD_BY = b"BY"  # Bye
_CMD_CK = b"CK"  # Clock sync

# RTP-MIDI constants
_RTP_VERSION = 2
_RTP_PAYLOAD_TYPE = 0x61
_PROTOCOL_VERSION = 2

# Timing
_SYNC_INTERVAL = 10.0    # seconds between clock syncs
_SYNC_TIMEOUT = 30.0     # seconds without sync before declaring disconnected
_INVITE_TIMEOUT = 5.0    # seconds to wait for invitation response
_RECONNECT_INTERVAL = 3.0  # seconds between reconnection attempts
_RECV_TIMEOUT = 0.01     # socket recv timeout for polling


def _ts_now() -> int:
    """Return current timestamp in 100-microsecond units (AppleMIDI convention)."""
    return int(time.monotonic() * 10000) & 0xFFFFFFFFFFFFFFFF


class RtpMidiClient:
    """RTP-MIDI client that connects to a remote device.

    Establishes an AppleMIDI session and provides send/receive for raw MIDI
    bytes. Automatically reconnects when the connection is lost.
    """

    def __init__(self, host: str, port: int = 5004, name: str = "ShuffleParty") -> None:
        self._host = host
        self._control_port = port
        self._data_port = port + 1
        self._name = name
        self._ssrc = random.randint(1, 0xFFFFFFFF)
        self._remote_ssrc: int | None = None
        self._seq = random.randint(0, 0xFFFF)
        self._connected = False
        self._last_sync = 0.0

        # Sockets (created fresh on each connect)
        self._ctrl_sock: socket.socket | None = None
        self._data_sock: socket.socket | None = None

        # Incoming MIDI message queue (thread-safe)
        self._inbox: deque[bytes] = deque(maxlen=256)

        # Background threads
        self._running = False
        self._recv_thread: threading.Thread | None = None
        self._sync_thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def connected(self) -> bool:
        return self._connected

    def _create_sockets(self) -> bool:
        """Create fresh UDP socket pair. Returns True on success."""
        self._close_sockets()
        try:
            self._ctrl_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._data_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._ctrl_sock.settimeout(_RECV_TIMEOUT)
            self._data_sock.settimeout(_RECV_TIMEOUT)
            self._ctrl_sock.bind(("", 0))
            self._data_sock.bind(("", self._ctrl_sock.getsockname()[1] + 1))
            return True
        except OSError as e:
            logger.warning("Could not create sockets — %r", e)
            self._close_sockets()
            return False

    def _close_sockets(self) -> None:
        """Close sockets if open."""
        for sock in (self._ctrl_sock, self._data_sock):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
        self._ctrl_sock = None
        self._data_sock = None

    def connect(self) -> bool:
        """Initiate the AppleMIDI session. Returns True if accepted."""
        if not self._create_sockets():
            return False

        token = random.randint(1, 0xFFFFFFFF)

        # Invite on control port
        if not self._send_invite(self._ctrl_sock, self._control_port, token):
            self._close_sockets()
            return False

        # Invite on data port
        if not self._send_invite(self._data_sock, self._data_port, token):
            self._close_sockets()
            return False

        self._connected = True
        self._last_sync = time.monotonic()
        self._running = True

        # Start background receiver and sync threads
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()
        self._sync_thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._sync_thread.start()

        logger.info("RTP-MIDI session established with %s:%d (SSRC=%08x)",
                     self._host, self._control_port, self._remote_ssrc or 0)
        return True

    def _reconnect(self) -> bool:
        """Tear down the current session and establish a new one."""
        logger.info("Reconnecting to %s:%d...", self._host, self._control_port)
        self._running = False
        self._connected = False
        self._close_sockets()

        # Wait for threads to exit
        for thread in (self._recv_thread, self._sync_thread):
            if thread is not None and thread.is_alive():
                thread.join(timeout=2.0)
        self._recv_thread = None
        self._sync_thread = None

        # Fresh SSRC for the new session
        self._ssrc = random.randint(1, 0xFFFFFFFF)
        self._remote_ssrc = None
        self._inbox.clear()

        return self.connect()

    def _send_invite(self, sock: socket.socket, port: int, token: int) -> bool:
        """Send an invitation and wait for OK response."""
        name_bytes = self._name.encode("utf-8")
        pkt = struct.pack(">HH I I I",
                          _SIGNATURE, int.from_bytes(_CMD_IN, "big"),
                          _PROTOCOL_VERSION, token, self._ssrc)
        pkt += name_bytes + b"\x00"

        sock.sendto(pkt, (self._host, port))

        deadline = time.monotonic() + _INVITE_TIMEOUT
        while time.monotonic() < deadline:
            try:
                data, addr = sock.recvfrom(256)
            except socket.timeout:
                continue
            if len(data) < 16:
                continue
            sig, cmd = struct.unpack(">HH", data[:4])
            if sig == _SIGNATURE and struct.pack(">H", cmd) == _CMD_OK:
                _, _, _, remote_ssrc = struct.unpack(">I I I I", data[4:20])
                self._remote_ssrc = remote_ssrc
                logger.debug("Invitation accepted on port %d (remote SSRC=%08x)", port, remote_ssrc)
                return True

        logger.warning("Invitation timed out on port %d", port)
        return False

    def send_midi(self, *messages: bytes) -> None:
        """Send one or more raw MIDI messages in a single RTP packet."""
        if not self._connected or self._data_sock is None:
            return

        # Build MIDI command section
        midi_payload = b""
        for msg in messages:
            midi_payload += msg

        # MIDI header: B=0, J=0, Z=0, P=0, length in lower 4 bits
        length = len(midi_payload)
        if length < 16:
            midi_header = bytes([length])  # short header, B=0
        else:
            midi_header = struct.pack(">H", length & 0x0FFF)  # long header, B=0

        # RTP header (M=0, matching X-TOUCH EXTENDER format)
        ts = _ts_now() & 0xFFFFFFFF
        self._seq = (self._seq + 1) & 0xFFFF
        rtp = struct.pack(">BBHII",
                          (_RTP_VERSION << 6) | 0,  # V=2, P=0, X=0, CC=0
                          _RTP_PAYLOAD_TYPE,         # M=0, PT=0x61
                          self._seq, ts, self._ssrc)

        pkt = rtp + midi_header + midi_payload
        try:
            self._data_sock.sendto(pkt, (self._host, self._data_port))
        except OSError:
            self._connected = False

    def recv_midi(self) -> list[bytes]:
        """Return all MIDI messages received since last call."""
        result = []
        while self._inbox:
            result.append(self._inbox.popleft())
        return result

    def _recv_loop(self) -> None:
        """Background thread: receive and parse incoming RTP-MIDI packets."""
        while self._running:
            if self._data_sock is None:
                break

            # Check data socket
            try:
                data, addr = self._data_sock.recvfrom(1024)
            except socket.timeout:
                self._handle_control()
                self._check_sync_timeout()
                continue
            except OSError:
                break

            if len(data) < 4:
                continue

            # Check if it's an AppleMIDI command (sync etc)
            sig = struct.unpack(">H", data[:2])[0]
            if sig == _SIGNATURE:
                self._handle_applemidi(data, self._data_sock, self._data_port)
                continue

            if len(data) < 13:
                continue

            # Parse RTP header
            payload = data[12:]
            if payload:
                self._parse_midi_payload(payload)

            self._handle_control()

    def _handle_control(self) -> None:
        """Check control socket for sync packets."""
        if self._ctrl_sock is None:
            return
        try:
            data, addr = self._ctrl_sock.recvfrom(256)
        except socket.timeout:
            return
        except OSError:
            return
        if len(data) >= 4:
            sig = struct.unpack(">H", data[:2])[0]
            if sig == _SIGNATURE:
                self._handle_applemidi(data, self._ctrl_sock, self._control_port)

    def _check_sync_timeout(self) -> None:
        """Detect connection loss via sync timeout."""
        if self._connected and (time.monotonic() - self._last_sync) > _SYNC_TIMEOUT:
            logger.warning("No sync from %s for %.0fs — connection lost.",
                           self._host, _SYNC_TIMEOUT)
            self._connected = False

    def _handle_applemidi(self, data: bytes, sock: socket.socket, port: int) -> None:
        """Handle AppleMIDI session commands (sync, bye)."""
        if len(data) < 4:
            return
        cmd = data[2:4]
        if cmd == _CMD_CK:
            self._handle_sync(data, sock, port)
        elif cmd == _CMD_BY:
            logger.info("Remote sent BYE — session ended.")
            self._connected = False

    def _handle_sync(self, data: bytes, sock: socket.socket, port: int) -> None:
        """Respond to clock sync requests on the same socket that received them."""
        if len(data) < 36:
            return
        _, _, ssrc, count, ts1, ts2, ts3 = struct.unpack(">HH I B xxx Q Q Q", data[:36])

        self._last_sync = time.monotonic()

        if count == 0:
            resp = struct.pack(">HH I B xxx Q Q Q",
                               _SIGNATURE, int.from_bytes(_CMD_CK, "big"),
                               self._ssrc, 1, ts1, _ts_now(), 0)
            sock.sendto(resp, (self._host, port))
        elif count == 1:
            resp = struct.pack(">HH I B xxx Q Q Q",
                               _SIGNATURE, int.from_bytes(_CMD_CK, "big"),
                               self._ssrc, 2, ts1, ts2, _ts_now())
            sock.sendto(resp, (self._host, port))

    def _parse_midi_payload(self, payload: bytes) -> None:
        """Extract MIDI messages from RTP-MIDI payload."""
        if not payload:
            return

        # Read MIDI command header
        header_byte = payload[0]

        if header_byte & 0x40:  # long header
            if len(payload) < 2:
                return
            length = struct.unpack(">H", payload[:2])[0] & 0x0FFF
            midi_data = payload[2:2 + length]
        else:
            length = header_byte & 0x0F
            midi_data = payload[1:1 + length]

        # Split into individual MIDI messages
        i = 0
        running_status = 0
        while i < len(midi_data):
            byte = midi_data[i]
            if byte >= 0xF0:
                # System message
                if byte == 0xF0:  # SysEx
                    end = midi_data.find(0xF7, i)
                    if end >= 0:
                        self._inbox.append(midi_data[i:end + 1])
                        i = end + 1
                    else:
                        break
                else:
                    i += 1
            elif byte >= 0x80:
                running_status = byte
                msg_type = byte & 0xF0
                if msg_type in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
                    if i + 2 < len(midi_data):
                        self._inbox.append(midi_data[i:i + 3])
                        i += 3
                    else:
                        break
                elif msg_type in (0xC0, 0xD0):
                    if i + 1 < len(midi_data):
                        self._inbox.append(midi_data[i:i + 2])
                        i += 2
                    else:
                        break
                else:
                    i += 1
            elif running_status:
                msg_type = running_status & 0xF0
                if msg_type in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
                    if i + 1 < len(midi_data):
                        self._inbox.append(bytes([running_status]) + midi_data[i:i + 2])
                        i += 2
                    else:
                        break
                elif msg_type in (0xC0, 0xD0):
                    self._inbox.append(bytes([running_status, byte]))
                    i += 1
                else:
                    i += 1
            else:
                i += 1

    def _sync_loop(self) -> None:
        """Background thread: send periodic clock sync and handle reconnection."""
        while self._running:
            if self._connected and self._ctrl_sock is not None:
                ts = _ts_now()
                pkt = struct.pack(">HH I B xxx Q Q Q",
                                  _SIGNATURE, int.from_bytes(_CMD_CK, "big"),
                                  self._ssrc, 0, ts, 0, 0)
                try:
                    self._ctrl_sock.sendto(pkt, (self._host, self._control_port))
                except OSError:
                    self._connected = False
                time.sleep(_SYNC_INTERVAL)
            else:
                # Connection lost — attempt reconnect
                time.sleep(_RECONNECT_INTERVAL)
                if self._running and not self._connected:
                    with self._lock:
                        if not self._connected:
                            self._attempt_reconnect()

    def _attempt_reconnect(self) -> None:
        """Try to re-establish the session. Called from sync thread."""
        self._close_sockets()
        if not self._create_sockets():
            return

        self._ssrc = random.randint(1, 0xFFFFFFFF)
        self._remote_ssrc = None
        token = random.randint(1, 0xFFFFFFFF)

        if not self._send_invite(self._ctrl_sock, self._control_port, token):
            self._close_sockets()
            return

        if not self._send_invite(self._data_sock, self._data_port, token):
            self._close_sockets()
            return

        self._connected = True
        self._last_sync = time.monotonic()
        self._inbox.clear()
        logger.info("RTP-MIDI reconnected to %s:%d", self._host, self._control_port)

    def close(self) -> None:
        """Send BYE and clean up."""
        self._running = False
        if self._connected and self._ctrl_sock is not None:
            bye = struct.pack(">HH I I",
                              _SIGNATURE, int.from_bytes(_CMD_BY, "big"),
                              _PROTOCOL_VERSION, self._ssrc)
            try:
                self._ctrl_sock.sendto(bye, (self._host, self._control_port))
            except OSError:
                pass
        self._connected = False

        # Wait for threads to exit
        for thread in (self._recv_thread, self._sync_thread):
            if thread is not None and thread.is_alive():
                thread.join(timeout=2.0)

        self._close_sockets()
