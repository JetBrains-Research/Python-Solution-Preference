#!/usr/bin/env python3
import sys
import os
import uvicorn

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.main import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
