import threading
import time

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold, open_seconds):
        self.failure_threshold = failure_threshold
        self.open_seconds = open_seconds
        self._lock = threading.Lock()
        self._state = CLOSED
        self._failures = 0
        self._opened_at = None

    @property
    def state(self):
        with self._lock:
            return self._state

    @property
    def failures(self):
        with self._lock:
            return self._failures

    def allow(self):
        with self._lock:
            if self._state == CLOSED:
                return True
            if self._state == OPEN:
                if time.monotonic() - self._opened_at < self.open_seconds:
                    return False
                self._state = HALF_OPEN
                return True
            return False

    def record_failure(self):
        with self._lock:
            if self._state == HALF_OPEN:
                self._state = OPEN
                self._opened_at = time.monotonic()
            elif self._state == CLOSED:
                self._failures += 1
                if self._failures >= self.failure_threshold:
                    self._state = OPEN
                    self._opened_at = time.monotonic()

    def record_success(self):
        with self._lock:
            self._state = CLOSED
            self._failures = 0
            self._opened_at = None

    def reset(self):
        with self._lock:
            self._state = CLOSED
            self._failures = 0
            self._opened_at = None