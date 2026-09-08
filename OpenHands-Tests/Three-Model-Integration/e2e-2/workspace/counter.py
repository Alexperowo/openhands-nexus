import threading
import time

class ThreadSafeCounter:
    def __init__(self):
        self._val = 0
        self._lock = threading.Lock()

    def increment(self):
        # Flawed retry: only increment locked, decrement unlocked
        with self._lock:
            curr = self._val
            time.sleep(0.00001)
            self._val = curr + 1

    def decrement(self):
        curr = self._val
        time.sleep(0.00001)
        self._val = curr - 1

    def get_value(self):
        return self._val
