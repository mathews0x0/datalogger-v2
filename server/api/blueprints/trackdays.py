from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import os
import json
from datetime import datetime
import uuid

from api.models import db, User, TrackDayMeta, SessionMeta
import api.config as config
from api.blueprints.sessions import load_trackdays, save_trackdays

trackdays_bp = Blueprint('trackdays', __name__)

@trackdays_bp.route('/api/trackdays', methods=['GET'])
@jwt_required()
def get_trackdays():
    """Get all trackdays for current user with summary info"""
    user_id = get_jwt_identity()
    trackdays_meta = TrackDayMeta.query.filter_by(user_id=user_id).all()
    
    # We still need to load the session data for counts, or store it in DB
    # For now, let's just use the trackdays.json for the details, but filtered by DB
    trackdays_list = load_trackdays(user_id) # This loads trackdays from user silo
    
    # Filter by IDs found in DB for this user
    user_td_ids = [td.trackday_id for td in trackdays_meta]
    user_trackdays = [td for td in trackdays_list if td['id'] in user_td_ids]
    
    # Enrich with session counts and quick stats
    user_sessions_dir = config.get_user_sessions_dir(user_id)
    for td in user_trackdays:
        sessions = td.get('session_ids', [])
        td['session_count'] = len(sessions)
        
        # Calculate aggregate stats
        total_laps = 0
        best_lap = None
        
        for sid in sessions:
            try:
                session_path = user_sessions_dir / f"{sid}.json"
                if session_path.exists():
                    with open(session_path, 'r') as f:
                        sdata = json.load(f)
                        if 'summary' in sdata:
                            total_laps += sdata['summary'].get('total_laps', 0)
                            slap = sdata['summary'].get('best_lap_time')
                            if slap and (best_lap is None or slap < best_lap):
                                best_lap = slap
            except Exception:
                pass
        
        td['total_laps'] = total_laps
        td['best_lap_time'] = best_lap
    
    return jsonify(user_trackdays)

@trackdays_bp.route('/api/trackdays', methods=['POST'])
@jwt_required()
def create_trackday():
    """Create a new trackday"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    trackdays = load_trackdays(user_id)
    
    # Generate unique ID
    import uuid
    trackday_id = f"td_{uuid.uuid4().hex[:8]}"
    
    new_trackday = {
        'id': trackday_id,
        'name': data.get('name', 'Untitled Trackday'),
        'date': data.get('date', datetime.now().strftime('%Y-%m-%d')),
        'organizer': data.get('organizer', ''),
        'rider_name': data.get('rider_name', ''),
        'track_id': data.get('track_id'),
        'track_name': data.get('track_name', ''),
        'notes': data.get('notes', ''),
        'session_ids': [],
        'created_at': datetime.now().isoformat()
    }
    
    trackdays.append(new_trackday)
    save_trackdays(user_id, trackdays)
    
    # Save to DB for tracking user ownership
    td_meta = TrackDayMeta(
        trackday_id=trackday_id,
        user_id=user_id,
        name=new_trackday['name'],
        date=new_trackday['date']
    )
    db.session.add(td_meta)
    db.session.commit()
    
    return jsonify(new_trackday), 201

@trackdays_bp.route('/api/trackdays/<trackday_id>', methods=['GET'])
@jwt_required()
def get_trackday(trackday_id):
    """Get full trackday details with aggregated data from all sessions"""
    user_id = get_jwt_identity()
    # Check ownership
    td_meta = TrackDayMeta.query.filter_by(trackday_id=trackday_id, user_id=user_id).first()
    if not td_meta:
        return jsonify({"error": "Trackday not found or access denied"}), 404

    trackdays = load_trackdays(user_id)
    trackday = next((td for td in trackdays if td['id'] == trackday_id), None)
    if not trackday:
        return jsonify({"error": "Trackday data not found"}), 404
    
    # Aggregate all sessions
    user_sessions_dir = config.get_user_sessions_dir(user_id)
    all_laps = []
    all_sector_times = []
    total_duration = 0
    best_lap_time = None
    sessions_data = []
    sector_count = 0
    
    for sid in trackday.get('session_ids', []):
        try:
            session_path = user_sessions_dir / f"{sid}.json"
            if session_path.exists():
                with open(session_path, 'r') as f:
                    sdata = json.load(f)
                    
                sessions_data.append({
                    'session_id': sid,
                    'session_name': sdata.get('meta', {}).get('session_name', sid),
                    'start_time': sdata.get('meta', {}).get('start_time'),
                    'total_laps': sdata.get('summary', {}).get('total_laps', 0),
                    'best_lap_time': sdata.get('summary', {}).get('best_lap_time')
                })
                
                total_duration += sdata.get('meta', {}).get('duration_sec', 0)
                
                # Get sector count
                if 'track' in sdata:
                    sector_count = max(sector_count, sdata['track'].get('sector_count', 0))
                
                # Collect laps
                for lap in sdata.get('laps', []):
                    lap_copy = lap.copy()
                    lap_copy['session_id'] = sid
                    lap_copy['session_name'] = sdata.get('meta', {}).get('session_name', sid)
                    all_laps.append(lap_copy)
                    
                    if lap.get('lap_time') and lap.get('valid'):
                        if best_lap_time is None or lap['lap_time'] < best_lap_time:
                            best_lap_time = lap['lap_time']
        except Exception as e:
            print(f"[Trackday] Error loading session {sid}: {e}")
    
    # Sort laps by lap time
    all_laps.sort(key=lambda x: x.get('lap_time') or 999999)
    
    # Mark best lap in trackday
    if all_laps and all_laps[0].get('lap_time'):
        all_laps[0]['is_trackday_best'] = True
    
    # Calculate sector medians
    sector_medians = []
    for i in range(sector_count):
        times = [l['sector_times'][i] for l in all_laps if l.get('sector_times') and len(l['sector_times']) > i and l['sector_times'][i] > 0]
        sector_medians.append(sum(times) / len(times) if times else 0)
    
    # Calculate consistency
    valid_times = [l['lap_time'] for l in all_laps if l.get('lap_time') and l.get('valid')]
    consistency = 0
    if len(valid_times) > 1:
        import statistics
        consistency = statistics.stdev(valid_times)
    
    # Calculate TBL (Theoretical Best Lap) - best sector times across all laps
    tbl_sectors = []
    tbl_total = 0
    for i in range(sector_count):
        sector_times = [l['sector_times'][i] for l in all_laps 
                       if l.get('sector_times') and len(l['sector_times']) > i and l['sector_times'][i] > 0]
        if sector_times:
            best_sector = min(sector_times)
            tbl_sectors.append(best_sector)
            tbl_total += best_sector
        else:
            tbl_sectors.append(0)
    
    result = {
        **trackday,
        'sessions': sessions_data,
        'laps': all_laps,
        'summary': {
            'total_sessions': len(sessions_data),
            'total_laps': len(all_laps),
            'total_duration': total_duration,
            'best_lap_time': best_lap_time,
            'consistency': round(consistency, 3)
        },
        'sector_count': sector_count,
        'sector_medians': sector_medians,
        'tbl': {
            'total': round(tbl_total, 3) if tbl_total > 0 else None,
            'sectors': tbl_sectors
        } if tbl_total > 0 else None
    }
    
    return jsonify(result)

@trackdays_bp.route('/api/trackdays/<trackday_id>', methods=['PUT'])
@jwt_required()
def update_trackday(trackday_id):
    """Update trackday details"""
    user_id = get_jwt_identity()
    # Check ownership
    td_meta = TrackDayMeta.query.filter_by(trackday_id=trackday_id, user_id=user_id).first()
    if not td_meta:
        return jsonify({"error": "Trackday not found or access denied"}), 404

    data = request.get_json()
    trackdays = load_trackdays(user_id)
    
    for td in trackdays:
        if td['id'] == trackday_id:
            td['name'] = data.get('name', td['name'])
            td['date'] = data.get('date', td['date'])
            td['organizer'] = data.get('organizer', td['organizer'])
            td['rider_name'] = data.get('rider_name', td.get('rider_name', ''))
            td['notes'] = data.get('notes', td['notes'])
            save_trackdays(user_id, trackdays)
            
            # Update DB meta too
            td_meta.name = td['name']
            td_meta.date = td['date']
            db.session.commit()
            
            return jsonify(td)
    
    return jsonify({"error": "Trackday data not found"}), 404

@trackdays_bp.route('/api/trackdays/<trackday_id>', methods=['DELETE'])
@jwt_required()
def delete_trackday(trackday_id):
    """Delete a trackday (does not delete sessions)"""
    user_id = get_jwt_identity()
    # Check ownership
    td_meta = TrackDayMeta.query.filter_by(trackday_id=trackday_id, user_id=user_id).first()
    if not td_meta:
        return jsonify({"error": "Trackday not found or access denied"}), 404

    trackdays = load_trackdays(user_id)
    trackdays = [td for td in trackdays if td['id'] != trackday_id]
    save_trackdays(user_id, trackdays)
    
    # Remove from DB
    db.session.delete(td_meta)
    db.session.commit()
    
    return jsonify({"success": True})

@trackdays_bp.route('/api/trackdays/<trackday_id>/sessions/<session_id>', methods=['POST'])
@jwt_required()
def tag_session_to_trackday(trackday_id, session_id):
    """Add a session to a trackday"""
    user_id = get_jwt_identity()
    # Check ownership of both trackday and session
    td_meta = TrackDayMeta.query.filter_by(trackday_id=trackday_id, user_id=user_id).first()
    s_meta = SessionMeta.query.filter_by(session_id=session_id, user_id=user_id).first()
    
    if not td_meta or not s_meta:
        return jsonify({"error": "Trackday or session not found or access denied"}), 404

    trackdays = load_trackdays(user_id)
    for td in trackdays:
        if td['id'] == trackday_id:
            if 'session_ids' not in td:
                td['session_ids'] = []
            if session_id not in td['session_ids']:
                td['session_ids'].append(session_id)
                save_trackdays(user_id, trackdays)
            return jsonify({"success": True, "session_ids": td['session_ids']})
    
    return jsonify({"error": "Trackday data not found"}), 404

@trackdays_bp.route('/api/trackdays/<trackday_id>/sessions/<session_id>', methods=['DELETE'])
@jwt_required()
def untag_session_from_trackday(trackday_id, session_id):
    """Remove a session from a trackday"""
    user_id = get_jwt_identity()
    # Check ownership
    td_meta = TrackDayMeta.query.filter_by(trackday_id=trackday_id, user_id=user_id).first()
    if not td_meta:
        return jsonify({"error": "Trackday not found or access denied"}), 404

    trackdays = load_trackdays(user_id)
    for td in trackdays:
        if td['id'] == trackday_id:
            if session_id in td.get('session_ids', []):
                td['session_ids'].remove(session_id)
                save_trackdays(user_id, trackdays)
            return jsonify({"success": True, "session_ids": td.get('session_ids', [])})
    
    return jsonify({"error": "Trackday data not found"}), 404

