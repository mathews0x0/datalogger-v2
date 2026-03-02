from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
import os

from api.models import db, User, SessionMeta, Annotation, TeamMember

annotations_bp = Blueprint('annotations', __name__)

@annotations_bp.route('/api/sessions/<session_id>/annotations', methods=['POST'])
@jwt_required()
def add_annotation(session_id):
    """Add annotation to a session"""
    user_id = int(get_jwt_identity())
    
    # Access check: owner, coach/owner of owner's team, or public
    # MUST find the session that belongs to this user or they have access to
    s_meta = SessionMeta.query.filter_by(session_id=session_id, user_id=user_id).first()
    if not s_meta:
        # Check team access fallback if session owner is different
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
        session_id=s_meta.id, # Link to the UNIQUE primary key ID, not the session_id string
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

@annotations_bp.route('/api/sessions/<session_id>/annotations', methods=['GET'])
def get_annotations(session_id):
    """Get annotations for a session"""
    # Anyone who can view the session can view annotations
    try:
        verify_jwt_in_request(optional=True)
    except:
        pass
    user_id = get_jwt_identity()
    
    # Look for session - prioritize own
    s_meta = None
    if user_id:
        s_meta = SessionMeta.query.filter_by(session_id=session_id, user_id=int(user_id)).first()
    
    # Fallback to any session for public/team check
    if not s_meta:
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
            from api.models import TeamMember
            owner_teams = TeamMember.query.filter_by(user_id=s_meta.user_id).all()
            for ot in owner_teams:
                caller_membership = TeamMember.query.filter_by(team_id=ot.team_id, user_id=user_id).first()
                if caller_membership and caller_membership.role in ['owner', 'coach']:
                    has_access = True
                    break
    
    if not has_access:
        return jsonify({"error": "Access denied"}), 403
        
    annotations = Annotation.query.filter_by(session_id=s_meta.id).order_by(Annotation.created_at.asc()).all()
    
    result = []
    for a in annotations:
        a_dict = a.to_dict()
        author = User.query.get(a.author_id)
        a_dict['author_name'] = author.name if author else "Unknown"
        result.append(a_dict)
        
    return jsonify(result)

@annotations_bp.route('/api/annotations/<int:annotation_id>', methods=['DELETE'])
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

