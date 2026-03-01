from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
import os
import json

from api.models import db, User, SessionMeta, TrackMeta, TrackDayMeta, TeamMember
import api.config as config
from api.helpers import robust_get_json
from api.blueprints.sessions import load_trackdays

leaderboards_bp = Blueprint('leaderboards', __name__)

@leaderboards_bp.route('/api/leaderboards/track/<int:track_id>')
def get_track_leaderboard(track_id):
    """Get leaderboard for a specific track"""
    period = request.args.get('period', 'all') # all, month, week
    
    query = db.session.query(
        SessionMeta.user_id,
        db.func.min(SessionMeta.best_lap_time).label('best_lap'),
        User.name,
        User.bike_info,
        SessionMeta.start_time,
        SessionMeta.session_id
    ).join(User, SessionMeta.user_id == User.id).filter(
        SessionMeta.track_id == track_id,
        SessionMeta.is_public == True,
        SessionMeta.best_lap_time > 0
    )
    
    # Apply period filter if needed
    # Note: start_time is stored as string in format "2025-02-07 14:05:32"
    if period == 'month':
        from datetime import datetime, timedelta
        month_ago = (datetime.utcnow() - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
        query = query.filter(SessionMeta.start_time >= month_ago)
    elif period == 'week':
        from datetime import datetime, timedelta
        week_ago = (datetime.utcnow() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        query = query.filter(SessionMeta.start_time >= week_ago)
        
    # Group by user to get one entry per user
    query = query.group_by(SessionMeta.user_id)
    
    # Sort by best lap
    results = query.order_by('best_lap').all()
    
    leaderboard = []
    for i, res in enumerate(results):
        leaderboard.append({
            "rank": i + 1,
            "user_id": res.user_id,
            "user_name": res.name or f"Rider {res.user_id}",
            "lap_time": res.best_lap,
            "date": res.start_time,
            "bike_info": res.bike_info,
            "session_id": res.session_id
        })
        
    return jsonify(leaderboard)

@leaderboards_bp.route('/api/leaderboards/trackday/<trackday_id>')
def get_trackday_leaderboard(trackday_id):
    """Get leaderboard for a specific trackday across all participants"""
    td_meta = TrackDayMeta.query.filter_by(trackday_id=trackday_id).first()
    if not td_meta:
        return jsonify({"error": "Trackday not found"}), 404
    
    trackdays = load_trackdays(td_meta.user_id)
    td_data = next((td for td in trackdays if td['id'] == trackday_id), None)
    if not td_data:
        return jsonify({"error": "Trackday details not found on disk"}), 404
        
    # In V2, we might want to allow multiple users to join a trackday.
    # For now, let's find all public sessions on the same track and same day.
    track_id = td_data.get('track_id')
    date_str = td_data.get('date') # YYYY-MM-DD
    
    if not track_id or not date_str:
        return jsonify({"error": "Incomplete trackday data"}), 400
        
    # Query all public sessions on that track on that day
    query = db.session.query(
        SessionMeta.user_id,
        db.func.min(SessionMeta.best_lap_time).label('best_lap'),
        User.name,
        User.bike_info,
        SessionMeta.start_time,
        SessionMeta.session_id
    ).join(User, SessionMeta.user_id == User.id).filter(
        SessionMeta.track_id == track_id,
        SessionMeta.is_public == True,
        SessionMeta.best_lap_time > 0,
        SessionMeta.start_time.like(f"{date_str}%")
    ).group_by(SessionMeta.user_id).order_by('best_lap')
    
    results = query.all()
    
    leaderboard = []
    for i, res in enumerate(results):
        leaderboard.append({
            "rank": i + 1,
            "user_id": res.user_id,
            "user_name": res.name or f"Rider {res.user_id}",
            "lap_time": res.best_lap,
            "date": res.start_time,
            "bike_info": res.bike_info,
            "session_id": res.session_id
        })
        
    return jsonify({
        "trackday_name": td_data.get('name'),
        "track_name": td_data.get('track_name'),
        "date": date_str,
        "leaderboard": leaderboard
    })

@leaderboards_bp.route('/api/compare', methods=['GET'])
def compare_laps():
    """Compare two laps (optionally from different sessions/users)"""
    s1_id = request.args.get('session1')
    l1_idx = request.args.get('lap1', type=int)
    s2_id = request.args.get('session2')
    l2_idx = request.args.get('lap2', type=int)
    
    if not all([s1_id, l1_idx is not None, s2_id, l2_idx is not None]):
        return jsonify({"error": "Missing parameters"}), 400
        
    def get_lap_telemetry(session_id, lap_idx):
        # Check if session is public or owned by user
        try:
            verify_jwt_in_request(optional=True)
        except:
            pass
        user_id = get_jwt_identity()
        
        s_meta = SessionMeta.query.filter_by(session_id=session_id).first()
        if not s_meta:
            return None, "Session not found"
            
        if not s_meta.is_public:
            if not user_id:
                return None, "Access denied"
            
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
                    return None, "Access denied"
        
        # Load session to get lap start/end indices
        sessions_dir = config.get_user_sessions_dir(s_meta.user_id)
        session_file = sessions_dir / f"{session_id}.json"
        if not session_file.exists():
            return None, "Session data not found"
            
        with open(session_file, 'r') as f:
            s_data = json.load(f)
            
        laps = s_data.get('laps', [])
        if lap_idx < 0 or lap_idx >= len(laps):
            return None, "Lap index out of range"
            
        lap = laps[lap_idx]
        start_idx = lap.get('start_index')
        end_idx = lap.get('end_index')
        
        # Load telemetry
        telemetry_file = sessions_dir / f"{session_id}_telemetry.json"
        if not telemetry_file.exists():
            return None, "Telemetry data not found"
            
        with open(telemetry_file, 'r') as f:
            t_data = json.load(f)
            
        # Extract lap telemetry
        # Assuming t_data is a list of points or a dict with lists
        if isinstance(t_data, list):
            lap_telemetry = t_data[start_idx:end_idx+1]
        else:
            # Handle other formats if necessary
            lap_telemetry = []
            
        return {
            "lap_info": lap,
            "telemetry": lap_telemetry,
            "user_name": User.query.get(s_meta.user_id).name or f"User {s_meta.user_id}",
            "session_name": s_meta.session_name
        }, None

    lap1_data, err1 = get_lap_telemetry(s1_id, l1_idx)
    if err1: return jsonify({"error": f"Lap 1: {err1}"}), 400
    
    lap2_data, err2 = get_lap_telemetry(s2_id, l2_idx)
    if err2: return jsonify({"error": f"Lap 2: {err2}"}), 400
    
    return jsonify({
        "lap1": lap1_data,
        "lap2": lap2_data
    })


# ============================================================================
# API ROUTES
# ============================================================================

