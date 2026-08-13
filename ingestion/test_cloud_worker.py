import importlib
import os
import sys
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    requests_module = types.ModuleType("requests")
    requests_module.post = lambda *args, **kwargs: None
    requests_module.patch = lambda *args, **kwargs: None
    sys.modules["requests"] = requests_module

try:
    import dotenv  # noqa: F401
except ModuleNotFoundError:
    dotenv_module = types.ModuleType("dotenv")
    dotenv_module.load_dotenv = lambda: None
    sys.modules["dotenv"] = dotenv_module


ENV = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_KEY": "secret",
    "SHELLY_CLOUD_AUTH_KEY": "auth",
    "SHELLY_CLOUD_SERVER": "https://shelly.example",
    "SHELLY_METER_DEVICE_ID": "meter-1",
    "TELEMETRY_COLLECTOR_ID": "test-collector",
    "TELEMETRY_SITE_ID": "flat-1",
}


class Response:
    def __init__(self, data=None, status_code=200):
        self._data = data
        self.status_code = status_code
        self.text = str(data)

    def raise_for_status(self):
        if self.status_code >= 400:
            error = RuntimeError(f"HTTP {self.status_code}")
            error.response = self
            raise error

    def json(self):
        return self._data


class CloudWorkerTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(os.environ, ENV, clear=False):
            if "ingestion.cloud_worker" in sys.modules:
                self.worker = sys.modules["ingestion.cloud_worker"]
            else:
                self.worker = importlib.import_module("ingestion.cloud_worker")
        self.worker.SUPABASE_URL = ENV["SUPABASE_URL"]
        self.worker.SUPABASE_KEY = ENV["SUPABASE_KEY"]
        self.worker.SHELLY_AUTH_KEY = ENV["SHELLY_CLOUD_AUTH_KEY"]
        self.worker.SHELLY_SERVER = ENV["SHELLY_CLOUD_SERVER"]
        self.worker.SHELLY_DEVICE_ID = ENV["SHELLY_METER_DEVICE_ID"]
        self.worker.COLLECTOR_ID = ENV["TELEMETRY_COLLECTOR_ID"]
        self.worker.SITE_ID = ENV["TELEMETRY_SITE_ID"]
        self.worker.last_readings.clear()

    def test_builds_fixed_rate_rows_with_shared_poll_and_aware_timestamp(self):
        observed = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
        rows = self.worker.build_rows(
            {"emeters": [
                {"power": 0, "voltage": 230, "total": 100},
                {"power": 3040, "voltage": 231, "total": 200},
            ]},
            "11111111-1111-1111-1111-111111111111",
            observed,
            observed,
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual({row["poll_id"] for row in rows}, {"11111111-1111-1111-1111-111111111111"})
        self.assertEqual({row["created_at"] for row in rows}, {"2026-08-13T12:00:00Z"})
        self.assertEqual(rows[0]["power_w"], 0.0)
        self.assertEqual(rows[0]["site_id"], "flat-1")
        self.assertEqual(rows[0]["sample_reason"], "periodic")
        self.assertEqual(rows[0]["quality_flags"], [])

    def test_poll_id_is_deterministic_for_the_same_scheduled_minute(self):
        first = datetime(2026, 8, 13, 12, 0, 1, tzinfo=timezone.utc)
        retry = datetime(2026, 8, 13, 12, 0, 59, tzinfo=timezone.utc)
        next_minute = datetime(2026, 8, 13, 12, 1, tzinfo=timezone.utc)

        self.assertEqual(
            self.worker.poll_id_for_schedule(first),
            self.worker.poll_id_for_schedule(retry),
        )
        self.assertNotEqual(
            self.worker.poll_id_for_schedule(first),
            self.worker.poll_id_for_schedule(next_minute),
        )

    def test_missing_required_channel_is_not_recorded_as_success(self):
        observed = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
        rows = self.worker.build_rows(
            {"emeters": [{"power": 0, "voltage": 230, "total": 100}]},
            "11111111-1111-1111-1111-111111111111",
            observed,
            observed,
        )

        self.assertEqual(rows, [])

    def test_missing_or_invalid_values_are_null_and_flagged_not_zero(self):
        row = self.worker.build_rows(
            {"emeters": [
                {"power": "bad", "total": -1},
                {"power": 0, "voltage": 230, "total": 10},
            ]},
            "poll-1",
            datetime.now(timezone.utc),
            datetime.now(timezone.utc),
        )[0]

        self.assertIsNone(row["power_w"])
        self.assertIsNone(row["voltage"])
        self.assertIsNone(row["energy_total_wh"])
        self.assertCountEqual(
            row["quality_flags"],
            ["power_invalid", "voltage_missing", "energy_total_out_of_range"],
        )

        poll = self.worker.build_poll_row(
            "55555555-5555-5555-5555-555555555555",
            datetime.now(timezone.utc),
            {
                "request_started_at": datetime.now(timezone.utc),
                "received_at": datetime.now(timezone.utc),
                "latency_ms": 5,
                "http_status": 200,
            },
            "success",
            raw_payload={"emeters": [{"power": "bad"}]},
        )
        self.assertIsNotNone(poll["raw_payload"])
        self.assertEqual(len(poll["payload_hash"]), 64)

    def test_retries_same_idempotent_payload_and_commits_state_after_success(self):
        shelly = Response({
            "isok": True,
            "data": {"device_status": {"emeters": [
                {"power": 0, "voltage": 230, "total": 10},
                {"power": 0, "voltage": 231, "total": 20},
            ]}},
        })
        failed = Response(status_code=503)
        accepted = Response(status_code=201)

        with (
            patch.object(
                self.worker.requests,
                "post",
                side_effect=[shelly, failed, accepted],
            ) as post,
            patch.object(self.worker.time, "sleep"),
        ):
            result = self.worker.process_reading(
                poll_id="11111111-1111-1111-1111-111111111111"
            )

        self.assertTrue(result)
        first_write = post.call_args_list[1].kwargs["json"]
        second_write = post.call_args_list[2].kwargs["json"]
        self.assertEqual(first_write, second_write)
        self.assertEqual(first_write["p_poll"]["outcome"], "success")
        self.assertIsNone(first_write["p_poll"]["raw_payload"])
        self.assertEqual(len(first_write["p_poll"]["payload_hash"]), 64)
        self.assertEqual(
            first_write["p_readings"][0]["poll_id"],
            "11111111-1111-1111-1111-111111111111",
        )
        self.assertIn(("meter-1", 0), self.worker.last_readings)
        self.assertEqual(post.call_args_list[1].kwargs["timeout"], self.worker.SUPABASE_TIMEOUT_SECONDS)
        self.assertIn(
            "/rest/v1/rpc/ingest_telemetry_poll",
            post.call_args_list[1].args[0],
        )

    def test_failed_atomic_write_does_not_commit_state_or_leave_success_parent(self):
        shelly = Response({
            "isok": True,
            "data": {"device_status": {"emeters": [{"power": 0, "voltage": 230, "total": 10}]}},
        })
        with (
            patch.object(
                self.worker.requests,
                "post",
                side_effect=[
                    shelly,
                    Response(status_code=503),
                    Response(status_code=503),
                    Response(status_code=503),
                ],
            ) as post,
            patch.object(self.worker.time, "sleep"),
        ):
            result = self.worker.process_reading(
                poll_id="22222222-2222-2222-2222-222222222222"
            )

        self.assertFalse(result)
        self.assertEqual(self.worker.last_readings, {})
        self.assertEqual(post.call_count, 4)
        self.assertTrue(all(
            "/rest/v1/rpc/ingest_telemetry_poll" in call.args[0]
            for call in post.call_args_list[1:]
        ))

    def test_empty_channel_payload_is_a_failed_poll(self):
        shelly = Response({"isok": True, "data": {"device_status": {"emeters": []}}})
        with patch.object(
            self.worker.requests,
            "post",
            side_effect=[shelly, Response(status_code=201)],
        ) as post:
            result = self.worker.process_reading(
                poll_id="33333333-3333-3333-3333-333333333333"
            )

        self.assertFalse(result)
        self.assertEqual(post.call_count, 2)
        payload = post.call_args_list[1].kwargs["json"]
        self.assertEqual(payload["p_poll"]["outcome"], "source_error")
        self.assertEqual(payload["p_poll"]["error_code"], "no_emeter_channels")
        self.assertEqual(payload["p_readings"], [])
        self.assertIn("/rest/v1/rpc/ingest_telemetry_poll", post.call_args_list[1].args[0])

    def test_partial_channel_payload_records_missing_channel_lineage(self):
        shelly = Response({
            "isok": True,
            "data": {"device_status": {"emeters": [
                {"power": 0, "voltage": 230, "total": 10},
            ]}},
        })
        with patch.object(
            self.worker.requests,
            "post",
            side_effect=[shelly, Response(status_code=201)],
        ) as post:
            result = self.worker.process_reading(
                poll_id="77777777-7777-7777-7777-777777777777"
            )

        self.assertFalse(result)
        poll = post.call_args_list[1].kwargs["json"]["p_poll"]
        self.assertEqual(poll["error_code"], "missing_required_channels")
        self.assertIn("[1]", poll["error_message"])

    def test_source_failure_is_recorded_as_failed_poll_without_observations(self):
        rejected = Response({"isok": False}, status_code=200)
        with patch.object(
            self.worker.requests,
            "post",
            side_effect=[rejected, Response(status_code=201)],
        ) as post:
            result = self.worker.process_reading(
                poll_id="44444444-4444-4444-4444-444444444444"
            )

        self.assertFalse(result)
        self.assertEqual(post.call_count, 2)
        payload = post.call_args_list[1].kwargs["json"]
        poll = payload["p_poll"]
        self.assertEqual(poll["outcome"], "source_error")
        self.assertEqual(poll["error_code"], "shelly_api_rejected")
        self.assertEqual(payload["p_readings"], [])
        self.assertIn("/rest/v1/rpc/ingest_telemetry_poll", post.call_args_list[1].args[0])
        self.assertEqual(self.worker.last_readings, {})

    def test_transport_failure_does_not_manufacture_a_received_timestamp(self):
        accepted = Response(status_code=200)
        with (
            patch.object(
                self.worker.requests,
                "post",
                side_effect=[TimeoutError("network timeout"), accepted],
            ) as post,
            patch.object(self.worker.time, "sleep"),
        ):
            result = self.worker.process_reading(
                poll_id="66666666-6666-6666-6666-666666666666"
            )

        self.assertFalse(result)
        payload = post.call_args_list[1].kwargs["json"]
        self.assertIsNone(payload["p_poll"]["received_at"])
        self.assertEqual(payload["p_poll"]["outcome"], "source_error")
        self.assertEqual(payload["p_readings"], [])

    def test_main_fails_fast_when_required_configuration_is_missing(self):
        with (
            patch.object(self.worker, "configuration_valid", return_value=False),
            patch.object(self.worker, "run_forever") as run_forever,
        ):
            exit_code = self.worker.main()

        self.assertEqual(exit_code, 1)
        run_forever.assert_not_called()

    def test_empty_lineage_configuration_is_invalid(self):
        with patch.object(self.worker, "SITE_ID", "   "):
            self.assertFalse(self.worker.configuration_valid())
        with patch.object(self.worker, "COLLECTOR_ID", ""):
            self.assertFalse(self.worker.configuration_valid())


if __name__ == "__main__":
    unittest.main()
