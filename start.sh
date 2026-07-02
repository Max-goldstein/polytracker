#!/bin/bash
cd "$(dirname "$0")"
echo "Starting PolyTracker on http://localhost:8765"
python3 -m uvicorn app:app --host 0.0.0.0 --port 8765 --reload
