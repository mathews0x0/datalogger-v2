import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"

# Sub-directories
LEARNING_DIR = DATA_DIR / "learning"
TRACKS_DIR = DATA_DIR / "tracks"
SESSIONS_DIR = DATA_DIR / "sessions"
METADATA_DIR = DATA_DIR / "metadata"
REGISTRY_FILE = METADATA_DIR / "registry.json"
SECTOR_COUNT = 3




# Ensure directories exist
for d in [LEARNING_DIR, TRACKS_DIR, SESSIONS_DIR, METADATA_DIR]:
    d.mkdir(parents=True, exist_ok=True)
