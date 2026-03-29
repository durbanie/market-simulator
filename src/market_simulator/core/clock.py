"""Clock for providing timestamps in different simulation modes."""

import time
from enum import StrEnum


class ClockMode(StrEnum):
    """Clock operating mode."""
    REAL_TIME = "REAL_TIME"
    FAST_SIMULATION = "FAST_SIMULATION"
    REAL_TIME_SIMULATION = "REAL_TIME_SIMULATION"


class Clock:
    """Provides timestamps for the simulation.

    Supports three modes:
    - REAL_TIME: passes through wall time with an optional offset.
    - FAST_SIMULATION: uses modeled time advanced explicitly by the caller.
    - REAL_TIME_SIMULATION: uses modeled time, but advance/fast_forward
      sleep until the target time actually arrives (skips sleep if behind).
    """

    def __init__(
        self,
        mode: ClockMode = ClockMode.FAST_SIMULATION,
        offset_us: int = 0,
    ) -> None:
        """Initialize the clock.

        Args:
            mode: The clock operating mode.
            offset_us: In REAL_TIME mode, added to wall time. In
                FAST_SIMULATION and REAL_TIME_SIMULATION modes, used as the
                initial modeled time.
        """
        self._mode = mode
        self._offset_us = offset_us
        self._modeled_time_us = offset_us

    @property
    def mode(self) -> ClockMode:
        """Return the current clock mode."""
        return self._mode

    def _wall_time_us(self) -> int:
        """Return wall time in microseconds, adjusted by offset."""
        return int(time.time() * 1_000_000) + self._offset_us

    def now(self) -> int:
        """Return the current time in integer microseconds from Unix epoch.

        In REAL_TIME mode, returns wall time plus offset.
        In FAST_SIMULATION and REAL_TIME_SIMULATION modes, returns the
        modeled time.
        """
        if self._mode == ClockMode.REAL_TIME:
            return self._wall_time_us()
        return self._modeled_time_us

    def advance(self, delta_us: int) -> None:
        """Advance modeled time by a delta.

        In REAL_TIME_SIMULATION mode, sleeps for the delta duration.

        Args:
            delta_us: Microseconds to advance. Must be non-negative.

        Raises:
            ValueError: If delta_us is negative.
            RuntimeError: If called in REAL_TIME mode.
        """
        if self._mode == ClockMode.REAL_TIME:
            raise RuntimeError("Cannot advance time in REAL_TIME mode.")
        if delta_us < 0:
            raise ValueError("delta_us must be non-negative.")
        self._modeled_time_us += delta_us
        if self._mode == ClockMode.REAL_TIME_SIMULATION and delta_us > 0:
            time.sleep(delta_us / 1_000_000)

    def fast_forward(self, timestamp_us: int) -> None:
        """Set modeled time to the given timestamp.

        In REAL_TIME_SIMULATION mode, sleeps until the target wall time
        if the target is in the future. Skips sleep if the target is in
        the past (allows catch-up).

        Args:
            timestamp_us: Target time in microseconds.

        Raises:
            ValueError: If timestamp_us is before the current modeled time.
            RuntimeError: If called in REAL_TIME mode.
        """
        if self._mode == ClockMode.REAL_TIME:
            raise RuntimeError("Cannot fast_forward in REAL_TIME mode.")
        if timestamp_us < self._modeled_time_us:
            raise ValueError(
                f"Cannot fast_forward to {timestamp_us}, "
                f"which is before current time {self._modeled_time_us}."
            )

        self._modeled_time_us = timestamp_us

        if self._mode == ClockMode.REAL_TIME_SIMULATION:
            wait_us = timestamp_us - self._wall_time_us()
            if wait_us > 0:
                time.sleep(wait_us / 1_000_000)
