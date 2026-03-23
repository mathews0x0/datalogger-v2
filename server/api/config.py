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
SECTOR_COUNT = 7




# Legacy global directories (keeping definitions for migration/reference but not creating them)


def get_user_dir(user_id):
    """Get the base data directory for a specific user"""
    u_dir = DATA_DIR / "users" / str(user_id)
    u_dir.mkdir(parents=True, exist_ok=True)
    return u_dir

def get_user_sessions_dir(user_id):
    """Get the sessions directory for a specific user"""
    s_dir = get_user_dir(user_id) / "sessions"
    s_dir.mkdir(parents=True, exist_ok=True)
    return s_dir

def get_user_learning_dir(user_id):
    """Get the learning directory for a specific user"""
    l_dir = get_user_dir(user_id) / "learning"
    l_dir.mkdir(parents=True, exist_ok=True)
    return l_dir

def get_user_tracks_dir(user_id):
    """Get the tracks directory for a specific user"""
    t_dir = get_user_dir(user_id) / "tracks"
    t_dir.mkdir(parents=True, exist_ok=True)
    return t_dir
