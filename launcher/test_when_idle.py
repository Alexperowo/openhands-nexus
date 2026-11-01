"""when-idle waits for every conversation to stop before it runs the command."""
import importlib.machinery
import importlib.util
import unittest
from pathlib import Path

loader = importlib.machinery.SourceFileLoader("when_idle", str(Path(__file__).with_name("when-idle")))
spec = importlib.util.spec_from_loader("when_idle", loader)
when_idle = importlib.util.module_from_spec(spec)
loader.exec_module(when_idle)


class Clock:
    def __init__(self):
        self.now = 0.0

    def sleep(self, seconds):
        self.now += seconds

    def __call__(self):
        return self.now


class WaitIdleTests(unittest.TestCase):
    def run_with(self, counts):
        clock, seen = Clock(), iter(counts)
        result = when_idle.wait_idle(count=lambda: next(seen, 0), sleep=clock.sleep, clock=clock)
        return result, clock.now

    def test_runs_after_the_reply(self):
        result, waited = self.run_with([1, 1, 1, 0, 0])
        self.assertTrue(result)
        self.assertEqual(waited, 4 * when_idle.POLL)

    def test_one_idle_moment_is_not_enough(self):
        result, waited = self.run_with([0, 1, 0, 0])
        self.assertTrue(result)
        self.assertEqual(waited, 3 * when_idle.POLL)

    def test_gives_up_when_never_idle(self):
        clock = Clock()
        self.assertFalse(when_idle.wait_idle(count=lambda: 1, sleep=clock.sleep, clock=clock))
        self.assertGreaterEqual(clock.now, when_idle.LIMIT)

    def test_no_command(self):
        with self.assertRaises(SystemExit):
            when_idle.main([])


if __name__ == "__main__":
    unittest.main()
