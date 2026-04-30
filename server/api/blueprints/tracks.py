from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
import json
import shutil

from api.models import db, User, TrackMeta, SessionMeta, GlobalTrack
import api.config as config
from api.auth_utils import get_current_user_id
from api.track_catalog import (
    get_user_track_stats_dir,
    load_json_file,
    load_track_json,
    load_track_layout,
    resolve_track,
    track_file_path,
)

tracks_bp = Blueprint('tracks', __name__)


def _user_track_summary(user_id, track_id):
    sessions_meta = SessionMeta.query.filter_by(user_id=user_id, track_id=track_id).all()
    best_lap_time = None
    for session in sessions_meta:
        if session.best_lap_time is not None:
            if best_lap_time is None or session.best_lap_time < best_lap_time:
                best_lap_time = session.best_lap_time
    return len(sessions_meta), best_lap_time


def user_tbl_file_path(user_id, resolved_track):
    if resolved_track["track_scope"] == "global":
        user_track_dir = get_user_track_stats_dir(user_id, resolved_track["track_id"], resolved_track["track_name"])
        return user_track_dir / "tbl.json"
    return track_file_path(resolved_track, "tbl.json")


def clear_user_track_tbl_if_no_sessions(user_id, track_id):
    sessions_count, _ = _user_track_summary(user_id, track_id)
    if sessions_count > 0:
        return False
    resolved = resolve_track(track_id, user_id=user_id)
    if not resolved:
        return False
    tbl_file = user_tbl_file_path(user_id, resolved)
    if tbl_file.exists():
        tbl_file.unlink()
        return True
    return False


@tracks_bp.route('/api/tracks')
@jwt_required()
def get_tracks():
    user_id = get_current_user_id()

    tracks = []
    matched_global_ids = {
        track_id for (track_id,) in db.session.query(SessionMeta.track_id)
        .filter(SessionMeta.user_id == user_id, SessionMeta.track_id.isnot(None))
        .distinct()
        .all()
        if track_id is not None
    }
    global_tracks = GlobalTrack.query.filter(GlobalTrack.track_id.in_(matched_global_ids)).order_by(GlobalTrack.track_name.asc()).all() if matched_global_ids else []
    for global_track in global_tracks:
        session_count, best_lap_time = _user_track_summary(user_id, global_track.track_id)
        tracks.append({
            "track_id": global_track.track_id,
            "track_name": global_track.track_name,
            "folder_name": global_track.folder_name,
            "sessions_count": session_count,
            "track_scope": "global",
            "track_source": "global_package",
            "has_canonical_layout": bool(global_track.has_canonical_layout),
            "package_version": global_track.package_version,
            "best_lap_time": best_lap_time,
        })

    fallback_tracks = TrackMeta.query.filter_by(user_id=user_id).order_by(TrackMeta.track_name.asc()).all()
    for track in fallback_tracks:
        session_count, best_lap_time = _user_track_summary(user_id, track.track_id)
        tracks.append({
            "track_id": track.track_id,
            "track_name": track.track_name,
            "folder_name": track.folder_name,
            "sessions_count": session_count,
            "track_scope": "user_fallback",
            "track_source": "session_generated",
            "has_canonical_layout": False,
            "package_version": None,
            "best_lap_time": best_lap_time,
        })

    tracks.sort(key=lambda item: (item["track_scope"] != "global", (item.get("track_name") or "").lower()))
    return jsonify({"tracks": tracks})


@tracks_bp.route('/api/tracks/<int:track_id>')
@jwt_required()
def get_track(track_id):
    user_id = get_current_user_id()
    resolved = resolve_track(track_id, user_id=user_id)
    if not resolved:
        return jsonify({"error": "Track not found"}), 404

    track_data = load_track_json(resolved)
    if not track_data:
        return jsonify({"error": "Track data not found"}), 404

    sessions_count, best_lap_time = _user_track_summary(user_id, track_id)
    tbl_data = None
    tbl_file = user_tbl_file_path(user_id, resolved)
    if sessions_count == 0:
        if tbl_file.exists():
            tbl_file.unlink()
    elif tbl_file.exists():
        tbl_data = load_json_file(tbl_file)

    return jsonify({
        **track_data,
        "tbl": tbl_data,
        "sessions_count": sessions_count,
        "best_lap_time": best_lap_time,
    })


@tracks_bp.route('/api/tracks/<int:track_id>', methods=['POST'])
@jwt_required()
def update_track(track_id):
    user_id = get_current_user_id()
    resolved = resolve_track(track_id, user_id=user_id)
    if not resolved:
        return jsonify({"error": "Track not found"}), 404
    if resolved["track_scope"] == "global":
        return jsonify({"error": "Global tracks are read-only"}), 403

    track_file = track_file_path(resolved, "track.json")
    if not track_file.exists():
        return jsonify({"error": "Track data not found"}), 404

    with open(track_file, 'r') as handle:
        track_data = json.load(handle)

    updates = request.json or {}
    allowed_fields = ['pit_center_lat', 'pit_center_lon', 'pit_radius_m', 'track_name']
    for field in allowed_fields:
        if field in updates:
            track_data[field] = updates[field]

    with open(track_file, 'w') as handle:
        json.dump(track_data, handle)
    return jsonify({"success": True, "track": track_data})


@tracks_bp.route('/api/tracks/<int:track_id>/map')
@jwt_required()
def get_track_map(track_id):
    user_id = get_current_user_id()
    resolved = resolve_track(track_id, user_id=user_id)
    if not resolved:
        return jsonify({"error": "Track not found"}), 404

    candidates = [
        ("layout_preview.svg", "image/svg+xml"),
        ("layout.svg", "image/svg+xml"),
        ("preview_overlay.svg", "image/svg+xml"),
        ("track_map.png", "image/png"),
    ]
    for filename, mimetype in candidates:
        path = track_file_path(resolved, filename)
        if path.exists():
            return send_file(path, mimetype=mimetype)

    return jsonify({"error": "Map not found"}), 404


@tracks_bp.route('/api/tracks/<int:track_id>/layout')
@jwt_required()
def get_track_layout(track_id):
    user_id = get_current_user_id()
    resolved = resolve_track(track_id, user_id=user_id)
    if not resolved:
        return jsonify({"error": "Track not found"}), 404
    layout = load_track_layout(resolved)
    if not layout:
        return jsonify({"error": "Canonical layout not found"}), 404
    track_data = load_track_json(resolved) or {}
    layout["sectors"] = track_data.get("sectors") or []
    layout["start_line"] = track_data.get("start_line")
    return jsonify(layout)


@tracks_bp.route('/api/tracks/<int:track_id>/rename', methods=['POST'])
@jwt_required()
def rename_track(track_id):
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    resolved = resolve_track(track_id, user_id=current_user_id)
    if not resolved:
        return jsonify({"error": "Track not found"}), 404
    if resolved["track_scope"] == "global":
        return jsonify({"error": "Global tracks are admin-managed"}), 403

    track = TrackMeta.query.filter_by(track_id=track_id, user_id=current_user_id).first()
    if not track:
        return jsonify({"error": "Track not found"}), 404

    data = request.get_json() or {}
    new_name = data.get('new_name')
    if not new_name:
        return jsonify({"error": "new_name required"}), 400
    if len(new_name) > 255:
        return jsonify({"error": "Track name too long (max 255 characters)"}), 400

    old_name = track.track_name
    track.track_name = new_name
    db.session.commit()

    track_json_path = track_file_path(resolved, "track.json")
    if track_json_path.exists():
        with open(track_json_path, 'r') as handle:
            track_data = json.load(handle)
        track_data['track_name'] = new_name
        with open(track_json_path, 'w') as handle:
            json.dump(track_data, handle, indent=4)

    return jsonify({
        "success": True,
        "message": f"Renamed '{old_name}' to '{new_name}'"
    })


@tracks_bp.route('/api/tracks/<int:track_id>/geometry')
@jwt_required()
def get_track_geometry(track_id):
    user_id = get_current_user_id()
    resolved = resolve_track(track_id, user_id=user_id)
    if not resolved:
        return jsonify({"error": "Track not found"}), 404

    geo_path = track_file_path(resolved, "geometry.json")
    if geo_path.exists():
        return send_file(geo_path)
    return jsonify({"error": "Geometry not found"}), 404


@tracks_bp.route('/api/tracks/<int:track_id>/active', methods=['POST'])
@jwt_required()
def set_active_track(track_id):
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    resolved = resolve_track(track_id, user_id=current_user_id)
    if not resolved:
        return jsonify({"error": "Track not found or access denied"}), 404

    user.active_track_id = track_id
    db.session.commit()
    return jsonify({"success": True, "active_track_id": track_id})


@tracks_bp.route('/api/tracks/<int:track_id>', methods=['DELETE'])
@jwt_required()
def delete_track_endpoint(track_id):
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    resolved = resolve_track(track_id, user_id=current_user_id)
    if not resolved:
        return jsonify({"error": "Track not found or access denied"}), 404
    if resolved["track_scope"] == "global":
        return jsonify({"error": "Global tracks cannot be deleted by users"}), 403

    track_meta = TrackMeta.query.filter_by(track_id=track_id, user_id=current_user_id).first()
    if not track_meta:
        return jsonify({"error": "Track not found or access denied"}), 404

    sessions_to_delete = SessionMeta.query.filter_by(track_id=track_id, user_id=current_user_id).all()
    deleted_sessions = 0
    user_sessions_dir = config.get_user_sessions_dir(current_user_id)
    for session in sessions_to_delete:
        s_file = user_sessions_dir / f"{session.session_id}.json"
        t_file = user_sessions_dir / f"{session.session_id}_telemetry.json"
        if s_file.exists():
            s_file.unlink()
        if t_file.exists():
            t_file.unlink()
        db.session.delete(session)
        deleted_sessions += 1

    track_dir = config.get_user_tracks_dir(current_user_id) / track_meta.folder_name
    if track_dir.exists():
        shutil.rmtree(track_dir, ignore_errors=True)

    db.session.delete(track_meta)
    db.session.commit()
    return jsonify({
        "success": True,
        "message": f"Deleted track '{track_meta.folder_name}' and {deleted_sessions} sessions."
    })
