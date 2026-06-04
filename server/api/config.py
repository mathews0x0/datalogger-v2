import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
APP_VERSION_FILE = PROJECT_ROOT / "VERSION"

# Sub-directories
LEARNING_DIR = DATA_DIR / "learning"
TRACKS_DIR = DATA_DIR / "tracks"
GLOBAL_TRACKS_DIR = TRACKS_DIR
SESSIONS_DIR = DATA_DIR / "sessions"
METADATA_DIR = DATA_DIR / "metadata"
REGISTRY_FILE = METADATA_DIR / "registry.json"
SECTOR_COUNT = 7
GLOBAL_TRACK_ID_MIN = 1_000_000
DEFAULT_SECTOR_COUNT_SETTING_KEY = "default_sector_count"
DEFAULT_SECTOR_COUNT_ENV_KEY = "RACESENSE_DEFAULT_SECTOR_COUNT"




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

def get_global_tracks_dir():
    """Get the shared global tracks directory."""
    GLOBAL_TRACKS_DIR.mkdir(parents=True, exist_ok=True)
    return GLOBAL_TRACKS_DIR

def get_global_track_dir(folder_name):
    """Get a specific shared global track directory."""
    t_dir = get_global_tracks_dir() / folder_name
    t_dir.mkdir(parents=True, exist_ok=True)
    return t_dir


def get_default_sector_count():
    try:
        env_value = os.environ.get(DEFAULT_SECTOR_COUNT_ENV_KEY)
        if env_value:
            value = int(env_value)
            if value > 0:
                return value
        from flask import has_app_context
        if not has_app_context():
            return SECTOR_COUNT
        from api.models import AppSetting
        setting = AppSetting.query.filter_by(key=DEFAULT_SECTOR_COUNT_SETTING_KEY).first()
        if not setting:
            return SECTOR_COUNT
        value = int(setting.value)
        if value <= 0:
            return SECTOR_COUNT
        return value
    except Exception:
        return SECTOR_COUNT


def get_app_version():
    try:
        if APP_VERSION_FILE.exists():
            value = APP_VERSION_FILE.read_text(encoding="utf-8").strip()
            if value:
                return value
    except Exception:
        pass
    return "0.0.0"
