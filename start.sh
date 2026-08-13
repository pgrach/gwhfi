#!/bin/bash
set -uo pipefail

echo "Starting Data Worker..."
python ingestion/cloud_worker.py &
worker_pid=$!

echo "Starting Main Controller..."
python ingestion/main.py &
controller_pid=$!

shutdown() {
    trap - TERM INT
    kill -TERM "$worker_pid" "$controller_pid" 2>/dev/null || true
    wait "$worker_pid" "$controller_pid" 2>/dev/null || true
}

trap shutdown TERM INT EXIT

# Either process is required for a healthy service. Exit when one dies so the
# platform restarts the pair instead of silently running control without data
# (or data without control).
wait -n "$worker_pid" "$controller_pid"
exit_code=$?
if [ "$exit_code" -eq 0 ]; then
    # A clean exit is still unhealthy here: both processes are required to run
    # continuously, so force the platform to restart the service pair.
    exit_code=1
fi
echo "A required process exited (code $exit_code); stopping the service pair."
exit "$exit_code"
