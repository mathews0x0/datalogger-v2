#!/usr/bin/env python3
"""
Datalogger V2 - Consolidated Server Launcher
Run with: python run.py
"""
import sys
from pathlib import Path

# Add server directories to path
API_PATH = Path(__file__).parent / "api"
ROOT_PATH = Path(__file__).parent

if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

if str(API_PATH) not in sys.path:
    sys.path.insert(0, str(API_PATH))

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from api.main import app
from api.models import db

if __name__ == "__main__":
    with app.app_context():
        try:
            db.create_all()
        except Exception as e:
            print(f"[RaceSense] db.create_all() skipped: {e}")

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
