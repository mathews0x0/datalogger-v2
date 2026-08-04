import os
import subprocess
import json
import sys
import re

import api.config as config
from api.models import db, TrackMeta, SessionMeta, GlobalTrack, UnmatchedTrackReport

MIN_ESP_VERSION = config.get_app_version()

def get_local_firmware_version():
    """Return the single RaceSense build shared by server and firmware."""
    return config.get_app_version()

def is_compatible(esp_version):
    """Check whether a device is on this or a newer Mark release."""
    if not esp_version: return False
    try:
        device_match = re.fullmatch(r"(?:Mark\s+)?(\d+)", str(esp_version).strip(), re.IGNORECASE)
        minimum_match = re.fullmatch(r"Mark\s+(\d+)", MIN_ESP_VERSION, re.IGNORECASE)
        if not device_match or not minimum_match:
            return False
        return int(device_match.group(1)) >= int(minimum_match.group(1))
    except (TypeError, ValueError, AttributeError):
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
    if track:
        return track.folder_name
    global_track = GlobalTrack.query.filter_by(track_id=track_id).first()
    return global_track.folder_name if global_track else None

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

def is_primary_session_json(filename):
    """Return True only for canonical session JSON files, not sidecar artifacts."""
    if not filename or not filename.endswith('.json'):
        return False
    return not (
        filename.endswith('_telemetry.json')
        or filename.endswith('_playback.json')
    )

def register_new_sessions(user_id):
    """Scan user-specific sessions directory and register any new sessions"""
    sessions_dir = config.get_user_sessions_dir(user_id)
    if not sessions_dir.exists():
        return
    
    new_found = False
    for filename in os.listdir(sessions_dir):
        if is_primary_session_json(filename):
            session_id = filename.replace('.json', '')
            try:
                with open(sessions_dir / filename, 'r') as f:
                    data = json.load(f)
                    # print(f"  Checking {filename} (tracks: {data.get('track', {}).get('track_id')})")
                    
                    # 1. Ensure track is registered for THIS user
                    track_id = data.get('track', {}).get('track_id')
                    track_scope = data.get('track', {}).get('track_scope') or 'user_fallback'
                    if track_id:
                        if track_scope == 'user_fallback':
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
                            else:
                                # Sync: ensure session JSON uses the DB's authoritative track name
                                json_track_name = data.get('track', {}).get('track_name')
                                if json_track_name and json_track_name != track_meta.track_name:
                                    print(f"    Syncing track name for {track_id}: '{json_track_name}' -> '{track_meta.track_name}'")
                                    data['track']['track_name'] = track_meta.track_name
                                    try:
                                        with open(sessions_dir / filename, 'w') as fw:
                                            json.dump(data, fw, indent=2)
                                    except Exception as write_err:
                                        print(f"    Failed to sync track name to session JSON: {write_err}")

                    # 2. Register or refresh session metadata for this user.
                    # Re-analysis must update timing and lap summaries without
                    # resetting the rider's public/private choice.
                    existing = SessionMeta.query.filter_by(session_id=session_id, user_id=user_id).first()
                    session_values = {
                        "track_id": track_id,
                        "session_name": data.get('meta', {}).get('session_name'),
                        "start_time": data.get('meta', {}).get('start_time'),
                        "duration_sec": data.get('meta', {}).get('duration_sec'),
                        "total_laps": data.get('summary', {}).get('total_laps') or data.get('aggregates', {}).get('total_laps') or len(data.get('laps', [])),
                        "best_lap_time": data.get('aggregates', {}).get('best_lap_time') or data.get('summary', {}).get('best_lap_time'),
                    }
                    if not existing:
                        print(f"    Registering new session {session_id} for user {user_id}")
                        sm = SessionMeta(
                            session_id=session_id,
                            user_id=user_id,
                            **session_values,
                            is_public=True,
                        )
                        db.session.add(sm)
                        new_found = True
                    else:
                        for key, value in session_values.items():
                            setattr(existing, key, value)
                        new_found = True

                        if track_id and track_scope == 'user_fallback':
                            existing_report = UnmatchedTrackReport.query.filter_by(
                                user_id=user_id,
                                fallback_track_id=track_id,
                                status='open'
                            ).first()
                            if not existing_report:
                                report_payload = {
                                    "track": data.get('track', {}),
                                    "references": data.get('references', {}),
                                    "source_file": data.get('meta', {}).get('source_file'),
                                }
                                db.session.add(UnmatchedTrackReport(
                                    user_id=user_id,
                                    session_id=session_id,
                                    fallback_track_id=track_id,
                                    fallback_track_name=data.get('track', {}).get('track_name') or f"Track {track_id}",
                                    status='open',
                                    payload=json.dumps(report_payload)
                                ))
            except Exception as e:
                print(f"Failed to auto-register session {filename}: {e}")
    
    if new_found:
        db.session.commit()
