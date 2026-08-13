from pathlib import Path
import unittest


class StartScriptSupervisionTests(unittest.TestCase):
    def test_required_process_exit_is_always_reported_as_failure(self):
        script = (Path(__file__).resolve().parents[1] / "start.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn('wait -n "$worker_pid" "$controller_pid"', script)
        self.assertIn('if [ "$exit_code" -eq 0 ]; then', script)
        self.assertIn("exit_code=1", script)
        self.assertIn('kill -TERM "$worker_pid" "$controller_pid"', script)


if __name__ == "__main__":
    unittest.main()
