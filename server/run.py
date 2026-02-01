#!/usr/bin/env python3
"""
Datalogger V2 - Consolidated Server Launcher
Run with: python run.py
"""
import sys
from pathlib import Path

# Add core to path
# Add core to path
CORE_PATH = Path(__file__).parent / "core"
API_PATH = Path(__file__).parent / "api"
ROOT_PATH = Path(__file__).parent.parent

if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

if str(CORE_PATH) not in sys.path:
    sys.path.insert(0, str(CORE_PATH))
if str(API_PATH) not in sys.path:
    sys.path.insert(0, str(API_PATH))

from api.main import app

if __name__ == "__main__":
    print("[Datalogger V2] Starting server...")
    app.run(host='0.0.0.0', port=6969, debug=True)
