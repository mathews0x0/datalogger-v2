from flask import Blueprint, jsonify, request, send_file, Response
from flask_jwt_extended import jwt_required, get_jwt_identity
import os
import json
import shutil

from api.models import db, User, TrackMeta, SessionMeta
import api.config as config
from api.helpers import get_track_folder

tracks_bp = Blueprint('tracks', __name__)

@tracks_bp.route('/api/tracks')
@jwt_required()
def get_tracks():
    """Get all tracks for current user"""
    user_id = get_jwt_identity()
    tracks_meta = TrackMeta.query.filter_by(user_id=user_id).all()
    
    tracks = []
    for t in tracks_meta:
        session_count = SessionMeta.query.filter_by(user_id=user_id, track_id=t.track_id).count()
        
        tracks.append({
            "track_id": t.track_id,
            "track_name": t.track_name,
            "folder_name": t.folder_name,
            "sessions_count": session_count
        })
    
    return jsonify({"tracks": tracks})

@tracks_bp.route('/api/tracks/<int:track_id>')
@jwt_required()
def get_track(track_id):
    """Get track details including TBL"""
    user_id = get_jwt_identity()
    folder = get_track_folder(track_id, user_id=user_id)
    if not folder:
        return jsonify({"error": "Track not found"}), 404
    
    track_dir = config.get_user_tracks_dir(user_id) / folder
    
    # Load track.json
    track_file = track_dir / "track.json"
    if not track_file.exists():
        return jsonify({"error": "Track data not found"}), 404
    
    with open(track_file, 'r') as f:
        track_data = json.load(f)
    
    # Load tbl.json
    tbl_file = track_dir / "tbl.json"
    tbl_data = None
    if tbl_file.exists():
        with open(tbl_file, 'r') as f:
            tbl_data = json.load(f)
    
    # Filter sessions by user_id
    sessions_meta = SessionMeta.query.filter_by(user_id=user_id, track_id=track_id).all()
    best_lap_time = None
    
    for s in sessions_meta:
        if s.best_lap_time:
            if best_lap_time is None or s.best_lap_time < best_lap_time:
                best_lap_time = s.best_lap_time
    
    return jsonify({
        **track_data,
        "tbl": tbl_data,
        "sessions_count": len(sessions_meta),
        "best_lap_time": best_lap_time
    })

@tracks_bp.route('/api/tracks/<int:track_id>', methods=['POST'])
@jwt_required()
def update_track(track_id):
    """Update track metadata"""
    user_id = get_jwt_identity()
    folder = get_track_folder(track_id, user_id=user_id)
    if not folder:
        return jsonify({"error": "Track not found"}), 404
    
    track_dir = config.get_user_tracks_dir(user_id) / folder
    track_file = track_dir / "track.json"
    
    if not track_file.exists():
        return jsonify({"error": "Track data not found"}), 404
    
    try:
        with open(track_file, 'r') as f:
            track_data = json.load(f)
            
        updates = request.json
        # Only allow specific fields to be updated
        allowed_fields = ['pit_center_lat', 'pit_center_lon', 'pit_radius_m', 'track_name']
        for field in allowed_fields:
            if field in updates:
                track_data[field] = updates[field]
                
        with open(track_file, 'w') as f:
            json.dump(track_data, f)
            
        return jsonify({"success": True, "track": track_data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@tracks_bp.route('/api/tracks/<int:track_id>/map')
@jwt_required()
def get_track_map(track_id):
    """Get track map image"""
    user_id = get_jwt_identity()
    folder = get_track_folder(track_id, user_id=user_id)
    if not folder:
        return jsonify({"error": "Track not found"}), 404
    
    track_dir = config.get_user_tracks_dir(user_id) / folder
    map_file = track_dir / "track_map.png"
    if not map_file.exists():
        return jsonify({"error": "Map not found"}), 404
    
    return send_file(map_file, mimetype='image/png')

@tracks_bp.route('/api/tracks/<int:track_id>/rename', methods=['POST'])
@jwt_required()
def rename_track(track_id):
    """Rename a track"""
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    # Try to find the user's own track first
    track = TrackMeta.query.filter_by(track_id=track_id, user_id=current_user_id).first()
    
    # If not found but user is admin, allow looking up any record
    if not track and current_user.is_admin:
        track = TrackMeta.query.filter_by(track_id=track_id).first()

    if not track:
        return jsonify({"error": "Track not found"}), 404
    
    if int(track.user_id) != current_user_id and not current_user.is_admin:
        return jsonify({"error": "Access denied"}), 403

    data = request.get_json()
    new_name = data.get('new_name')
    
    if not new_name:
        return jsonify({"error": "new_name required"}), 400
    
    if len(new_name) > 255:
        return jsonify({"error": "Track name too long (max 255 characters)"}), 400
    
    try:
        old_name = track.track_name
        track.track_name = new_name
        db.session.commit()
        
        return jsonify({
            "success": True,
            "message": f"Renamed '{old_name}' to '{new_name}'"
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@tracks_bp.route('/api/tracks/<int:track_id>/geometry')
@jwt_required()
def get_track_geometry(track_id):
    """Serve the geometry.json file for a track."""
    user_id = get_jwt_identity()
    folder_name = get_track_folder(track_id, user_id=user_id)
    if not folder_name:
         return jsonify({"error": "Track not found"}), 404
         
    track_dir = config.get_user_tracks_dir(user_id)
    geo_path = track_dir / folder_name / "geometry.json"
    if geo_path.exists():
        return send_file(geo_path)
    
    return jsonify({"error": "Geometry not found. Please regenerate track."}), 404
@tracks_bp.route('/api/tracks/<int:track_id>', methods=['DELETE'])
@jwt_required()
def delete_track_endpoint(track_id):
    # Ownership check
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    # Try specific user track first
    track_meta = TrackMeta.query.filter_by(track_id=track_id, user_id=current_user_id).first()
    
    # Admin fallback
    if not track_meta and current_user.is_admin:
        track_meta = TrackMeta.query.filter_by(track_id=track_id).first()

    if not track_meta:
        return jsonify({"error": "Track not found or access denied"}), 404

    if int(track_meta.user_id) != current_user_id and not current_user.is_admin:
        return jsonify({"error": "Access denied — you can only delete your own tracks"}), 403

    from src.analysis.core.registry_manager import RegistryManager
    
    try:
        user_tracks_dir = config.get_user_tracks_dir(current_user_id)
        registry_path = user_tracks_dir / "registry.json"
        registry = RegistryManager(registry_path=str(registry_path))
        
        track = registry.get_track_by_id(track_id)
        # If not in registry but in DB, we should still clean up DB
        folder_name = track_meta.folder_name
        print(f"[API] Deleting track {track_id} ({folder_name}) for user {current_user_id}...")
        
        # 1. Delete associated processed sessions for THIS user only
        sessions_to_delete = SessionMeta.query.filter_by(track_id=track_id, user_id=current_user_id).all()
        
        deleted_sessions = 0
        user_sessions_dir = config.get_user_sessions_dir(current_user_id)
        for s in sessions_to_delete:
            s_file = user_sessions_dir / f"{s.session_id}.json"
            t_file = user_sessions_dir / f"{s.session_id}_telemetry.json"
            try:
                if s_file.exists(): os.remove(s_file)
                if t_file.exists(): os.remove(t_file)
                db.session.delete(s)
                deleted_sessions += 1
            except Exception as e:
                print(f"Failed to delete session {s.session_id}: {e}")
        
        # 2. Delete Track Folder
        track_dir = user_tracks_dir / folder_name
        if track_dir.exists():
            shutil.rmtree(track_dir, ignore_errors=True)
            
        # Also remove from registry.json if it's there
        registry.delete_track(track_id)
        
        # 3. Remove from DB
        db.session.delete(track_meta)
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": f"Deleted track '{folder_name}' and {deleted_sessions} sessions."
        })
        
    except Exception as e:
        print(f"[API] Delete Track Error: {e}")
        return jsonify({"error": f"Failed to delete: {str(e)}"}), 500

