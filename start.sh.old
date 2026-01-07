#!/bin/bash

# Start the Data Worker in the background
echo "Starting Data Worker..."
python ingestion/cloud_worker.py &

# Start the Main Controller in the foreground
echo "Starting Main Controller..."
python ingestion/main.py
