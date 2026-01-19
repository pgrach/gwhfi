@echo off
echo Starting Data Worker...
start "Smart Water Worker" python ingestion/cloud_worker.py

echo Starting Main Controller...
python ingestion/main.py

pause
