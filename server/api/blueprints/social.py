from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
import os
import json

from api.models import db, User, TrackMeta, SessionMeta, Follow
import api.config as config
from sqlalchemy.orm import aliased

social_bp = Blueprint('social', __name__)

@social_bp.route('/api/users/<int:target_user_id>/follow', methods=['POST'])
@jwt_required()
def follow_user(target_user_id):
    """Follow a user"""
    follower_id = int(get_jwt_identity())
    
    if follower_id == target_user_id:
        return jsonify({"error": "You cannot follow yourself"}), 400
        
    target_user = User.query.get(target_user_id)
    if not target_user:
        return jsonify({"error": "User not found"}), 404
        
    existing_follow = Follow.query.filter_by(follower_id=follower_id, following_id=target_user_id).first()
    if existing_follow:
        return jsonify({"message": "Already following"}), 200
        
    follow = Follow(follower_id=follower_id, following_id=target_user_id)
    db.session.add(follow)
    db.session.commit()
    
    return jsonify({"success": True, "message": f"Following {target_user.name or target_user.email}"})

@social_bp.route('/api/users/<int:target_user_id>/follow', methods=['DELETE'])
@jwt_required()
def unfollow_user(target_user_id):
    """Unfollow a user"""
    follower_id = int(get_jwt_identity())
    
    follow = Follow.query.filter_by(follower_id=follower_id, following_id=target_user_id).first()
    if not follow:
        return jsonify({"error": "Not following"}), 400
        
    db.session.delete(follow)
    db.session.commit()
    
    return jsonify({"success": True, "message": "Unfollowed successfully"})

@social_bp.route('/api/users/<int:user_id>/followers', methods=['GET'])
@jwt_required()
def get_followers(user_id):
    """List followers of a user"""
    follows = Follow.query.filter_by(following_id=user_id).all()
    follower_ids = [f.follower_id for f in follows]
    
    users = User.query.filter(User.id.in_(follower_ids)).all() if follower_ids else []
    return jsonify([u.to_dict() for u in users])

@social_bp.route('/api/users/<int:user_id>/following', methods=['GET'])
@jwt_required()
def get_following(user_id):
    """List users followed by a user"""
    follows = Follow.query.filter_by(follower_id=user_id).all()
    following_ids = [f.following_id for f in follows]
    
    users = User.query.filter(User.id.in_(following_ids)).all() if following_ids else []
    return jsonify([u.to_dict() for u in users])

@social_bp.route('/api/feed/following', methods=['GET'])
@jwt_required()
def get_following_feed():
    """Get recent public sessions from users followed by current user"""
    follower_id = int(get_jwt_identity())
    
    # Get IDs of users we follow
    follows = Follow.query.filter_by(follower_id=follower_id).all()
    following_ids = [f.following_id for f in follows]
    
    if not following_ids:
        return jsonify([])
        
    # Get recent public sessions from these users
    sessions_meta = SessionMeta.query.filter(
        SessionMeta.user_id.in_(following_ids),
        SessionMeta.is_public == True
    ).order_by(SessionMeta.start_time.desc()).limit(20).all()
    
    feed = []
    for s in sessions_meta:
        track = TrackMeta.query.filter_by(track_id=s.track_id).first()
        owner = User.query.get(s.user_id)
        
        feed.append({
            'session_id': s.session_id,
            'session_name': s.session_name,
            'start_time': s.start_time,
            'duration_sec': s.duration_sec,
            'track_id': s.track_id,
            'track_name': track.track_name if track else 'Unknown',
            'total_laps': s.total_laps,
            'best_lap_time': s.best_lap_time,
            'owner_name': owner.name if owner else "Unknown",
            'owner_id': s.user_id,
            'is_public': True
        })
        
    return jsonify(feed)

@social_bp.route('/api/users/<int:user_id>/social-counts', methods=['GET'])
@jwt_required()
def get_social_counts(user_id):
    """Get follower/following counts for a user"""
    followers_count = Follow.query.filter_by(following_id=user_id).count()
    following_count = Follow.query.filter_by(follower_id=user_id).count()
    
    # Check if current user follows this user
    is_following = False
    try:
        verify_jwt_in_request(optional=True)
        current_user_id = get_jwt_identity()
        if current_user_id:
            is_following = Follow.query.filter_by(follower_id=int(current_user_id), following_id=user_id).first() is not None
    except:
        pass
        
    return jsonify({
        "followers_count": followers_count,
        "following_count": following_count,
        "is_following": is_following
    })

@social_bp.route('/api/users/<int:user_id>/stats', methods=['GET'])
@jwt_required()
def get_user_stats(user_id):
    """Get aggregate stats for a user"""
    sessions = SessionMeta.query.filter_by(user_id=user_id).all()
    
    total_sessions = len(sessions)
    total_laps = sum(s.total_laps or 0 for s in sessions)
    
    # Tracks visited
    track_ids = set(s.track_id for s in sessions if s.track_id)
    tracks_visited = len(track_ids)
    
    # Personal bests per track
    pb_query = db.session.query(
        SessionMeta.track_id,
        db.func.min(SessionMeta.best_lap_time).label('best_lap')
    ).filter(
        SessionMeta.user_id == user_id,
        SessionMeta.best_lap_time > 0
    ).group_by(SessionMeta.track_id).all()
    
    personal_bests = []
    for pb in pb_query:
        track = TrackMeta.query.filter_by(track_id=pb.track_id).first()
        personal_bests.append({
            "track_id": pb.track_id,
            "track_name": track.track_name if track else "Unknown Track",
            "best_lap": pb.best_lap
        })
        
    return jsonify({
        "total_sessions": total_sessions,
        "total_laps": total_laps,
        "tracks_visited": tracks_visited,
        "personal_bests": personal_bests
    })

# ============================================================================
# TEAM ENDPOINTS
# ============================================================================

