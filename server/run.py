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
    import os
    is_dev = os.environ.get('FLASK_ENV', 'development') == 'development'
    port = int(os.environ.get('PORT', 6969))
    print(f"[RaceSense] Starting server... (env={'development' if is_dev else 'production'}, port={port})")
    if is_dev:
        app.run(host='0.0.0.0', port=port, debug=True)
    else:
        # In production, use gunicorn instead of Flask dev server
        # This block is a fallback; use: gunicorn -w 4 -b 0.0.0.0:6969 api.main:app
        print("[RaceSense] WARNING: Running Flask dev server in production. Use gunicorn instead.")
        app.run(host='0.0.0.0', port=port, debug=False)
