"""
Datalogger Companion API Server
Flask backend for companion app
"""

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
import os
import json
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
import shutil

# Point to UI folder in same server directory
static_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../ui'))
app = Flask(__name__, static_folder=static_path, static_url_path='')
CORS(app)  # Enable CORS for development

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity, set_access_cookies, unset_jwt_cookies, verify_jwt_in_request
from models import db, bcrypt, User, SessionMeta, TrackMeta, TrackDayMeta, Follow, Team, TeamMember, TeamInvite, Annotation

# Base directory
import config
OUTPUT_DIR = config.DATA_DIR

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + str(config.DATA_DIR / 'racesense.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'racesense-v2-development-secret-key')
app.config['JWT_TOKEN_LOCATION'] = ['cookies']
app.config['JWT_COOKIE_CSRF_PROTECT'] = False 
app.config['JWT_ACCESS_COOKIE_PATH'] = '/api/'
app.config['JWT_REFRESH_COOKIE_PATH'] = '/api/auth/refresh'
app.config['JWT_COOKIE_HTTPONLY'] = True

db.init_app(app)
bcrypt.init_app(app)
jwt = JWTManager(app)

from functools import wraps

def require_tier(tier):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = get_jwt_identity()
            user = User.query.get(user_id)
            if not user:
                return jsonify({"error": "User not found"}), 404
            
            # Tier hierarchy: team > pro > free
            tier_values = {'free': 0, 'pro': 1, 'team': 2}
            user_tier_val = tier_values.get(user.subscription_tier, 0)
            required_tier_val = tier_values.get(tier, 0)
            
            if user_tier_val < required_tier_val:
                return jsonify({
                    "error": "Upgrade required",
                    "message": f"This feature requires a {tier.capitalize()} subscription.",
                    "required_tier": tier,
                    "current_tier": user.subscription_tier
                }), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.before_request
def protect_api():
    # Only protect /api routes
    if request.path.startswith('/api/'):
        # Allow health, login, register, and status
        public_paths = [
            '/api/health',
            '/api/status',
            '/api/auth/login',
            '/api/auth/register',
            '/api/public/sessions'
        ]
        if request.path in public_paths:
            return
            
        # Also allow shared and public session data
        if request.path.startswith('/api/shared/') or request.path.startswith('/api/public/'):
            return
            
        # Also allow logout (it handles its own JWT if needed, or just clears cookies)
        if request.path == '/api/auth/logout':
            return

        try:
            # For some endpoints, JWT is optional (we handle check inside)
            optional_jwt_paths = [
                '/api/sessions/' # We'll check prefixes
            ]
            
            # If it's a session detail or telemetry request, we'll handle auth inside the function
            if request.path.startswith('/api/sessions/') and (request.path.count('/') >= 4 or request.path.endswith('/telemetry')):
                 # e.g. /api/sessions/<id> or /api/sessions/<id>/telemetry
                 return

            verify_jwt_in_request()
        except Exception:
            return jsonify({"error": "Authentication required"}), 401


import time
import sys
import uuid

# Add core to path for imports
CORE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../core'))
if CORE_PATH not in sys.path:
    sys.path.insert(0, CORE_PATH)

import requests  # Required for device scanning and checking

MIN_ESP_VERSION = "0.0.0"

from update_manager import UpdateManager
FIRMWARE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../firmware'))
update_mgr = UpdateManager(FIRMWARE_DIR)

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

# ============================================================================
# AUTH ENDPOINTS
# ============================================================================

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    name = data.get('name', '')

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 400

    user = User(email=email, name=name)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify({"success": True, "message": "User registered successfully"}), 201

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    # DEV MODE: bypass login if empty
    if not email and not password:
        user = User.query.first() # Get the default admin user
        if not user:
             return jsonify({"error": "No users found"}), 401
    else:
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            return jsonify({"error": "Invalid email or password"}), 401

    access_token = create_access_token(identity=str(user.id))
    response = jsonify({"success": True, "user": user.to_dict()})
    set_access_cookies(response, access_token)
    return response

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    response = jsonify({"success": True})
    unset_jwt_cookies(response)
    return response

@app.route('/api/auth/me', methods=['GET'])
@jwt_required()
def me():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user.to_dict())

@app.route('/api/auth/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()
    if 'name' in data: user.name = data['name']
    if 'bike_info' in data: user.bike_info = data['bike_info']
    if 'home_track' in data: user.home_track = data['home_track']
    
    db.session.commit()
    return jsonify(user.to_dict())

@app.route('/api/sessions/limit', methods=['GET'])
@jwt_required()
def get_session_limit():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    count = SessionMeta.query.filter_by(user_id=user_id).count()
    max_sessions = 5 if user.subscription_tier == 'free' else 999999
    
    return jsonify({
        "used": count,
        "max": max_sessions,
        "tier": user.subscription_tier
    })

@app.route('/api/admin/set-tier', methods=['POST'])
@jwt_required()
def admin_set_tier():
    current_user_id = int(get_jwt_identity())
    current_user = User.query.get(current_user_id)
    
    # Simple admin check: user_id=1 or specific domain
    is_admin = (current_user_id == 1 or (current_user.email and current_user.email.endswith('@racesense.v2')))
    
    if not is_admin:
        return jsonify({"error": "Admin access required"}), 403
        
    data = request.get_json()
    target_user_id = data.get('user_id')
    new_tier = data.get('tier')
    
    if not target_user_id or not new_tier:
        return jsonify({"error": "user_id and tier required"}), 400
        
    if new_tier not in ['free', 'pro', 'team']:
        return jsonify({"error": "Invalid tier"}), 400
        
    target_user = User.query.get(target_user_id)
    if not target_user:
        return jsonify({"error": "Target user not found"}), 404
        
    target_user.subscription_tier = new_tier
    db.session.commit()
    
    return jsonify({
        "success": True, 
        "user_id": target_user_id, 
        "tier": new_tier
    })

# ============================================================================
# SOCIAL / FOLLOW ENDPOINTS
# ============================================================================

@app.route('/api/users/<int:target_user_id>/follow', methods=['POST'])
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

@app.route('/api/users/<int:target_user_id>/follow', methods=['DELETE'])
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

@app.route('/api/users/<int:user_id>/followers', methods=['GET'])
def get_followers(user_id):
    """List followers of a user"""
    follows = Follow.query.filter_by(following_id=user_id).all()
    follower_ids = [f.follower_id for f in follows]
    
    users = User.query.filter(User.id.in_(follower_ids)).all() if follower_ids else []
    return jsonify([u.to_dict() for u in users])

@app.route('/api/users/<int:user_id>/following', methods=['GET'])
def get_following(user_id):
    """List users followed by a user"""
    follows = Follow.query.filter_by(follower_id=user_id).all()
    following_ids = [f.following_id for f in follows]
    
    users = User.query.filter(User.id.in_(following_ids)).all() if following_ids else []
    return jsonify([u.to_dict() for u in users])

@app.route('/api/feed/following', methods=['GET'])
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

@app.route('/api/users/<int:user_id>/social-counts', methods=['GET'])
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

@app.route('/api/users/<int:user_id>/stats', methods=['GET'])
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

@app.route('/api/teams', methods=['POST'])
@jwt_required()
@require_tier('team')
def create_team():
    """Create a new team (Team tier only)"""
    user_id = int(get_jwt_identity())
    data = request.get_json()
    
    name = data.get('name')
    if not name:
        return jsonify({"error": "Team name required"}), 400
        
    team = Team(
        name=name,
        logo_url=data.get('logo_url'),
        owner_id=user_id
    )
    db.session.add(team)
    db.session.flush() # Get team ID
    
    # Add creator as owner member
    member = TeamMember(
        team_id=team.id,
        user_id=user_id,
        role='owner'
    )
    db.session.add(member)
    db.session.commit()
    
    return jsonify(team.to_dict()), 201

@app.route('/api/teams', methods=['GET'])
@jwt_required()
def list_teams():
    """List teams current user belongs to"""
    user_id = int(get_jwt_identity())
    
    memberships = TeamMember.query.filter_by(user_id=user_id).all()
    team_ids = [m.team_id for m in memberships]
    
    teams = Team.query.filter(Team.id.in_(team_ids)).all() if team_ids else []
    
    result = []
    for t in teams:
        team_dict = t.to_dict()
        # Find user's role in this team
        role = next((m.role for m in memberships if m.team_id == t.id), 'rider')
        team_dict['my_role'] = role
        result.append(team_dict)
        
    return jsonify(result)

@app.route('/api/teams/<int:team_id>', methods=['GET'])
@jwt_required()
def get_team_details(team_id):
    """Get team details and members"""
    user_id = int(get_jwt_identity())
    
    # Check if user is a member
    membership = TeamMember.query.filter_by(team_id=team_id, user_id=user_id).first()
    if not membership:
        return jsonify({"error": "Access denied"}), 403
        
    team = Team.query.get(team_id)
    if not team:
        return jsonify({"error": "Team not found"}), 404
        
    # Get all members
    members = db.session.query(
        TeamMember.user_id,
        TeamMember.role,
        TeamMember.joined_at,
        User.name,
        User.email
    ).join(User, TeamMember.user_id == User.id).filter(
        TeamMember.team_id == team_id
    ).all()
    
    team_dict = team.to_dict()
    team_dict['members'] = [
        {
            "user_id": m.user_id,
            "role": m.role,
            "joined_at": m.joined_at.isoformat() if m.joined_at else None,
            "name": m.name,
            "email": m.email
        } for m in members
    ]
    
    return jsonify(team_dict)

@app.route('/api/teams/<int:team_id>', methods=['PUT'])
@jwt_required()
def update_team(team_id):
    """Update team info (owner only)"""
    user_id = int(get_jwt_identity())
    
    team = Team.query.get(team_id)
    if not team:
        return jsonify({"error": "Team not found"}), 404
        
    if team.owner_id != user_id:
        return jsonify({"error": "Only the owner can update team info"}), 403
        
    data = request.get_json()
    if 'name' in data: team.name = data['name']
    if 'logo_url' in data: team.logo_url = data['logo_url']
    
    db.session.commit()
    return jsonify(team.to_dict())

@app.route('/api/teams/<int:team_id>', methods=['DELETE'])
@jwt_required()
def delete_team(team_id):
    """Delete team (owner only)"""
    user_id = int(get_jwt_identity())
    
    team = Team.query.get(team_id)
    if not team:
        return jsonify({"error": "Team not found"}), 404
        
    if team.owner_id != user_id:
        return jsonify({"error": "Only the owner can delete the team"}), 403
        
    # Delete all members and invites first
    TeamMember.query.filter_by(team_id=team_id).delete()
    TeamInvite.query.filter_by(team_id=team_id).delete()
    db.session.delete(team)
    db.session.commit()
    
    return jsonify({"success": True, "message": "Team deleted"})

# ============================================================================
# TEAM INVITE ENDPOINTS
# ============================================================================

@app.route('/api/teams/<int:team_id>/invite', methods=['POST'])
@jwt_required()
def create_team_invite(team_id):
    """Generate invite link (owner/coach only)"""
    user_id = int(get_jwt_identity())
    
    # Check permissions
    membership = TeamMember.query.filter_by(team_id=team_id, user_id=user_id).first()
    if not membership or membership.role not in ['owner', 'coach']:
        return jsonify({"error": "Permission denied"}), 403
        
    import uuid
    from datetime import datetime, timedelta
    
    token = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(days=7)
    
    invite = TeamInvite(
        team_id=team_id,
        token=token,
        expires_at=expires_at
    )
    db.session.add(invite)
    db.session.commit()
    
    return jsonify({
        "token": token,
        "expires_at": expires_at.isoformat(),
        "invite_url": f"/teams/join/{token}"
    })

@app.route('/api/teams/join/<token>', methods=['POST'])
@jwt_required()
def join_team(token):
    """Join a team via invite token"""
    user_id = int(get_jwt_identity())
    
    invite = TeamInvite.query.filter_by(token=token, used=False).first()
    if not invite:
        return jsonify({"error": "Invalid or used invite token"}), 404
        
    if invite.expires_at < datetime.utcnow():
        return jsonify({"error": "Invite token expired"}), 410
        
    # Check if already a member
    existing = TeamMember.query.filter_by(team_id=invite.team_id, user_id=user_id).first()
    if existing:
        return jsonify({"error": "Already a member of this team"}), 400
        
    # Join as rider
    member = TeamMember(
        team_id=invite.team_id,
        user_id=user_id,
        role='rider'
    )
    db.session.add(member)
    
    # Optional: mark invite as used? Or leave it for others? 
    # Usually team invites are reusable until they expire, but let's keep it simple.
    # invite.used = True 
    
    db.session.commit()
    
    team = Team.query.get(invite.team_id)
    return jsonify({"success": True, "team_name": team.name})

@app.route('/api/teams/<int:team_id>/members/<int:target_user_id>', methods=['DELETE'])
@jwt_required()
def remove_team_member(team_id, target_user_id):
    """Remove member or leave team"""
    user_id = int(get_jwt_identity())
    
    # Check permissions
    membership = TeamMember.query.filter_by(team_id=team_id, user_id=user_id).first()
    if not membership:
        return jsonify({"error": "Access denied"}), 403
        
    # If leaving yourself
    if user_id == target_user_id:
        if membership.role == 'owner':
            return jsonify({"error": "Owner cannot leave. Delete the team or transfer ownership first."}), 400
        db.session.delete(membership)
        db.session.commit()
        return jsonify({"success": True, "message": "Left team"})
        
    # If removing someone else
    if membership.role not in ['owner', 'coach']:
        return jsonify({"error": "Permission denied"}), 403
        
    target_membership = TeamMember.query.filter_by(team_id=team_id, user_id=target_user_id).first()
    if not target_membership:
        return jsonify({"error": "Member not found"}), 404
        
    if target_membership.role == 'owner':
        return jsonify({"error": "Cannot remove the owner"}), 403
        
    db.session.delete(target_membership)
    db.session.commit()
    
    return jsonify({"success": True, "message": "Member removed"})

# ============================================================================
# ANNOTATION ENDPOINTS
# ============================================================================

@app.route('/api/sessions/<session_id>/annotations', methods=['POST'])
@jwt_required()
def add_annotation(session_id):
    """Add annotation to a session"""
    user_id = int(get_jwt_identity())
    
    # Check access to session
    s_meta = SessionMeta.query.filter_by(session_id=session_id).first()
    if not s_meta:
        return jsonify({"error": "Session not found"}), 404
        
    # Access check: owner, coach/owner of owner's team, or public
    has_access = False
    if int(s_meta.user_id) == user_id:
        has_access = True
    else:
        # Check if caller is coach/owner of a team the session owner belongs to
        owner_teams = TeamMember.query.filter_by(user_id=s_meta.user_id).all()
        for ot in owner_teams:
            caller_membership = TeamMember.query.filter_by(team_id=ot.team_id, user_id=user_id).first()
            if caller_membership and caller_membership.role in ['owner', 'coach']:
                has_access = True
                break
                
    if not has_access:
        return jsonify({"error": "Access denied"}), 403
        
    data = request.get_json()
    annotation = Annotation(
        session_id=session_id,
        author_id=user_id,
        lap_number=data.get('lap_number'),
        sector_number=data.get('sector_number'),
        text=data.get('text')
    )
    
    if not annotation.text:
        return jsonify({"error": "Annotation text required"}), 400
        
    db.session.add(annotation)
    db.session.commit()
    
    return jsonify(annotation.to_dict()), 201

@app.route('/api/sessions/<session_id>/annotations', methods=['GET'])
def get_annotations(session_id):
    """Get annotations for a session"""
    # Anyone who can view the session can view annotations
    try:
        verify_jwt_in_request(optional=True)
    except:
        pass
    user_id = get_jwt_identity()
    
    s_meta = SessionMeta.query.filter_by(session_id=session_id).first()
    if not s_meta:
        return jsonify({"error": "Session not found"}), 404
        
    # Check access (same logic as get_session)
    has_access = False
    if s_meta.is_public:
        has_access = True
    elif user_id:
        user_id = int(user_id)
        if int(s_meta.user_id) == user_id:
            has_access = True
        else:
            # Team check
            owner_teams = TeamMember.query.filter_by(user_id=s_meta.user_id).all()
            for ot in owner_teams:
                caller_membership = TeamMember.query.filter_by(team_id=ot.team_id, user_id=user_id).first()
                if caller_membership and caller_membership.role in ['owner', 'coach']:
                    has_access = True
                    break
    
    if not has_access:
        return jsonify({"error": "Access denied"}), 403
        
    annotations = Annotation.query.filter_by(session_id=session_id).order_by(Annotation.created_at.asc()).all()
    
    result = []
    for a in annotations:
        a_dict = a.to_dict()
        author = User.query.get(a.author_id)
        a_dict['author_name'] = author.name if author else "Unknown"
        result.append(a_dict)
        
    return jsonify(result)

@app.route('/api/annotations/<int:annotation_id>', methods=['DELETE'])
@jwt_required()
def delete_annotation(annotation_id):
    """Delete own annotation"""
    user_id = int(get_jwt_identity())
    
    annotation = Annotation.query.get(annotation_id)
    if not annotation:
        return jsonify({"error": "Annotation not found"}), 404
        
    if annotation.author_id != user_id:
        return jsonify({"error": "Permission denied"}), 403
        
    db.session.delete(annotation)
    db.session.commit()
    
    return jsonify({"success": True})

# ============================================================================
# LEADERBOARD ENDPOINTS
# ============================================================================

@app.route('/api/leaderboards/track/<int:track_id>')
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

@app.route('/api/leaderboards/trackday/<trackday_id>')
def get_trackday_leaderboard(trackday_id):
    """Get leaderboard for a specific trackday across all participants"""
    # Find the trackday details
    trackdays = load_trackdays()
    td_data = next((td for td in trackdays if td['id'] == trackday_id), None)
    if not td_data:
        return jsonify({"error": "Trackday not found"}), 404
        
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

@app.route('/api/compare', methods=['GET'])
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
        session_file = config.SESSIONS_DIR / f"{session_id}.json"
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
        telemetry_file = config.SESSIONS_DIR / f"{session_id}_telemetry.json"
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
# UTILITY FUNCTIONS
# ============================================================================

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

# ============================================================================
# NETWORK HELPERS
# ============================================================================

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

# ============================================================================
# API ROUTES
# ============================================================================

@app.route('/')
@app.route('/shared/<token>')
@app.route('/community')
def index(token=None):
    """Serve the companion app"""
    return send_file(os.path.join(app.static_folder, 'index.html'))

@app.route('/api/health')
@app.route('/api/status') # Alias for frontend
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "version": "1.0",
        "timestamp": datetime.now().isoformat(),
        "is_recording": False # Mock for now
    })

@app.route('/api/tracks')
@jwt_required()
def get_tracks():
    """Get all tracks for current user"""
    user_id = get_jwt_identity()
    tracks_meta = TrackMeta.query.filter_by(user_id=user_id).all()
    
    tracks = []
    for t in tracks_meta:
        folder = t.folder_name
        session_pattern = f"{folder}_session_"
        sessions_dir = config.SESSIONS_DIR
        
        session_count = 0
        if sessions_dir.exists():
            # Filter sessions by user_id in DB too
            session_count = SessionMeta.query.filter_by(user_id=user_id, track_id=t.track_id).count()
        
        tracks.append({
            "track_id": t.track_id,
            "track_name": t.track_name,
            "folder_name": t.folder_name,
            "sessions_count": session_count
        })
    
    return jsonify({"tracks": tracks})

@app.route('/api/tracks/<int:track_id>')
@jwt_required()
def get_track(track_id):
    """Get track details including TBL"""
    user_id = get_jwt_identity()
    folder = get_track_folder(track_id, user_id=user_id)
    if not folder:
        return jsonify({"error": "Track not found"}), 404
    
    track_dir = config.TRACKS_DIR / folder
    
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

@app.route('/api/tracks/<int:track_id>', methods=['POST'])
@jwt_required()
def update_track(track_id):
    """Update track metadata"""
    user_id = get_jwt_identity()
    folder = get_track_folder(track_id, user_id=user_id)
    if not folder:
        return jsonify({"error": "Track not found"}), 404
    
    track_dir = config.TRACKS_DIR / folder
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

@app.route('/api/tracks/<int:track_id>/map')
@jwt_required()
def get_track_map(track_id):
    """Get track map image"""
    user_id = get_jwt_identity()
    folder = get_track_folder(track_id, user_id=user_id)
    if not folder:
        return jsonify({"error": "Track not found"}), 404
    
    map_file = config.TRACKS_DIR / folder / "track_map.png"
    if not map_file.exists():
        return jsonify({"error": "Map not found"}), 404
    
    return send_file(map_file, mimetype='image/png')

@app.route('/api/sessions')
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

@app.route('/api/sessions/<path:session_id>')
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
        
    sessions_dir = config.SESSIONS_DIR
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

@app.route('/api/sessions/<path:session_id>/telemetry')
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
        
    sessions_dir = config.SESSIONS_DIR
    telemetry_file = sessions_dir / f"{session_id}_telemetry.json"
    
    if telemetry_file.exists():
        return send_file(telemetry_file, mimetype='application/json')
    
    return jsonify({"error": "Telemetry data not found"}), 404

@app.route('/api/sessions/<path:session_id>/privacy', methods=['PUT'])
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

@app.route('/api/sessions/<path:session_id>/share', methods=['POST'])
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

@app.route('/api/shared/<token>')
def get_shared_session(token):
    """Get session data via share token (NO AUTH REQUIRED)"""
    s_meta = SessionMeta.query.filter_by(share_token=token).first()
    
    if not s_meta:
        return jsonify({"error": "Shared session not found"}), 404
        
    # Optional: check expiry if implemented
    if s_meta.share_expires_at and s_meta.share_expires_at < datetime.utcnow():
        return jsonify({"error": "Shared link has expired"}), 410
        
    sessions_dir = config.SESSIONS_DIR
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

@app.route('/api/shared/<token>/telemetry')
def get_shared_telemetry(token):
    """Get telemetry via share token (NO AUTH REQUIRED)"""
    s_meta = SessionMeta.query.filter_by(share_token=token).first()
    
    if not s_meta:
        return jsonify({"error": "Shared session not found"}), 404
        
    sessions_dir = config.SESSIONS_DIR
    telemetry_file = sessions_dir / f"{s_meta.session_id}_telemetry.json"
    
    if telemetry_file.exists():
        return send_file(telemetry_file, mimetype='application/json')
    
    return jsonify({"error": "Telemetry data not found"}), 404

@app.route('/api/public/sessions')
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


@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Receiver for ESP32 raw CSV uploads"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        content = data.get('content')
        
        if not filename or not content:
            return jsonify({"error": "filename and content required"}), 400
            
        safe_name = os.path.basename(filename)
        # Enforce .csv extension for safety
        if not safe_name.lower().endswith('.csv'):
             safe_name += '.csv'
             
        save_path = config.LEARNING_DIR / safe_name
        
        # Determine write mode (append if chunked? No, typical upload is one shot for now)
        # ESP32 sends whole file string.
        
        with open(save_path, 'w') as f:
            f.write(content)
            
        return jsonify({"success": True, "filename": safe_name})
        
    except Exception as e:
        print(f"Upload Error: {e}")
        return jsonify({"error": str(e)}), 500


def register_new_sessions(user_id):
    """Scan sessions directory and register any new sessions to the user"""
    sessions_dir = config.SESSIONS_DIR
    if not sessions_dir.exists():
        return
    
    new_found = False
    for filename in os.listdir(sessions_dir):
        if filename.endswith('.json') and not filename.endswith('_telemetry.json'):
            session_id = filename.replace('.json', '')
            existing = SessionMeta.query.filter_by(session_id=session_id).first()
            if not existing:
                try:
                    with open(sessions_dir / filename, 'r') as f:
                        data = json.load(f)
                        # Ensure track is registered
                        track_id = data.get('track', {}).get('track_id')
                        if track_id:
                            track_meta = TrackMeta.query.filter_by(track_id=track_id).first()
                            if not track_meta:
                                track_meta = TrackMeta(
                                    track_id=track_id,
                                    user_id=user_id,
                                    track_name=data.get('track', {}).get('track_name'),
                                    folder_name=data.get('track', {}).get('folder_name')
                                )
                                db.session.add(track_meta)
                        
                        sm = SessionMeta(
                            session_id=session_id,
                            user_id=user_id,
                            track_id=track_id,
                            session_name=data.get('meta', {}).get('session_name'),
                            start_time=data.get('meta', {}).get('start_time'),
                            duration_sec=data.get('meta', {}).get('duration_sec'),
                            total_laps=data.get('summary', {}).get('total_laps', len(data.get('laps', []))),
                            best_lap_time=data.get('summary', {}).get('best_lap_time')
                        )
                        db.session.add(sm)
                        new_found = True
                except Exception as e:
                    print(f"Failed to auto-register session {filename}: {e}")
    
    if new_found:
        db.session.commit()

@app.route('/api/process', methods=['POST'])
@jwt_required()
def process_session():
    """Process a learning CSV file"""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    # Check session limit for free users
    if user.subscription_tier == 'free':
        count = SessionMeta.query.filter_by(user_id=user_id).count()
        if count >= 5:
            return jsonify({
                "error": "Limit reached",
                "message": "Free tier is limited to 5 processed sessions. Please upgrade to Pro for unlimited storage.",
                "used": count,
                "max": 5
            }), 403

    data = request.get_json()
    filename = data.get('filename') or data.get('csv_file') # support legacy
    
    if not filename:
        return jsonify({"error": "filename required"}), 400
    
    # Sandbox enforcement
    safe_name = os.path.basename(filename)
    csv_path = config.LEARNING_DIR / safe_name
    
    if not csv_path.exists():
        return jsonify({"error": "File not found"}), 404
    
    # Run analysis script
    try:
        # Locate script in our core folder
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../core/run_analysis.py'))
        
        result = subprocess.run([
            'python3', script_path, str(csv_path)
        ], capture_output=True, text=True, timeout=60)

        
        if result.returncode == 0:
            register_new_sessions(user_id)
            return jsonify({
                "status": "complete",
                "message": "Session processed successfully",
                "output": result.stdout
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Processing failed",
                "error": result.stderr
            }), 500
    
    except subprocess.TimeoutExpired:
        return jsonify({
            "status": "error",
            "message": "Processing timeout"
        }), 500
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/api/sync/device', methods=['POST'])
def sync_device():
    """Pull CSV files from ESP32 Device"""
    import requests
    data = request.get_json() or {}
    device_ip = data.get('ip', '192.168.4.1') # Default to AP IP
    
    # 1. Get List
    try:
        print(f"Syncing from {device_ip}...")
        resp = requests.get(f"http://{device_ip}/list", timeout=10)
        if resp.status_code != 200:
            return jsonify({"error": f"Device Error: {resp.status_code}"}), 400
            
        files = resp.json().get('files', [])
    except Exception as e:
        return jsonify({"error": f"Failed to connect to device: {e}"}), 500

    synced = []
    failed = []
    
    # 2. Download Each
    for fname in files:
        try:
            print(f"Downloading {fname}...")
            r = requests.get(f"http://{device_ip}/download/{fname}", stream=True, timeout=10)
            if r.status_code == 200:
                save_path = config.LEARNING_DIR / fname
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024):
                        if chunk: f.write(chunk)
                        
                synced.append(fname)
                
                # 3. Delete from Device (Move from ESP to Pi)
                try:
                    time.sleep(0.2) # Small breather for ESP32
                    del_resp = requests.get(f"http://{device_ip}/delete/{fname}", timeout=5)
                    if del_resp.status_code == 200:
                        print(f"[Sync] Successfully deleted {fname} from ESP32")
                    else:
                        print(f"[Sync] Failed to delete {fname} from ESP32: {del_resp.status_code}")
                except Exception as de:
                    print(f"[Sync] Error deleting {fname} from ESP32: {de}")
            else:
                failed.append(fname)
        except Exception as e:
            print(f"Error downloading {fname}: {e}")
            failed.append(fname)
            
    return jsonify({
        "success": True,
        "synced": synced,
        "failed": failed,
        "device_ip": device_ip
    })
def rename_track(track_id):
    """Rename a track"""
    data = request.get_json()
    new_name = data.get('new_name')
    
    if not new_name:
        return jsonify({"error": "new_name required"}), 400
    
    # Run rename script
    try:
        # Use echo to auto-confirm
        result = subprocess.run([
            'python3', 'scripts/rename_track.py',
            '--track_id', str(track_id),
            '--new_name', new_name
        ], capture_output=True, text=True, input='y\n', cwd=BASE_DIR, timeout=10)
        
        if result.returncode == 0:
            return jsonify({
                "success": True,
                "message": f"Renamed to {new_name}"
            })
        else:
            return jsonify({
                "success": False,
                "error": result.stderr
            }), 400
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# ============================================================================
# FILE MANAGEMENT
# ============================================================================
from file_manager import FileManager
file_mgr = FileManager(base_dir=config.LEARNING_DIR)

@app.route('/api/learning/list')
def list_learning_files():
    """List learning CSV files with metadata"""
    archived = request.args.get('archived', 'false').lower() == 'true'
    return jsonify(file_mgr.get_files(archived=archived))

@app.route('/api/learning/<filename>/lock', methods=['POST'])
def lock_learning_file(filename):
    data = request.json
    locked = data.get('locked', True)
    if file_mgr.set_lock(filename, locked):
        return jsonify({"success": True, "locked": locked})
    return jsonify({"error": "Failed to update lock"}), 500

@app.route('/api/learning/delete', methods=['POST'])
def delete_learning_files():
    """Permanent Bulk Delete"""
    data = request.json
    filenames = data.get('files', [])
    from_archive = data.get('from_archive', False)
    if not filenames:
        return jsonify({"error": "No files specified"}), 400
        
    result = file_mgr.delete_files(filenames, from_archive=from_archive)
    return jsonify(result)

@app.route('/api/learning/archive', methods=['POST'])
def archive_learning_files():
    """Soft delete - Move to archive"""
    data = request.json
    filenames = data.get('files', [])
    if not filenames:
        return jsonify({"error": "No files specified"}), 400
        
    result = file_mgr.archive_files(filenames)
    return jsonify(result)

@app.route('/api/learning/restore', methods=['POST'])
def restore_learning_files():
    """Restore from archive"""
    data = request.json
    filenames = data.get('files', [])
    if not filenames:
        return jsonify({"error": "No files specified"}), 400
        
    result = file_mgr.restore_files(filenames)
    return jsonify(result)

@app.route('/api/learning/<filename>/raw')
def get_learning_file_raw(filename):
    """Get raw head of file"""
    lines = request.args.get('lines', 100, type=int)
    return jsonify(file_mgr.read_file_head(filename, lines))

@app.route('/api/learning/<filename>/geo')
def get_learning_file_geo(filename):
    """Get Geo Path for Visualization"""
    return jsonify(file_mgr.extract_geo_path(filename))

@app.route('/api/device/configure', methods=['POST'])
def configure_device():
    """Configure ESP32 WiFi (Proxy)"""
    import requests
    data = request.get_json()
    device_ip = data.get('ip', '192.168.4.1')
    ssid = data.get('ssid')
    password = data.get('password')
    
    if not ssid or not password:
        return jsonify({"error": "Missing ssid or password"}), 400
        
    try:
        # Send to ESP32
        print(f"Configuring device at {device_ip}...")
        resp = requests.post(
            f"http://{device_ip}/wifi/add", 
            json={"ssid": ssid, "password": password},
            timeout=5
        )
        
        if resp.status_code == 200:
             return jsonify({"success": True, "message": "Configuration sent. Device rebooting..."})
        else:
             return jsonify({"error": f"Device rejected config: {resp.status_code}"}), 400
             
    except Exception as e:
        return jsonify({"error": f"Failed to connect to device: {e}"}), 500

@app.route('/api/device/scan', methods=['GET'])
def scan_devices():
    """Scan local network for ESP32 Datalogger"""
    import threading
    from queue import Queue
    
    # Accept optional subnet parameter
    custom_subnet = request.args.get('subnet', None)
    
    # 1. Detect Subnets to scan
    subnets_to_scan = []
    
    if custom_subnet:
        subnets_to_scan.append(custom_subnet if custom_subnet.endswith('.') else custom_subnet + '.')
    else:
        # Auto-detect local subnet
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            subnets_to_scan.append(".".join(local_ip.split('.')[:3]) + ".")
        except:
            subnets_to_scan.append("192.168.1.")
        
        # Also check ESP32 default AP subnet
        if "192.168.4." not in subnets_to_scan:
            subnets_to_scan.append("192.168.4.")
    
    print(f"[Scanner] Scanning subnets: {subnets_to_scan}")

    found_devices = []
    print_lock = threading.Lock()
    
    # helper to run a batch of IPs
    def run_batch(ips):
        q = Queue()
        for ip in ips:
            q.put(ip)
            
        def threader():
            while True:
                try:
                    ip = q.get_nowait()
                except:
                    # Queue is empty
                    break
                    
                try:
                    # Check IP
                    data = robust_get_json(f"http://{ip}/status", timeout=2.0)
                    if data and "storage" in data:
                        with print_lock:
                            v = data.get('version', '0.0.0')
                            info = {
                                "ip": ip, 
                                "info": data,
                                "compatible": is_compatible(v),
                                "min_required": MIN_ESP_VERSION
                            }
                            print(f"Found device at {ip}: {info}")
                            found_devices.append(info)
                except Exception:
                    # Ignore errors checking IP
                    pass
                finally:
                    q.task_done()

        threads = []
        # Adjust thread count based on batch size
        count = min(50, len(ips))
        for _ in range(count):
            t = threading.Thread(target=threader)
            t.daemon = True
            t.start()
            threads.append(t)
        
        q.join()

    # --- PHASE 1: Priority Scan (ARP + Hostnames) ---
    priority_ips = set()
    try:
        # Get ARP table (use -n to avoid slow DNS lookups)
        arp_out = subprocess.check_output(['arp', '-an'], text=True)
        import re
        for line in arp_out.splitlines():
            # Extract IP from format "? (192.168.1.41) at ..."
            match = re.search(r'\(([\d\.]+)\)', line)
            if match:
                ip = match.group(1)
                if any(ip.startswith(s) for s in subnets_to_scan):
                    priority_ips.add(ip)
    except:
        pass

    priority_ips.add("datalogger.local")
    priority_ips.add("datalogger")
    
    print(f"[Scanner] Phase 1: Checking {len(priority_ips)} priority targets...")
    run_batch(list(priority_ips))
    
    # If found, return early!
    if found_devices:
        print(f"Scan complete (Fast). Found {len(found_devices)} devices")
        return jsonify({"devices": found_devices, "subnets_scanned": subnets_to_scan})

    # --- PHASE 2: Subnet Brute Force ---
    print("[Scanner] Phase 2: Brute force subnets...")
    subnet_ips = []
    for subnet in subnets_to_scan:
        for i in range(1, 255):
            ip = f"{subnet}{i}"
            if ip not in priority_ips:
                subnet_ips.append(ip)
    
    run_batch(subnet_ips)
    
    print(f"Scan complete. Found {len(found_devices)} devices: {[d['ip'] for d in found_devices]}")
    return jsonify({"devices": found_devices, "subnets_scanned": subnets_to_scan})

@app.route('/api/device/check', methods=['GET'])
def check_device():
    """Check if specific device IP is reachable"""
    ip = request.args.get('ip')
    if not ip:
        print("[Check] No IP provided")
        return jsonify({"reachable": False})
    
    try:
        print(f"[Check] Testing {ip}...")
        r = requests.get(f"http://{ip}/status", timeout=5)
        print(f"[Check] Response: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"[Check] Data: {data}")
            v = data.get('version', '0.0.0')
            return jsonify({
                "reachable": True, 
                "info": data,
                "compatible": is_compatible(v),
                "min_required": MIN_ESP_VERSION
            })
        else:
            print(f"[Check] Non-200 status: {r.status_code}")
            return jsonify({"reachable": False})
    except Exception as e:
        print(f"[Check] Exception: {type(e).__name__}: {e}")
        return jsonify({"reachable": False})

@app.route('/api/device/version-check', methods=['GET'])
def device_version_check():
    """Detailed version comparison for a specific device"""
    ip = request.args.get('ip')
    if not ip:
        return jsonify({"error": "No IP provided"}), 400
        
    local_v = get_local_firmware_version()
    
    try:
        r = requests.get(f"http://{ip}/status", timeout=5)
        if r.status_code == 200:
            data = r.json()
            device_v = data.get('version', '0.0.0')
            return jsonify({
                "device_version": device_v,
                "server_version": local_v,
                "update_available": device_v != local_v,
                "is_compatible": is_compatible(device_v)
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/device/update-ota', methods=['POST'])
def device_update_ota():
    """Trigger WiFi OTA update for a device"""
    data = request.get_json()
    ip = data.get('ip')
    if not ip:
        return jsonify({"error": "No IP provided"}), 400
        
    print(f"[OTA] Starting update for {ip}...")
    result = update_mgr.push_update(ip)
    print(f"[OTA] Result: {result}")
    
    return jsonify(result)

@app.route('/api/learning/processed')
def get_processed_files():
    """Returns set of source filenames that have already been processed into sessions."""
    processed = set()
    sessions_dir = config.SESSIONS_DIR
    
    if sessions_dir.exists():
        for filename in os.listdir(sessions_dir):
            if filename.endswith('.json') and not filename.endswith('_telemetry.json'):
                try:
                    with open(sessions_dir / filename, 'r') as f:
                        data = json.load(f)
                        source_file = data.get('meta', {}).get('source_file')
                        if source_file:
                            processed.add(source_file)
                except Exception:
                    continue
    
    return jsonify(list(processed))

@app.route('/api/process/all', methods=['POST'])
@jwt_required()
def process_all_files():
    """Process all unprocessed learning files, or specific files if provided."""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    
    # Get already processed files for this user
    processed_count = SessionMeta.query.filter_by(user_id=user_id).count()
    
    # Check if specific files were requested
    data = request.get_json() or {}
    requested_files = data.get('files', None)  # Optional list of specific files
    
    # Get list of learning files
    files = file_mgr.get_files()
    to_process = requested_files if requested_files else [f['filename'] for f in files]

    # Limit check for free tier
    if user.subscription_tier == 'free':
        if processed_count >= 5:
             return jsonify({
                "error": "Limit reached",
                "message": "Free tier is limited to 5 processed sessions. Please upgrade to Pro for unlimited storage.",
                "used": processed_count,
                "max": 5
            }), 403
        
        # Only process up to the limit
        remaining = 5 - processed_count
        if len(to_process) > remaining:
            to_process = to_process[:remaining]
            # We'll continue but notify user? Or just process what we can?
            # For now, just process what we can.
    
    results = {"success": [], "failed": []}
    
    for filename in to_process:
        csv_path = config.LEARNING_DIR / filename
        try:
            script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../core/run_analysis.py'))
            result = subprocess.run([
                'python3', script_path, str(csv_path)
            ], capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                results["success"].append(filename)
            else:
                results["failed"].append({"filename": filename, "error": result.stderr[:200]})
        except Exception as e:
            results["failed"].append({"filename": filename, "error": str(e)})
    
    if results["success"]:
        register_new_sessions(user_id)
        
    return jsonify({
        "status": "complete",
        "message": f"Processed {len(results['success'])} files",
        "processed": len(results["success"]),
        "failed": len(results["failed"]),
        "details": results
    })

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error"}), 500

@app.route('/api/tracks/<int:track_id>/geometry')
@jwt_required()
def get_track_geometry(track_id):
    """Serve the geometry.json file for a track."""
    user_id = get_jwt_identity()
    folder_name = get_track_folder(track_id, user_id=user_id)
    if not folder_name:
         return jsonify({"error": "Track not found"}), 404
         
    geo_path = OUTPUT_DIR / "tracks" / folder_name / "geometry.json"
    if geo_path.exists():
        return send_file(geo_path)
    
    return jsonify({"error": "Geometry not found. Please regenerate track."}), 404
@app.route('/api/sessions/<session_id>', methods=['DELETE'])
@jwt_required()
def delete_session_endpoint(session_id):
    """Delete a processed session"""
    user_id = get_jwt_identity()
    try:
        # Check ownership
        s_meta = SessionMeta.query.filter_by(session_id=session_id, user_id=user_id).first()
        if not s_meta:
            return jsonify({"error": "Session not found or access denied"}), 404
            
        s_path = config.SESSIONS_DIR / f"{session_id}.json"
        t_path = config.SESSIONS_DIR / f"{session_id}_telemetry.json"
        
        if s_path.exists(): os.remove(s_path)
        if t_path.exists(): os.remove(t_path)
        
        db.session.delete(s_meta)
        db.session.commit()
        return jsonify({"success": True, "message": f"Deleted {session_id}"})
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/tracks/<int:track_id>', methods=['DELETE'])
@jwt_required()
def delete_track_endpoint(track_id):
    """Delete a track, its folder, and all associated sessions."""
    user_id = get_jwt_identity()
    try:
        from src.core.registry_manager import RegistryManager
        import time
        import stat
        
        # Check ownership
        track_meta = TrackMeta.query.filter_by(track_id=track_id, user_id=user_id).first()
        if not track_meta:
            return jsonify({"error": "Track not found or access denied"}), 404
            
        registry = RegistryManager()
        
        track = registry.get_track_by_id(track_id)
        # If not in registry but in DB, we should still clean up DB
        folder_name = track_meta.folder_name
        print(f"[API] Deleting track {track_id} ({folder_name}) for user {user_id}...")
        
        # 1. Delete associated processed sessions for THIS user only
        sessions_to_delete = SessionMeta.query.filter_by(track_id=track_id, user_id=user_id).all()
        
        deleted_sessions = 0
        for s in sessions_to_delete:
            s_file = OUTPUT_DIR / "sessions" / f"{s.session_id}.json"
            t_file = OUTPUT_DIR / "sessions" / f"{s.session_id}_telemetry.json"
            try:
                if s_file.exists(): os.remove(s_file)
                if t_file.exists(): os.remove(t_file)
                db.session.delete(s)
                deleted_sessions += 1
            except Exception as e:
                print(f"Failed to delete session {s.session_id}: {e}")
        
        # 2. Delete Track Folder ONLY if no other users are using it
        # (Though in Phase 1, each user has their own folders)
        other_users = TrackMeta.query.filter(TrackMeta.track_id == track_id, TrackMeta.user_id != user_id).count()
        
        if other_users == 0:
            track_dir = OUTPUT_DIR / "tracks" / folder_name
            def on_rm_error(func, path, exc_info):
                os.chmod(path, stat.S_IWRITE)
                try: func(path)
                except: pass

            if track_dir.exists():
                for i in range(3):
                    try:
                        shutil.rmtree(track_dir, onerror=on_rm_error)
                        break
                    except Exception:
                        time.sleep(0.5)
            
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

@app.route('/api/learning/rename', methods=['POST'])
def rename_learning_file():
    """Rename raw CSV file (safely)"""
    try:
        data = request.json
        old_name = data.get('old_name')
        new_name = data.get('new_name')
        
        if not old_name or not new_name:
            return jsonify({"error": "Missing parameters"}), 400
            
        old_name = os.path.basename(old_name)
        new_name = os.path.basename(new_name)
        
        # Prevent extension change? Or enforce .csv?
        if not new_name.lower().endswith('.csv'):
            new_name += '.csv'
            
        src = OUTPUT_DIR / "learning" / old_name
        dst = OUTPUT_DIR / "learning" / new_name
        
        if not src.exists():
            return jsonify({"error": "Source file not found"}), 404
            
        if dst.exists():
            return jsonify({"error": "A file with that name already exists"}), 400
            
        os.rename(src, dst)
        return jsonify({"success": True, "new_name": new_name})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions/<session_id>/rename', methods=['POST'])
def rename_session(session_id):
    """Rename a session (updates meta.session_name)"""
    data = request.get_json()
    new_name = data.get('new_name')
    if not new_name:
        return jsonify({"error": "new_name required"}), 400

    sessions_dir = OUTPUT_DIR / "sessions"
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

@app.route('/api/sessions/<session_id>/notes', methods=['PUT'])
def update_session_notes(session_id):
    """Update session notes"""
    data = request.get_json()
    notes = data.get('notes', '')
    
    sessions_dir = OUTPUT_DIR / "sessions"
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
            
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Failed to save notes: {e}")
        return jsonify({"error": "Failed to save notes"}), 500

@app.route('/api/sessions/<session_id>/export')
@jwt_required()
@require_tier('pro')
def export_session(session_id):
    """
    Export session data as a ZIP file.
    Includes: session.json and _telemetry.json (if present)
    """
    import zipfile
    import io
    
    # 1. Locate Files
    sessions_dir = OUTPUT_DIR / "sessions"
    
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

def load_trackdays():
    """Load trackdays.json or return empty list"""
    trackdays_file = OUTPUT_DIR / "trackdays.json"
    if trackdays_file.exists():
        with open(trackdays_file, 'r') as f:
            return json.load(f)
    return []

def save_trackdays(trackdays):
    """Save trackdays to JSON file"""
    trackdays_file = OUTPUT_DIR / "trackdays.json"
    with open(trackdays_file, 'w') as f:
        json.dump(trackdays, f, indent=2)

@app.route('/api/trackdays', methods=['GET'])
@jwt_required()
def get_trackdays():
    """Get all trackdays for current user with summary info"""
    user_id = get_jwt_identity()
    trackdays_meta = TrackDayMeta.query.filter_by(user_id=user_id).all()
    
    # We still need to load the session data for counts, or store it in DB
    # For now, let's just use the trackdays.json for the details, but filtered by DB
    trackdays_list = load_trackdays() # This loads ALL trackdays from file
    
    # Filter by IDs found in DB for this user
    user_td_ids = [td.trackday_id for td in trackdays_meta]
    user_trackdays = [td for td in trackdays_list if td['id'] in user_td_ids]
    
    # Enrich with session counts and quick stats
    for td in user_trackdays:
        sessions = td.get('session_ids', [])
        td['session_count'] = len(sessions)
        
        # Calculate aggregate stats
        total_laps = 0
        best_lap = None
        
        for sid in sessions:
            try:
                session_path = OUTPUT_DIR / "sessions" / f"{sid}.json"
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

@app.route('/api/trackdays', methods=['POST'])
@jwt_required()
def create_trackday():
    """Create a new trackday"""
    user_id = get_jwt_identity()
    data = request.get_json()
    
    trackdays = load_trackdays()
    
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
    save_trackdays(trackdays)
    
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

@app.route('/api/trackdays/<trackday_id>', methods=['GET'])
@jwt_required()
def get_trackday(trackday_id):
    """Get full trackday details with aggregated data from all sessions"""
    user_id = get_jwt_identity()
    # Check ownership
    td_meta = TrackDayMeta.query.filter_by(trackday_id=trackday_id, user_id=user_id).first()
    if not td_meta:
        return jsonify({"error": "Trackday not found or access denied"}), 404

    trackdays = load_trackdays()
    trackday = next((td for td in trackdays if td['id'] == trackday_id), None)
    if not trackday:
        return jsonify({"error": "Trackday data not found"}), 404
    
    # Aggregate all sessions
    all_laps = []
    all_sector_times = []
    total_duration = 0
    best_lap_time = None
    sessions_data = []
    sector_count = 0
    
    for sid in trackday.get('session_ids', []):
        try:
            session_path = OUTPUT_DIR / "sessions" / f"{sid}.json"
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
            logger.error(f"Error loading session {sid}: {e}")
    
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

@app.route('/api/trackdays/<trackday_id>', methods=['PUT'])
@jwt_required()
def update_trackday(trackday_id):
    """Update trackday details"""
    user_id = get_jwt_identity()
    # Check ownership
    td_meta = TrackDayMeta.query.filter_by(trackday_id=trackday_id, user_id=user_id).first()
    if not td_meta:
        return jsonify({"error": "Trackday not found or access denied"}), 404

    data = request.get_json()
    trackdays = load_trackdays()
    
    for td in trackdays:
        if td['id'] == trackday_id:
            td['name'] = data.get('name', td['name'])
            td['date'] = data.get('date', td['date'])
            td['organizer'] = data.get('organizer', td['organizer'])
            td['rider_name'] = data.get('rider_name', td.get('rider_name', ''))
            td['notes'] = data.get('notes', td['notes'])
            save_trackdays(trackdays)
            
            # Update DB meta too
            td_meta.name = td['name']
            td_meta.date = td['date']
            db.session.commit()
            
            return jsonify(td)
    
    return jsonify({"error": "Trackday data not found"}), 404

@app.route('/api/trackdays/<trackday_id>', methods=['DELETE'])
@jwt_required()
def delete_trackday(trackday_id):
    """Delete a trackday (does not delete sessions)"""
    user_id = get_jwt_identity()
    # Check ownership
    td_meta = TrackDayMeta.query.filter_by(trackday_id=trackday_id, user_id=user_id).first()
    if not td_meta:
        return jsonify({"error": "Trackday not found or access denied"}), 404

    trackdays = load_trackdays()
    trackdays = [td for td in trackdays if td['id'] != trackday_id]
    save_trackdays(trackdays)
    
    # Remove from DB
    db.session.delete(td_meta)
    db.session.commit()
    
    return jsonify({"success": True})

@app.route('/api/trackdays/<trackday_id>/sessions/<session_id>', methods=['POST'])
@jwt_required()
def tag_session_to_trackday(trackday_id, session_id):
    """Add a session to a trackday"""
    user_id = get_jwt_identity()
    # Check ownership of both trackday and session
    td_meta = TrackDayMeta.query.filter_by(trackday_id=trackday_id, user_id=user_id).first()
    s_meta = SessionMeta.query.filter_by(session_id=session_id, user_id=user_id).first()
    
    if not td_meta or not s_meta:
        return jsonify({"error": "Trackday or session not found or access denied"}), 404

    trackdays = load_trackdays()
    for td in trackdays:
        if td['id'] == trackday_id:
            if 'session_ids' not in td:
                td['session_ids'] = []
            if session_id not in td['session_ids']:
                td['session_ids'].append(session_id)
                save_trackdays(trackdays)
            return jsonify({"success": True, "session_ids": td['session_ids']})
    
    return jsonify({"error": "Trackday data not found"}), 404

@app.route('/api/trackdays/<trackday_id>/sessions/<session_id>', methods=['DELETE'])
@jwt_required()
def untag_session_from_trackday(trackday_id, session_id):
    """Remove a session from a trackday"""
    user_id = get_jwt_identity()
    # Check ownership
    td_meta = TrackDayMeta.query.filter_by(trackday_id=trackday_id, user_id=user_id).first()
    if not td_meta:
        return jsonify({"error": "Trackday not found or access denied"}), 404

    trackdays = load_trackdays()
    for td in trackdays:
        if td['id'] == trackday_id:
            if session_id in td.get('session_ids', []):
                td['session_ids'].remove(session_id)
                save_trackdays(trackdays)
            return jsonify({"success": True, "session_ids": td.get('session_ids', [])})
    
    return jsonify({"error": "Trackday data not found"}), 404











# ============================================================================
# CLOUD / API SERVER ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    # Development mode
    print("=" * 60)
    print("Datalogger Cloud API Server")
    print("=" * 60)
    print(f"Output directory: {OUTPUT_DIR}")
    print()
    print("Starting server on http://localhost:5000")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5001, debug=False)
