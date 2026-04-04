from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import shutil

from api.models import db, User, SessionMeta, TrackMeta, Team, TeamMember, GlobalTrack, UnmatchedTrackReport
from api.decorators import admin_required
from api.track_catalog import TrackPackageError, upsert_global_track_package
import api.config as config

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

@admin_bp.route('/users', methods=['GET'])
@admin_required
def admin_list_users():
    """
    List all users with tier, session count, and stats.
    Query params: 
      - q: search query (email/name)
      - tier: filter by tier (free/pro/team)
      - approval: filter by approval status (pending/approved)
      - page: pagination (default 1)
      - per_page: items per page (default 50)
    """
    q = request.args.get('q', '').strip()
    tier_filter = request.args.get('tier', '').strip()
    approval_filter = request.args.get('approval', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    query = User.query
    
    # Search filter
    if q:
        search = f"%{q}%"
        query = query.filter(
            db.or_(
                User.email.ilike(search),
                User.name.ilike(search)
            )
        )
    
    # Tier filter
    if tier_filter and tier_filter in ['free', 'pro', 'team']:
        query = query.filter(User.subscription_tier == tier_filter)
    
    # Approval filter
    if approval_filter == 'pending':
        query = query.filter(User.is_approved == False)
    elif approval_filter == 'approved':
        query = query.filter(User.is_approved == True)
    
    # Order by created_at desc
    query = query.order_by(User.created_at.desc())
    
    # Pagination
    total = query.count()
    users = query.offset((page - 1) * per_page).limit(per_page).all()
    
    # Counts for stats
    pending_count = User.query.filter(User.is_approved == False).count()
    approved_count = User.query.filter(User.is_approved == True).count()
    
    # Enrich with session counts
    result = []
    for user in users:
        session_count = SessionMeta.query.filter_by(user_id=user.id).count()
        user_dict = user.to_dict()
        user_dict['session_count'] = session_count
        result.append(user_dict)
    
    return jsonify({
        "users": result,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "pending_count": pending_count,
        "approved_count": approved_count
    })

@admin_bp.route('/users/<int:user_id>/approve', methods=['PUT'])
@admin_required
def admin_approve_user(user_id):
    """Approve or reject a user's account"""
    target_user = User.query.get(user_id)
    if not target_user:
        return jsonify({"error": "User not found"}), 404
    
    data = request.get_json()
    approved = data.get('approved', True)
    
    target_user.is_approved = bool(approved)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "user_id": user_id,
        "is_approved": target_user.is_approved,
        "user": target_user.to_dict()
    })

@admin_bp.route('/users/<int:user_id>/tier', methods=['PUT'])
@admin_required
def admin_update_user_tier(user_id):
    """
    Update a user's subscription tier.
    Body: { "tier": "free" | "pro" | "team" }
    """
    target_user = User.query.get(user_id)
    if not target_user:
        return jsonify({"error": "User not found"}), 404
    
    data = request.get_json()
    new_tier = data.get('tier')
    
    if new_tier not in ['free', 'pro', 'team']:
        return jsonify({"error": "Invalid tier. Must be 'free', 'pro', or 'team'"}), 400
    
    old_tier = target_user.subscription_tier
    target_user.subscription_tier = new_tier
    
    # Clear expiry for manual upgrades (no auto-expiry)
    target_user.subscription_expires_at = None
    
    db.session.commit()
    
    return jsonify({
        "success": True,
        "user_id": user_id,
        "old_tier": old_tier,
        "new_tier": new_tier,
        "user": target_user.to_dict()
    })

@admin_bp.route('/users/<int:user_id>', methods=['GET'])
@admin_required
def admin_get_user(user_id):
    """Get detailed user info for admin view"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    # Get stats
    session_count = SessionMeta.query.filter_by(user_id=user_id).count()
    track_count = TrackMeta.query.filter_by(user_id=user_id).count()
    
    # Team memberships
    memberships = TeamMember.query.filter_by(user_id=user_id).all()
    teams = []
    for m in memberships:
        team = Team.query.get(m.team_id)
        if team:
            teams.append({
                "team_id": team.id,
                "team_name": team.name,
                "role": m.role
            })
    
    user_dict = user.to_dict()
    user_dict['stats'] = {
        "session_count": session_count,
        "track_count": track_count,
        "team_count": len(teams)
    }
    user_dict['teams'] = teams
    
    return jsonify(user_dict)

@admin_bp.route('/users/<int:user_id>/admin', methods=['PUT'])
@admin_required
def admin_toggle_admin(user_id):
    """
    Toggle admin status for a user.
    Only user_id=1 (super admin) can do this.
    Body: { "is_admin": true | false }
    """
    current_user_id = int(get_jwt_identity())
    
    # Only super admin (id=1) can grant/revoke admin
    if current_user_id != 1:
        return jsonify({"error": "Only the super admin can modify admin privileges"}), 403
    
    # Cannot demote yourself
    if user_id == 1:
        return jsonify({"error": "Cannot modify super admin privileges"}), 403
    
    target_user = User.query.get(user_id)
    if not target_user:
        return jsonify({"error": "User not found"}), 404
    
    data = request.get_json()
    is_admin = data.get('is_admin', False)
    
    target_user.is_admin = bool(is_admin)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "user_id": user_id,
        "is_admin": target_user.is_admin
    })

@admin_bp.route('/set-tier', methods=['POST'])
@admin_required
def admin_set_tier_deprecated():
    """DEPRECATED: Use PUT /api/admin/users/<id>/tier instead"""
    data = request.get_json()
    target_user_id = data.get('user_id')
    new_tier = data.get('tier')
    
    # Delegate to new endpoint logic
    if not target_user_id or not new_tier:
        return jsonify({"error": "user_id and tier required"}), 400
    
    target_user = User.query.get(target_user_id)
    if not target_user:
        return jsonify({"error": "Target user not found"}), 404
    
    if new_tier not in ['free', 'pro', 'team']:
        return jsonify({"error": "Invalid tier"}), 400
    
    target_user.subscription_tier = new_tier
    db.session.commit()
    
    return jsonify({
        "success": True, 
        "user_id": target_user_id, 
        "tier": new_tier,
        "_deprecated": "Use PUT /api/admin/users/<id>/tier instead"
    })

@admin_bp.route('/tracks', methods=['GET'])
@admin_required
def admin_list_tracks():
    tracks = GlobalTrack.query.order_by(GlobalTrack.track_name.asc()).all()
    payload = []
    for track in tracks:
        item = track.to_dict()
        item["matched_sessions_count"] = SessionMeta.query.filter_by(track_id=track.track_id).count()
        payload.append(item)
    return jsonify({"tracks": payload})

@admin_bp.route('/tracks/package', methods=['POST'])
@admin_required
def admin_upload_track_package():
    data = request.get_json() or {}
    package = data.get('package') if 'package' in data else data
    track_name = data.get('track_name') or data.get('name')
    slug = data.get('slug')
    track_id = data.get('track_id')

    try:
        global_track = upsert_global_track_package(track_name=track_name, package=package, slug=slug, track_id=track_id)
        return jsonify({
            "success": True,
            "track": global_track.to_dict()
        })
    except TrackPackageError as exc:
        return jsonify({"error": str(exc)}), 400

@admin_bp.route('/tracks/unmatched', methods=['GET'])
@admin_required
def admin_list_unmatched_tracks():
    reports = UnmatchedTrackReport.query.order_by(UnmatchedTrackReport.created_at.desc()).all()
    return jsonify({"reports": [report.to_dict() for report in reports]})

@admin_bp.route('/tracks/unmatched/<int:report_id>/resolve', methods=['POST'])
@admin_required
def admin_resolve_unmatched_track(report_id):
    report = UnmatchedTrackReport.query.get(report_id)
    if not report:
        return jsonify({"error": "Report not found"}), 404

    data = request.get_json() or {}
    status = data.get('status', 'resolved')
    if status not in {'resolved', 'ignored', 'open'}:
        return jsonify({"error": "Invalid status"}), 400

    global_track_id = data.get('global_track_id')
    if status == 'resolved':
        if not global_track_id:
            return jsonify({"error": "global_track_id is required when resolving"}), 400
        global_track = GlobalTrack.query.filter_by(track_id=int(global_track_id)).first()
        if not global_track:
            return jsonify({"error": "Global track not found"}), 404
        report.resolved_global_track_id = global_track.track_id
    else:
        report.resolved_global_track_id = None

    report.status = status
    db.session.commit()
    return jsonify({"success": True, "report": report.to_dict()})

@admin_bp.route('/tracks/<int:track_id>', methods=['DELETE'])
@admin_required
def admin_delete_track(track_id):
    global_track = GlobalTrack.query.filter_by(track_id=track_id).first()
    if not global_track:
        return jsonify({"error": "Global track not found"}), 404

    matched_sessions = SessionMeta.query.filter_by(track_id=track_id).count()
    if matched_sessions > 0:
        return jsonify({
            "error": "Track cannot be deleted while matched sessions exist",
            "matched_sessions_count": matched_sessions
        }), 409

    track_dir = config.get_global_track_dir(global_track.folder_name)
    if track_dir.exists():
        shutil.rmtree(track_dir, ignore_errors=True)

    UnmatchedTrackReport.query.filter_by(resolved_global_track_id=track_id).update({"resolved_global_track_id": None})
    User.query.filter_by(active_track_id=track_id).update({"active_track_id": None})
    db.session.delete(global_track)
    db.session.commit()
    return jsonify({"success": True, "track_id": track_id})
