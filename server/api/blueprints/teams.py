from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime, timedelta
import os

from api.models import db, User, Team, TeamMember, TeamInvite
from api.decorators import require_tier

teams_bp = Blueprint('teams', __name__)

@teams_bp.route('/api/teams', methods=['POST'])
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

@teams_bp.route('/api/teams', methods=['GET'])
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

@teams_bp.route('/api/teams/<int:team_id>', methods=['GET'])
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

@teams_bp.route('/api/teams/<int:team_id>', methods=['PUT'])
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

@teams_bp.route('/api/teams/<int:team_id>', methods=['DELETE'])
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

@teams_bp.route('/api/teams/<int:team_id>/invite', methods=['POST'])
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

@teams_bp.route('/api/teams/join/<token>', methods=['POST'])
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

@teams_bp.route('/api/teams/<int:team_id>/members/<int:target_user_id>', methods=['DELETE'])
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

