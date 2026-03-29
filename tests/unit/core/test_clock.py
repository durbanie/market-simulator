"""Tests for the Clock class."""

import time

import pytest

from market_simulator.core.clock import Clock, ClockMode


class TestFastSimulationMode:
    def test_initial_time_defaults_to_zero(self):
        clock = Clock(mode=ClockMode.FAST_SIMULATION)
        assert clock.now() == 0

    def test_initial_time_from_offset(self):
        clock = Clock(mode=ClockMode.FAST_SIMULATION, offset_us=1000)
        assert clock.now() == 1000

    def test_advance_increases_time(self):
        clock = Clock(mode=ClockMode.FAST_SIMULATION)
        clock.advance(500)
        assert clock.now() == 500
        clock.advance(300)
        assert clock.now() == 800

    def test_advance_by_zero(self):
        clock = Clock(mode=ClockMode.FAST_SIMULATION, offset_us=100)
        clock.advance(0)
        assert clock.now() == 100

    def test_advance_negative_raises(self):
        clock = Clock(mode=ClockMode.FAST_SIMULATION)
        with pytest.raises(ValueError, match="non-negative"):
            clock.advance(-1)

    def test_fast_forward_sets_time(self):
        clock = Clock(mode=ClockMode.FAST_SIMULATION)
        clock.fast_forward(5000)
        assert clock.now() == 5000

    def test_fast_forward_to_current_time(self):
        clock = Clock(mode=ClockMode.FAST_SIMULATION, offset_us=100)
        clock.fast_forward(100)
        assert clock.now() == 100

    def test_fast_forward_to_past_raises(self):
        clock = Clock(mode=ClockMode.FAST_SIMULATION, offset_us=1000)
        with pytest.raises(ValueError, match="before current time"):
            clock.fast_forward(999)

    def test_fast_forward_does_not_sleep(self):
        clock = Clock(mode=ClockMode.FAST_SIMULATION)
        start = time.monotonic()
        clock.fast_forward(10_000_000_000)  # 10000 seconds in the future
        elapsed = time.monotonic() - start
        assert elapsed < 0.1


class TestRealTimeMode:
    def test_now_returns_wall_time(self):
        clock = Clock(mode=ClockMode.REAL_TIME)
        before = int(time.time() * 1_000_000)
        result = clock.now()
        after = int(time.time() * 1_000_000)
        assert before <= result <= after

    def test_now_with_offset(self):
        offset = 1_000_000  # 1 second offset
        clock = Clock(mode=ClockMode.REAL_TIME, offset_us=offset)
        wall = int(time.time() * 1_000_000)
        result = clock.now()
        # Result should be approximately wall + offset (within 100ms tolerance)
        assert abs(result - (wall + offset)) < 100_000

    def test_advance_raises(self):
        clock = Clock(mode=ClockMode.REAL_TIME)
        with pytest.raises(RuntimeError, match="REAL_TIME mode"):
            clock.advance(100)

    def test_fast_forward_raises(self):
        clock = Clock(mode=ClockMode.REAL_TIME)
        with pytest.raises(RuntimeError, match="REAL_TIME mode"):
            clock.fast_forward(100)


class TestRealTimeSimulationMode:
    def test_now_returns_modeled_time(self):
        clock = Clock(mode=ClockMode.REAL_TIME_SIMULATION, offset_us=5000)
        assert clock.now() == 5000

    def test_advance_increases_time(self):
        clock = Clock(mode=ClockMode.REAL_TIME_SIMULATION)
        clock.advance(500)
        assert clock.now() == 500

    def test_advance_to_past_wall_time_does_not_sleep(self):
        # offset_us=0 means modeled time starts at 0, far in the past.
        clock = Clock(mode=ClockMode.REAL_TIME_SIMULATION)
        start = time.monotonic()
        clock.advance(1000)  # Still far in the past
        elapsed = time.monotonic() - start
        assert elapsed < 0.1
        assert clock.now() == 1000

    def test_advance_to_future_wall_time_sleeps(self):
        wall_us = int(time.time() * 1_000_000)
        clock = Clock(mode=ClockMode.REAL_TIME_SIMULATION, offset_us=wall_us)
        start = time.monotonic()
        clock.advance(200_000)  # 200ms ahead of wall time
        elapsed = time.monotonic() - start
        assert elapsed >= 0.15
        assert elapsed < 0.5
        assert clock.now() == wall_us + 200_000

    def test_fast_forward_to_past_wall_time_does_not_sleep(self):
        clock = Clock(mode=ClockMode.REAL_TIME_SIMULATION)
        start = time.monotonic()
        clock.fast_forward(1000)  # Still far in the past
        elapsed = time.monotonic() - start
        assert elapsed < 0.1
        assert clock.now() == 1000

    def test_fast_forward_to_future_wall_time_sleeps(self):
        wall_us = int(time.time() * 1_000_000)
        clock = Clock(mode=ClockMode.REAL_TIME_SIMULATION, offset_us=wall_us)
        target = wall_us + 200_000  # 200ms in the future
        start = time.monotonic()
        clock.fast_forward(target)
        elapsed = time.monotonic() - start
        assert elapsed >= 0.15
        assert elapsed < 0.5
        assert clock.now() == target


class TestModeProperty:
    def test_mode_property(self):
        clock = Clock(mode=ClockMode.FAST_SIMULATION)
        assert clock.mode == ClockMode.FAST_SIMULATION

    def test_mode_property_real_time(self):
        clock = Clock(mode=ClockMode.REAL_TIME)
        assert clock.mode == ClockMode.REAL_TIME
