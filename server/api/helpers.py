import os
import subprocess
import json
import sys

import api.config as config
from api.models import db, TrackMeta, SessionMeta

MIN_ESP_VERSION = "0.0.0"
FIRMWARE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../firmware'))

def get_local_firmware_version():
    try:
        p = os.path.join(FIRMWARE_DIR, 'lib/miniserver.py')
        with open(p, 'r') as f:
            for line in f:
                if 'VERSION =' in line:
                    return line.split('=')[1].strip().replace('"', '').replace("'", "")
    except:
        pass
    return "Unknown"

def is_compatible(esp_version):
    """Check if ESP firmware meets minimum requirements"""
    if not esp_version: return False
    try:
        # Simple version comparison (e.g. 1.0.2)
        v_parts = [int(p) for p in esp_version.split('.')]
        min_parts = [int(p) for p in MIN_ESP_VERSION.split('.')]
        return v_parts >= min_parts
    except:
        return False

def load_registry(user_id=None):
    """Load tracks for a user from DB"""
    query = TrackMeta.query
    if user_id:
        query = query.filter_by(user_id=user_id)
    tracks = query.all()
    
    return {
        "tracks": [
            {
                "track_id": t.track_id,
                "track_name": t.track_name,
                "folder_name": t.folder_name
            } for t in tracks
        ]
    }

def get_track_folder(track_id, user_id=None):
    """Get folder name for track ID from DB"""
    query = TrackMeta.query.filter_by(track_id=track_id)
    if user_id:
        query = query.filter_by(user_id=user_id)
    track = query.first()
    return track.folder_name if track else None

def robust_get_json(url, timeout=3.0):
    """
    Attempt to get JSON from a URL using curl (subprocess) to avoid python-requests issues.
    """
    # Fallback to subprocess curl
    try:
        # -s = silent, --connect-timeout = seconds
        # Use a slightly longer timeout for curl than the requests
        tout = max(int(timeout), 2)
        cmd = ['curl', '-s', '--connect-timeout', str(tout), url]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+2)
        
        if result.returncode == 0 and result.stdout.strip():
            try:
                return json.loads(result.stdout)
            except:
                print(f"[Scanner] WARN: Invalid JSON from {url}")
                pass
        else:
            if result.returncode != 0:
                # Use print for debug in console
                print(f"[Scanner] Curl failed for {url}: RC={result.returncode}. Stderr: {result.stderr}")
                pass
    except Exception as e:
        print(f"[Scanner] Exception checking {url}: {e}")
        pass
        
    return None

def register_new_sessions(user_id):
    """Scan user-specific sessions directory and register any new sessions"""
    sessions_dir = config.get_user_sessions_dir(user_id)
    if not sessions_dir.exists():
        return
    
    new_found = False
    for filename in os.listdir(sessions_dir):
        if filename.endswith('.json') and not filename.endswith('_telemetry.json'):
            session_id = filename.replace('.json', '')
            try:
                with open(sessions_dir / filename, 'r') as f:
                    data = json.load(f)
                    # print(f"  Checking {filename} (tracks: {data.get('track', {}).get('track_id')})")
                    
                    # 1. Ensure track is registered for THIS user
                    track_id = data.get('track', {}).get('track_id')
                    if track_id:
                        track_meta = TrackMeta.query.filter_by(track_id=track_id, user_id=user_id).first()
                        if not track_meta:
                            print(f"    Registering missing track {track_id} for user {user_id}")
                            track_meta = TrackMeta(
                                track_id=track_id,
                                user_id=user_id,
                                track_name=data.get('track', {}).get('track_name') or f"Track {track_id}",
                                folder_name=data.get('track', {}).get('folder_name') or f"track_{track_id}"
                            )
                            db.session.add(track_meta)
                            db.session.commit() # Commit track before session

                    # 2. Register session if missing for this user
                    existing = SessionMeta.query.filter_by(session_id=session_id, user_id=user_id).first()
                    if not existing:
                        print(f"    Registering new session {session_id} for user {user_id}")
                        sm = SessionMeta(
                            session_id=session_id,
                            user_id=user_id,
                            track_id=track_id,
                            session_name=data.get('meta', {}).get('session_name'),
                            start_time=data.get('meta', {}).get('start_time'),
                            duration_sec=data.get('meta', {}).get('duration_sec'),
                            total_laps=data.get('summary', {}).get('total_laps') or data.get('aggregates', {}).get('total_laps') or len(data.get('laps', [])),
                            best_lap_time=data.get('aggregates', {}).get('best_lap_time') or data.get('summary', {}).get('best_lap_time')
                        )
                        db.session.add(sm)
                        new_found = True
            except Exception as e:
                print(f"Failed to auto-register session {filename}: {e}")
    
    if new_found:
        db.session.commit()
