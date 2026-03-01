from functools import wraps
from flask import jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required
import os
from api.models import User

IS_CLOUD = os.environ.get('RACESENSE_CLOUD', 'false').lower() == 'true'

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

def admin_required(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        if not user.is_admin:
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function

def local_only(f):
    """Block endpoint when running in cloud mode (SSRF protection)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if IS_CLOUD:
            return jsonify({"error": "This feature is only available in local network mode"}), 403
        return f(*args, **kwargs)
    return decorated_function
