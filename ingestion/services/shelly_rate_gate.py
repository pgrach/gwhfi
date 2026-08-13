"""Process-shared rate gate for Shelly Cloud requests.

Railway runs the telemetry collector and heater controller as separate Python
processes.  A thread lock in either process cannot protect the Shelly account
from their combined request rate, so this gate stores the last reserved request
start in a tiny SQLite database under the operating-system temporary directory.
SQLite's ``BEGIN IMMEDIATE`` supplies the cross-process mutex on both Linux and
Windows without another runtime dependency.
"""

import os
import sqlite3
import tempfile
import time
from pathlib import Path


DEFAULT_MIN_REQUEST_INTERVAL_SECONDS = 1.05
WAIT_EPSILON_SECONDS = 0.000001
DEFAULT_GATE_PATH = os.getenv("SHELLY_RATE_GATE_PATH") or str(
    Path(tempfile.gettempdir()) / "gwhfi-shelly-cloud-rate-gate.sqlite3"
)


class ShellyRateGateError(RuntimeError):
    """Raised when the shared rate-gate state cannot be accessed safely."""


class SharedShellyRequestGate:
    """Reserve Shelly Cloud request starts across processes.

    Each instance may live in a different process.  Instances coordinate when
    they use the same ``path`` and ``gate_name``.  Waiting happens outside the
    SQLite write transaction, then the contender re-checks the timestamp before
    reserving its turn.
    """

    def __init__(
        self,
        path=DEFAULT_GATE_PATH,
        *,
        gate_name="shelly-cloud-account",
        min_interval_seconds=DEFAULT_MIN_REQUEST_INTERVAL_SECONDS,
        clock=None,
        sleeper=None,
        sqlite_timeout_seconds=10.0,
    ):
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must not be negative")

        self.path = str(path)
        self.gate_name = gate_name
        self.min_interval_seconds = float(min_interval_seconds)
        self._clock = clock or time.monotonic
        self._sleeper = sleeper or time.sleep
        self.sqlite_timeout_seconds = float(sqlite_timeout_seconds)

        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        return sqlite3.connect(
            self.path,
            timeout=self.sqlite_timeout_seconds,
            isolation_level=None,
        )

    def _initialize(self):
        try:
            connection = self._connect()
            try:
                connection.execute(
                    """
                    create table if not exists shelly_request_gate (
                        gate_name text primary key,
                        last_started_at real not null
                    )
                    """
                )
            finally:
                connection.close()
        except sqlite3.Error as exc:
            raise ShellyRateGateError(
                f"Unable to initialize shared Shelly request gate: {exc}"
            ) from exc

    def wait_for_turn(self):
        """Block until this caller atomically reserves the next request start."""
        while True:
            connection = None
            try:
                connection = self._connect()
                connection.execute("begin immediate")
                row = connection.execute(
                    "select last_started_at from shelly_request_gate where gate_name = ?",
                    (self.gate_name,),
                ).fetchone()

                now = self._clock()
                wait_seconds = 0.0
                if row is not None:
                    elapsed = now - float(row[0])
                    # A monotonic clock can only move backwards when this
                    # temporary database survived an operating-system reboot.
                    # Treat that record as stale instead of sleeping for the
                    # previous boot's uptime.
                    if elapsed >= 0:
                        wait_seconds = self.min_interval_seconds - elapsed

                if wait_seconds > WAIT_EPSILON_SECONDS:
                    connection.rollback()
                else:
                    connection.execute(
                        """
                        insert into shelly_request_gate (gate_name, last_started_at)
                        values (?, ?)
                        on conflict (gate_name) do update
                        set last_started_at = excluded.last_started_at
                        """,
                        (self.gate_name, now),
                    )
                    connection.commit()
                    return
            except sqlite3.Error as exc:
                if connection is not None:
                    try:
                        connection.rollback()
                    except sqlite3.Error:
                        pass
                raise ShellyRateGateError(
                    f"Unable to reserve shared Shelly request slot: {exc}"
                ) from exc
            finally:
                if connection is not None:
                    connection.close()

            self._sleeper(wait_seconds)
