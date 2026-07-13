#!/usr/bin/env bash
# Install dependencies and launch the FastAPI app
python3 -m pip install -r requirements.txt >/dev/null 2>&1
uvicorn main:app --host 0.0.0.0 --port 8000
