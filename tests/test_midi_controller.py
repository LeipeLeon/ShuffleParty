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
    # keyword must match as substring of lowered name: "x-touch-ext" contains "x-touch"
    assert _find_port(names, "", "x-touch") == "X-Touch-Ext X-TOUCH_INT"


def test_find_port_no_match():
    names = ["USB MIDI Interface"]
    assert _find_port(names, "", "x-touch ext") is None


def test_find_port_empty_list():
    assert _find_port([], "whatever", "whatever") is None


# -- build_channel_map --

def test_channel_map_no_pairs():
    result = build_channel_map(dj_channels=[3, 3], shuffle_channels=[1, 1])
    # No stereo pairs, channels 1–7 each get a fader (capped at 7)
    assert result == [[1], [2], [3], [4], [5], [6], [7]]


def test_channel_map_with_stereo_pairs():
    result = build_channel_map(
        dj_channels=[3, 4], shuffle_channels=[1, 2],
    )
    # Ch 1+2 paired, ch 3+4 paired, then 5,6,7,8,9,10 singles = 7 faders (capped)
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


# -- MidiExtender with mocked MIDI --

def _make_pitchwheel(channel, value_01):
    """Create a mock pitchwheel message for the given channel and 0.0–1.0 value."""
    raw = int(value_01 * 16383)
    msg = MagicMock()
    msg.type = "pitchwheel"
    msg.channel = channel
    msg.pitch = raw - 8192
    return msg


@pytest.fixture
def extender():
    """Create a MidiExtender with mocked MIDI ports."""
    channel_map = [[1, 2], [3, 4], [5], [6], [7]]
    with patch("shuffle_party.midi_controller._open_ports") as mock_open:
        mock_mido = MagicMock()
        mock_inport = MagicMock()
        mock_outport = MagicMock()
        mock_open.return_value = (mock_mido, mock_inport, mock_outport)
        ext = MidiExtender("", channel_map)
    assert ext.available
    return ext


def test_poll_channel_fader(extender):
    msg = _make_pitchwheel(0, 0.5)
    extender._inport.iter_pending.return_value = [msg]

    changed, master = extender.poll()

    assert 0 in changed
    assert abs(changed[0] - 0.5) < 0.001
    assert master is None


def test_poll_master_fader(extender):
    msg = _make_pitchwheel(_MASTER_FADER, 0.75)
    extender._inport.iter_pending.return_value = [msg]

    changed, master = extender.poll()

    assert changed == {}
    assert master is not None
    assert abs(master - 0.75) < 0.001


def test_poll_both_channel_and_master(extender):
    msgs = [_make_pitchwheel(2, 0.3), _make_pitchwheel(_MASTER_FADER, 0.9)]
    extender._inport.iter_pending.return_value = msgs

    changed, master = extender.poll()

    assert 2 in changed
    assert abs(changed[2] - 0.3) < 0.001
    assert abs(master - 0.9) < 0.001


def test_poll_ignores_echo_from_set_fader(extender):
    # Simulate sending a value, then receiving the echo
    extender.set_fader(0, 0.5)
    raw = int(0.5 * 16383)
    echo = _make_pitchwheel(0, 0.5)
    echo.pitch = raw - 8192  # exact match
    extender._inport.iter_pending.return_value = [echo]

    changed, master = extender.poll()

    assert changed == {}


def test_poll_ignores_master_echo(extender):
    extender.set_master_fader(0.8)
    echo = _make_pitchwheel(_MASTER_FADER, 0.8)
    raw = int(0.8 * 16383)
    echo.pitch = raw - 8192
    extender._inport.iter_pending.return_value = [echo]

    changed, master = extender.poll()

    assert master is None


def test_poll_no_messages(extender):
    extender._inport.iter_pending.return_value = []
    changed, master = extender.poll()
    assert changed == {}
    assert master is None


def test_poll_ignores_non_pitchwheel(extender):
    msg = MagicMock()
    msg.type = "control_change"
    extender._inport.iter_pending.return_value = [msg]

    changed, master = extender.poll()

    assert changed == {}
    assert master is None


def test_set_fader_sends_pitchwheel(extender):
    extender.set_fader(2, 1.0)
    extender._outport.send.assert_called_once()
    sent = extender._outport.send.call_args[0][0]
    extender._mido.Message.assert_called_with("pitchwheel", channel=2, pitch=16383 - 8192)


def test_set_master_fader_sends_pitchwheel(extender):
    extender.set_master_fader(0.0)
    extender._outport.send.assert_called_once()
    extender._mido.Message.assert_called_with("pitchwheel", channel=_MASTER_FADER, pitch=-8192)


def test_set_fader_clamps_value(extender):
    extender.set_fader(0, 1.5)  # above max
    extender._mido.Message.assert_called_with("pitchwheel", channel=0, pitch=16383 - 8192)

    extender._mido.reset_mock()
    extender.set_fader(0, -0.5)  # below min
    extender._mido.Message.assert_called_with("pitchwheel", channel=0, pitch=-8192)


def test_set_fader_out_of_range_ignored(extender):
    extender.set_fader(99, 0.5)
    extender._outport.send.assert_not_called()

    extender.set_fader(-1, 0.5)
    extender._outport.send.assert_not_called()


def test_fader_index_for_channels(extender):
    assert extender.fader_index_for_channels([1, 2]) == 0
    assert extender.fader_index_for_channels([3, 4]) == 1
    assert extender.fader_index_for_channels([5]) == 2
    assert extender.fader_index_for_channels([99]) is None


def test_close(extender):
    inport = extender._inport
    outport = extender._outport
    extender.close()
    assert not extender.available
    inport.close.assert_called_once()
    outport.close.assert_called_once()


def test_not_available_when_no_midi():
    with patch("shuffle_party.midi_controller._open_ports") as mock_open:
        mock_open.return_value = (None, None, None)
        ext = MidiExtender("", [[1]])
    assert not ext.available
    changed, master = ext.poll()
    assert changed == {}
    assert master is None
