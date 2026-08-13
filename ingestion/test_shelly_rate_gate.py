import multiprocessing
import tempfile
import time
import unittest
from pathlib import Path

from services.shelly_rate_gate import SharedShellyRequestGate


def reserve_shared_gate(path, interval, ready, start, output):
    gate = SharedShellyRequestGate(path, min_interval_seconds=interval)
    ready.put(True)
    start.wait()
    gate.wait_for_turn()
    output.put(time.monotonic())


class SharedShellyRequestGateTests(unittest.TestCase):
    def test_independent_instances_share_one_reservation_clock(self):
        now = [100.0]
        sleeps = []

        def clock():
            return now[0]

        def sleeper(seconds):
            sleeps.append(seconds)
            now[0] += seconds

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gate.sqlite3"
            first = SharedShellyRequestGate(path, clock=clock, sleeper=sleeper)
            second = SharedShellyRequestGate(path, clock=clock, sleeper=sleeper)

            first.wait_for_turn()
            second.wait_for_turn()

        self.assertEqual(len(sleeps), 1)
        self.assertAlmostEqual(sleeps[0], first.min_interval_seconds)

    def test_separate_processes_cannot_reserve_too_close_together(self):
        interval = 0.15
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "process-gate.sqlite3")
            context = multiprocessing.get_context("spawn")
            ready = context.Queue()
            output = context.Queue()
            start = context.Event()
            processes = [
                context.Process(
                    target=reserve_shared_gate,
                    args=(path, interval, ready, start, output),
                )
                for _ in range(2)
            ]
            for process in processes:
                process.start()
            for _ in processes:
                self.assertTrue(ready.get(timeout=10))
            start.set()
            timestamps = sorted(output.get(timeout=10) for _ in processes)
            for process in processes:
                process.join(timeout=10)
                self.assertEqual(process.exitcode, 0)

        self.assertGreaterEqual(timestamps[1] - timestamps[0], interval - 0.02)


if __name__ == "__main__":
    unittest.main()
