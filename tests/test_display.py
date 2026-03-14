"""Tests for countdown display logic (no pygame rendering)."""

import pytest
from shuffle_party.display import Display


class TestDisplay:

    def test_initial_remaining_equals_set_duration(self):
        display = Display(set_duration=900)
        assert display.remaining_seconds == 900

    def test_tick_decrements_by_one(self):
        display = Display(set_duration=10)
        display.tick()
        assert display.remaining_seconds == 9

    def test_tick_returns_false_when_time_remaining(self):
        display = Display(set_duration=10)
        assert display.tick() is False

    def test_tick_returns_true_when_timer_expires(self):
        display = Display(set_duration=1)
        assert display.tick() is True

    def test_tick_does_not_go_negative(self):
        display = Display(set_duration=1)
        display.tick()  # 0
        display.tick()  # still 0
        assert display.remaining_seconds == 0

    def test_start_timer_resets_countdown(self):
        display = Display(set_duration=900)
        for _ in range(100):
            display.tick()
        display.start_timer()
        assert display.remaining_seconds == 900

    def test_format_time_mm_ss(self):
        display = Display(set_duration=754)
        assert display.format_time() == "12:34"

    def test_format_time_zero(self):
        display = Display(set_duration=0)
        assert display.format_time() == "00:00"

    def test_format_time_just_seconds(self):
        display = Display(set_duration=5)
        assert display.format_time() == "00:05"
