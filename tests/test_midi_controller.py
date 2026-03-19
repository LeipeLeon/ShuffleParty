"""Tests for the MIDI controller module (X-TOUCH EXTENDER)."""

from unittest.mock import MagicMock, patch

import pytest

from shuffle_party.midi_controller import (
    MidiExtender,
    _MASTER_FADER,
    _find_port,
    build_channel_map,
)


# -- _find_port --

def test_find_port_by_hint():
    names = ["X-Touch-Ext X-TOUCH_INT", "USB MIDI Interface"]
    assert _find_port(names, "X-Touch-Ext", "x-touch ext") == "X-Touch-Ext X-TOUCH_INT"


def test_find_port_by_keyword():
    names = ["X-Touch-Ext X-TOUCH_INT", "USB MIDI Interface"]
    assert _find_port(names, "", "x-touch-ext") == "X-Touch-Ext X-TOUCH_INT"


def test_find_port_no_match():
    names = ["USB MIDI Interface"]
    assert _find_port(names, "", "x-touch ext") is None


def test_find_port_empty_list():
    assert _find_port([], "whatever", "whatever") is None


# -- build_channel_map --

def test_channel_map_no_pairs():
    result = build_channel_map(dj_channels=[3, 3], shuffle_channels=[1, 1])
    assert result == [[1], [2], [3], [4], [5], [6], [7]]


def test_channel_map_with_stereo_pairs():
    result = build_channel_map(
        dj_channels=[3, 4], shuffle_channels=[1, 2],
    )
    assert result == [[1, 2], [3, 4], [5], [6], [7], [8], [9]]
    assert len(result) == 7


def test_channel_map_capped_at_7():
    result = build_channel_map(
        dj_channels=[3, 3], shuffle_channels=[1, 1], total_channels=12,
    )
    assert len(result) == 7


def test_channel_map_fewer_channels():
    result = build_channel_map(
        dj_channels=[1, 1], shuffle_channels=[2, 2], total_channels=4,
    )
    assert result == [[1], [2], [3], [4]]


# -- Mock transport for MidiExtender tests --

def _make_pitchbend_tuple(channel, value_01):
    """Create a (status, lsb, msb) pitchbend tuple."""
    raw = int(value_01 * 16383)
    lsb = raw & 0x7F
    msb = (raw >> 7) & 0x7F
    return (0xE0 | channel, lsb, msb)


class MockTransport:
    """Mock MIDI transport for testing."""

    def __init__(self):
        self.available = True
        self.pending: list[tuple[int, int, int]] = []
        self.sent: list[tuple[int, int]] = []  # (channel, value_14bit)
        self.closed = False

    def iter_pending(self):
        result = list(self.pending)
        self.pending.clear()
        return result

    def send_pitchbend(self, channel, value_14bit):
        self.sent.append((channel, value_14bit))

    def close(self):
        self.closed = True


@pytest.fixture
def extender():
    """Create a MidiExtender with a mock transport."""
    channel_map = [[1, 2], [3, 4], [5], [6], [7]]
    # Bypass __init__ transport creation by patching _UsbTransport
    with patch("shuffle_party.midi_controller._UsbTransport") as MockUsb:
        mock_usb = MagicMock()
        mock_usb.available = False
        MockUsb.return_value = mock_usb
        ext = MidiExtender("", channel_map)

    # Inject our mock transport
    transport = MockTransport()
    ext._transport = transport
    ext._available = True
    return ext


def test_poll_channel_fader(extender):
    extender._transport.pending = [_make_pitchbend_tuple(0, 0.5)]
    changed, master = extender.poll()
    assert 0 in changed
    assert abs(changed[0] - 0.5) < 0.001
    assert master is None


def test_poll_master_fader(extender):
    extender._transport.pending = [_make_pitchbend_tuple(_MASTER_FADER, 0.75)]
    changed, master = extender.poll()
    assert changed == {}
    assert master is not None
    assert abs(master - 0.75) < 0.001


def test_poll_both_channel_and_master(extender):
    extender._transport.pending = [
        _make_pitchbend_tuple(2, 0.3),
        _make_pitchbend_tuple(_MASTER_FADER, 0.9),
    ]
    changed, master = extender.poll()
    assert 2 in changed
    assert abs(changed[2] - 0.3) < 0.001
    assert abs(master - 0.9) < 0.001


def test_poll_ignores_echo_from_set_fader(extender):
    extender.set_fader(0, 0.5)
    raw = int(0.5 * 16383)
    extender._transport.pending = [_make_pitchbend_tuple(0, 0.5)]
    changed, master = extender.poll()
    assert changed == {}


def test_poll_ignores_master_echo(extender):
    extender.set_master_fader(0.8)
    extender._transport.pending = [_make_pitchbend_tuple(_MASTER_FADER, 0.8)]
    changed, master = extender.poll()
    assert master is None


def test_poll_no_messages(extender):
    changed, master = extender.poll()
    assert changed == {}
    assert master is None


def test_poll_ignores_non_pitchwheel(extender):
    extender._transport.pending = [(0xB0, 7, 127)]  # CC message
    changed, master = extender.poll()
    assert changed == {}
    assert master is None


def test_set_fader_sends_pitchbend(extender):
    extender.set_fader(2, 1.0)
    assert len(extender._transport.sent) == 1
    channel, value = extender._transport.sent[0]
    assert channel == 2
    assert value == 16383


def test_set_master_fader_sends_pitchbend(extender):
    extender.set_master_fader(0.0)
    assert len(extender._transport.sent) == 1
    channel, value = extender._transport.sent[0]
    assert channel == _MASTER_FADER
    assert value == 0


def test_set_fader_clamps_value(extender):
    extender.set_fader(0, 1.5)
    assert extender._transport.sent[-1] == (0, 16383)

    extender.set_fader(0, -0.5)
    assert extender._transport.sent[-1] == (0, 0)


def test_set_fader_out_of_range_ignored(extender):
    extender.set_fader(99, 0.5)
    assert len(extender._transport.sent) == 0

    extender.set_fader(-1, 0.5)
    assert len(extender._transport.sent) == 0


def test_fader_index_for_channels(extender):
    assert extender.fader_index_for_channels([1, 2]) == 0
    assert extender.fader_index_for_channels([3, 4]) == 1
    assert extender.fader_index_for_channels([5]) == 2
    assert extender.fader_index_for_channels([99]) is None


def test_close(extender):
    extender.close()
    assert not extender.available
    assert extender._transport is None


def test_not_available_when_no_transport():
    with patch("shuffle_party.midi_controller._UsbTransport") as MockUsb:
        mock_usb = MagicMock()
        mock_usb.available = False
        MockUsb.return_value = mock_usb
        ext = MidiExtender("", [[1]])
    assert not ext.available
    changed, master = ext.poll()
    assert changed == {}
    assert master is None
