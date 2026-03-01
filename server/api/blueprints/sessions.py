from flask import Blueprint, jsonify, request, send_file, Response, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
import os
import json
import zipfile
import io
import time
from werkzeug.utils import safe_join

from api.models import db, User, SessionMeta, TrackMeta
from api.decorators import require_tier, local_only
import api.config as config
from api.helpers import get_track_folder

sessions_bp = Blueprint('sessions', __name__)

@sessions_bp.route('/api/sessions')
@jwt_required()
def get_sessions():
    """Get all sessions for current user, optionally filtered by track_id or user_id (coach only)"""
    current_user_id = int(get_jwt_identity())
    track_id = request.args.get('track_id', type=int)
    target_user_id = request.args.get('user_id', type=int)
    
    user_id_to_query = current_user_id
    if target_user_id and target_user_id != current_user_id:
        # Check if caller is coach/owner of a team target belongs to
        has_access = False
        target_teams = TeamMember.query.filter_by(user_id=target_user_id).all()
        for tt in target_teams:
            caller_membership = TeamMember.query.filter_by(team_id=tt.team_id, user_id=current_user_id).first()
            if caller_membership and caller_membership.role in ['owner', 'coach']:
                has_access = True
                break
        
        if not has_access:
            return jsonify({"error": "Access denied"}), 403
        user_id_to_query = target_user_id
    
    query = SessionMeta.query.filter_by(user_id=user_id_to_query)
    if track_id:
        query = query.filter_by(track_id=track_id)
    
    sessions_meta = query.order_by(SessionMeta.start_time.desc()).all()
    
    sessions = []
    for s in sessions_meta:
        # Get track name for response
        track = TrackMeta.query.filter_by(track_id=s.track_id).first()
        track_name = track.track_name if track else 'Unknown'
        
        # Get owner name
        owner = User.query.get(s.user_id)
        owner_name = owner.name if owner else "Unknown"
        
        sessions.append({
            'session_id': s.session_id,
            'session_name': s.session_name,
            'start_time': s.start_time,
            'duration_sec': s.duration_sec,
            'track_id': s.track_id,
            'track_name': track_name,
            'total_laps': s.total_laps,
            'best_lap_time': s.best_lap_time,
            'owner_name': owner_name,
            'owner_id': s.user_id,
            'is_public': s.is_public,
            'share_token': s.share_token
        })
    
    return jsonify(sessions)

@sessions_bp.route('/api/sessions/<path:session_id>')
def get_session(session_id):
    """Get full session data"""
    try:
        verify_jwt_in_request(optional=True)
    except:
        pass
    user_id = get_jwt_identity()
    
    # Check if session belongs to user or is public
    s_meta = SessionMeta.query.filter_by(session_id=session_id).first()
    if not s_meta:
        return jsonify({"error": "Session not found"}), 404
        
    if not s_meta.is_public:
        if not user_id:
            return jsonify({"error": "Access denied"}), 401
            
        user_id = int(user_id)
        if int(s_meta.user_id) != user_id:
            # Phase 5: Team Check
            has_team_access = False
            owner_teams = TeamMember.query.filter_by(user_id=s_meta.user_id).all()
            for ot in owner_teams:
                caller_membership = TeamMember.query.filter_by(team_id=ot.team_id, user_id=user_id).first()
                if caller_membership and caller_membership.role in ['owner', 'coach']:
                    has_team_access = True
                    break
            
            if not has_team_access:
                return jsonify({"error": "Access denied"}), 403
        
    sessions_dir = config.get_user_sessions_dir(s_meta.user_id)
    session_file = sessions_dir / f"{session_id}.json"
    
    if not session_file.exists():
        return jsonify({"error": "Session data file not found"}), 404
        
    with open(session_file, 'r') as f:
        session_data = json.load(f)
    
    # Add privacy info from DB
    session_data['is_public'] = s_meta.is_public
    session_data['share_token'] = s_meta.share_token
    
    # Add owner info for public/shared views
    owner = User.query.get(s_meta.user_id)
    session_data['owner_name'] = owner.name if owner else "Unknown Rider"
    session_data['is_shared_view'] = (not user_id or int(s_meta.user_id) != int(user_id))
    
    # Transform old format to new format for frontend compatibility
    if 'summary' not in session_data and 'aggregates' in session_data:
        session_data['summary'] = {
            'total_laps': len(session_data.get('laps', [])),
            'best_lap_time': session_data.get('aggregates', {}).get('best_lap_time', 0),
            'tbl_improved': False
        }
    
    return jsonify(session_data)

@sessions_bp.route('/api/sessions/<path:session_id>/telemetry')
def get_session_telemetry(session_id):
    """Get full telemetry data for a session"""
    try:
        verify_jwt_in_request(optional=True)
    except:
        pass
    user_id = get_jwt_identity()
    
    # Check if session belongs to user or is public
    s_meta = SessionMeta.query.filter_by(session_id=session_id).first()
    if not s_meta:
        return jsonify({"error": "Session not found"}), 404
        
    if not s_meta.is_public:
        if not user_id:
            return jsonify({"error": "Access denied"}), 401
            
        user_id = int(user_id)
        if int(s_meta.user_id) != user_id:
            # Phase 5: Team Check
            has_team_access = False
            owner_teams = TeamMember.query.filter_by(user_id=s_meta.user_id).all()
            for ot in owner_teams:
                caller_membership = TeamMember.query.filter_by(team_id=ot.team_id, user_id=user_id).first()
                if caller_membership and caller_membership.role in ['owner', 'coach']:
                    has_team_access = True
                    break
            
            if not has_team_access:
                return jsonify({"error": "Access denied"}), 403
        
    sessions_dir = config.get_user_sessions_dir(s_meta.user_id)
    telemetry_file = sessions_dir / f"{session_id}_telemetry.json"
    
    if telemetry_file.exists():
        return send_file(telemetry_file, mimetype='application/json')
    
    return jsonify({"error": "Telemetry data not found"}), 404

@sessions_bp.route('/api/sessions/<path:session_id>/privacy', methods=['PUT'])
@jwt_required()
def toggle_session_privacy(session_id):
    """Toggle session public/private status"""
    user_id = int(get_jwt_identity())
    s_meta = SessionMeta.query.filter_by(session_id=session_id, user_id=user_id).first()
    
    if not s_meta:
        return jsonify({"error": "Session not found or access denied"}), 404
        
    data = request.get_json()
    is_public = data.get('is_public', False)
    
    s_meta.is_public = is_public
    db.session.commit()
    
    return jsonify({"success": True, "is_public": s_meta.is_public})

@sessions_bp.route('/api/sessions/<path:session_id>/share', methods=['POST'])
@jwt_required()
def generate_share_link(session_id):
    """Generate or retrieve a share token for a session"""
    user_id = int(get_jwt_identity())
    s_meta = SessionMeta.query.filter_by(session_id=session_id, user_id=user_id).first()
    
    if not s_meta:
        return jsonify({"error": "Session not found or access denied"}), 404
        
    if not s_meta.share_token:
        s_meta.share_token = str(uuid.uuid4())
        
    db.session.commit()
    
    return jsonify({
        "success": True, 
        "share_token": s_meta.share_token,
        "share_url": f"/shared/{s_meta.share_token}"
    })

@sessions_bp.route('/api/shared/<token>')
def get_shared_session(token):
    """Get session data via share token (NO AUTH REQUIRED)"""
    s_meta = SessionMeta.query.filter_by(share_token=token).first()
    
    if not s_meta:
        return jsonify({"error": "Shared session not found"}), 404
        
    # Optional: check expiry if implemented
    if s_meta.share_expires_at and s_meta.share_expires_at < datetime.utcnow():
        return jsonify({"error": "Shared link has expired"}), 410
        
    sessions_dir = config.get_user_sessions_dir(s_meta.user_id)
    session_file = sessions_dir / f"{s_meta.session_id}.json"
    
    if not session_file.exists():
        return jsonify({"error": "Session data file not found"}), 404
        
    with open(session_file, 'r') as f:
        session_data = json.load(f)
    
    # Add owner info
    owner = User.query.get(s_meta.user_id)
    session_data['owner_name'] = owner.name if owner else "Unknown Rider"
    session_data['is_shared_view'] = True
    
    return jsonify(session_data)

@sessions_bp.route('/api/shared/<token>/telemetry')
def get_shared_telemetry(token):
    """Get telemetry via share token (NO AUTH REQUIRED)"""
    s_meta = SessionMeta.query.filter_by(share_token=token).first()
    
    if not s_meta:
        return jsonify({"error": "Shared session not found"}), 404
        
    sessions_dir = config.get_user_sessions_dir(s_meta.user_id)
    telemetry_file = sessions_dir / f"{s_meta.session_id}_telemetry.json"
    
    if telemetry_file.exists():
        return send_file(telemetry_file, mimetype='application/json')
    
    return jsonify({"error": "Telemetry data not found"}), 404

@sessions_bp.route('/api/public/sessions')
def get_public_sessions():
    """Get all public sessions"""
    track_id = request.args.get('track_id', type=int)
    
    query = SessionMeta.query.filter_by(is_public=True)
    if track_id:
        query = query.filter_by(track_id=track_id)
    
    sessions_meta = query.order_by(SessionMeta.start_time.desc()).all()
    
    sessions = []
    for s in sessions_meta:
        # Get track name for response
        track = TrackMeta.query.filter_by(track_id=s.track_id).first()
        track_name = track.track_name if track else 'Unknown'
        
        # Get owner name
        owner = User.query.get(s.user_id)
        owner_name = owner.name if owner else "Unknown"
        
        sessions.append({
            'session_id': s.session_id,
            'session_name': s.session_name,
            'start_time': s.start_time,
            'duration_sec': s.duration_sec,
            'track_id': s.track_id,
            'track_name': track_name,
            'total_laps': s.total_laps,
            'best_lap_time': s.best_lap_time,
            'owner_name': owner_name,
            'owner_id': s.user_id,
            'is_public': True
        })
    
    return jsonify(sessions)

# ============================================================================
# DEVICE TOKEN MANAGEMENT
# ============================================================================

@sessions_bp.route('/api/sessions/<session_id>', methods=['DELETE'])
@jwt_required()
def delete_session_endpoint(session_id):
    """Delete a processed session"""
    s_meta = SessionMeta.query.filter_by(session_id=session_id).first()
    if not s_meta:
        return jsonify({"error": "Session not found"}), 404

    # Ownership check
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)
    if int(s_meta.user_id) != current_user_id and not current_user.is_admin:
        return jsonify({"error": "Access denied — you can only delete your own sessions"}), 403

    try:
        sessions_dir = config.get_user_sessions_dir(s_meta.user_id)
        s_path = sessions_dir / f"{session_id}.json"
        t_path = sessions_dir / f"{session_id}_telemetry.json"
        
        if s_path.exists(): os.remove(s_path)
        if t_path.exists(): os.remove(t_path)
        
        db.session.delete(s_meta)
        db.session.commit()
        return jsonify({"success": True, "message": f"Deleted {session_id}"})
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sessions_bp.route('/api/sessions/<session_id>/rename', methods=['POST'])
@jwt_required()
def rename_session(session_id):
    """Rename a session (updates meta.session_name)"""
    # Ownership check
    current_user_id = int(get_jwt_identity())
    s_meta = SessionMeta.query.filter_by(session_id=session_id).first()
    if not s_meta:
        return jsonify({"error": "Session not found"}), 404
    current_user = User.query.get(current_user_id)
    if int(s_meta.user_id) != current_user_id and not current_user.is_admin:
        return jsonify({"error": "Access denied"}), 403

    data = request.get_json()
    new_name = data.get('new_name')
    if not new_name:
        return jsonify({"error": "new_name required"}), 400

    sessions_dir = config.get_user_sessions_dir(s_meta.user_id)
    safe_id = os.path.basename(session_id).replace('.json', '')
    json_path = sessions_dir / f"{safe_id}.json"
    
    if not json_path.exists():
        return jsonify({"error": "Session not found"}), 404
        
    try:
        with open(json_path, 'r') as f:
            session_data = json.load(f)
            
        session_data['meta']['session_name'] = new_name
        
        with open(json_path, 'w') as f:
            json.dump(session_data, f, indent=2)
            
        return jsonify({"success": True, "new_name": new_name})
    except FileNotFoundError:
        return jsonify({"error": "Session file not found on disk"}), 404
    except Exception:
        # Do not expose raw exception (paths)
        return jsonify({"error": "Failed to rename session due to an internal error"}), 500

@sessions_bp.route('/api/sessions/<session_id>/notes', methods=['PUT'])
@jwt_required()
def update_session_notes(session_id):
    """Update session notes"""
    current_user_id = int(get_jwt_identity())
    s_meta = SessionMeta.query.filter_by(session_id=session_id).first()
    if not s_meta:
        return jsonify({"error": "Session not found"}), 404
    current_user = User.query.get(current_user_id)
    if int(s_meta.user_id) != current_user_id and not current_user.is_admin:
        return jsonify({"error": "Access denied"}), 403

    data = request.get_json()
    notes = data.get('notes', '')
    
    sessions_dir = config.get_user_sessions_dir(s_meta.user_id)
    safe_id = os.path.basename(session_id).replace('.json', '')
    json_path = sessions_dir / f"{safe_id}.json"
    
    if not json_path.exists():
        return jsonify({"error": "Session not found"}), 404
        
    try:
        with open(json_path, 'r') as f:
            session_data = json.load(f)
            
        # Ensure mode section exists
        if 'mode' not in session_data:
            session_data['mode'] = {}
            
        session_data['mode']['notes'] = notes
        
        with open(json_path, 'w') as f:
            json.dump(session_data, f, indent=2)
            
        return jsonify({"success": True, "notes": notes})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@sessions_bp.route('/api/sessions/<session_id>/export')
@jwt_required()
def export_session(session_id):
    """
    Export session data as a ZIP file.
    Includes: session.json and _telemetry.json (if present)
    """
    import zipfile
    import io
    
    # 1. Locate Files
    s_meta = SessionMeta.query.filter_by(session_id=session_id).first()
    if not s_meta:
        return jsonify({"error": "Session not found"}), 404
        
    sessions_dir = config.get_user_sessions_dir(s_meta.user_id)
    
    # Sanitize ID
    safe_id = os.path.basename(session_id).replace('.json', '')
    json_filename = f"{safe_id}.json"
    json_path = sessions_dir / json_filename
    
    if not json_path.exists():
        # Try searching by name? No, ID is safer.
        return jsonify({"error": "Session file not found"}), 404

    # Load data for metadata
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
            
        session_name = data.get('meta', {}).get('session_name', safe_id)
        start_time = data.get('meta', {}).get('start_time', '')
        track_name = data.get('track', {}).get('track_name', 'Unknown')
        best_lap = data.get('summary', {}).get('best_lap_time', 0)
        
        # Format Timestamp
        try:
            dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            date_str = dt.strftime('%Y-%m-%d_%H%M')
            readable_date = dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            date_str = "unknown_date"
            readable_date = start_time
            
        # Create Filename: session_DATE_NAME.zip
        # Sanitize Name
        clean_name = "".join([c for c in session_name if c.isalnum() or c in (' ', '_', '-')]).strip().replace(' ', '_')
        download_name = f"session_{date_str}_{clean_name}.zip"
        
        # README Content
        readme_content = f"""SESSION EXPORT
--------------------------------
Session:  {session_name}
Track:    {track_name}
Date:     {readable_date}
ID:       {safe_id}
--------------------------------
Best Lap: {best_lap}s
Laps:     {len(data.get('laps', []))}
--------------------------------
Generated by Datalogger Companion
"""

    except Exception:
         # Log internally but sanitize output
        print(f"Export Error for {session_id}") 
        return jsonify({"error": "Failed to read session metadata"}), 500

    # 2. Create ZIP in Memory
    mem_zip = io.BytesIO()
    
    try:
        with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Add Main Session JSON
            zf.write(json_path, arcname=json_filename)
            
            # Add README
            zf.writestr("README.txt", readme_content)
            
    except Exception:
        return jsonify({"error": "Failed to create backup archive"}), 500

    # 3. Serve File
    mem_zip.seek(0)
    return send_file(
        mem_zip,
        mimetype='application/zip',
        as_attachment=True,
        download_name=download_name
    )

# ============================================================================
# TRACKDAY AGGREGATION
# ============================================================================

def load_trackdays(user_id):
    """Load user'specific trackdays.json or return empty list"""
    trackdays_file = config.get_user_dir(user_id) / "trackdays.json"
    if trackdays_file.exists():
        with open(trackdays_file, 'r') as f:
            return json.load(f)
    return []

def save_trackdays(user_id, trackdays):
    """Save trackdays to user-specific JSON file"""
    trackdays_file = config.get_user_dir(user_id) / "trackdays.json"
    with open(trackdays_file, 'w') as f:
        json.dump(trackdays, f, indent=2)

