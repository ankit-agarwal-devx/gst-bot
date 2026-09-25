"""Clocks for the fake. VirtualClock makes a 40 s stall take 0 s of real time."""
import threading
import time


class RealClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def time(self) -> float:
        return time.time()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


class VirtualClock:
    """Time only moves when someone sleeps or advances it.

    Shared by all threads: two threads that each sleep 3 s move the clock 6 s.
    That is coarse, but it never blocks and it is deterministic.
    """

    def __init__(self, start_wall: float = 1_790_000_000.0) -> None:
        self._lock = threading.Lock()
        self._elapsed = 0.0
        self._start_wall = start_wall
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        with self._lock:
            return self._elapsed

    def time(self) -> float:
        with self._lock:
            return self._start_wall + self._elapsed

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("cannot move time backwards")
        with self._lock:
            self._elapsed += seconds

    def sleep(self, seconds: float) -> None:
        with self._lock:
            self.sleeps.append(seconds)
            if seconds > 0:
                self._elapsed += seconds
