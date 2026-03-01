import os
import sys

# Entry point legacy support: main.py proxies the app factory.
from api import create_app
import api.config as config

app = create_app()
OUTPUT_DIR = config.DATA_DIR

if __name__ == '__main__':
    # Development mode
    print("=" * 60)
    print("Datalogger Cloud API Server")
    print("=" * 60)
    print(f"Output directory: {OUTPUT_DIR}")
    print()
    print("Starting server on http://localhost:5001")
    print("=" * 60)
    
    import multiprocessing
    # Make sure multiprocessing plays nice
    multiprocessing.freeze_support()
    
    app.run(host='0.0.0.0', port=5001, debug=False)
