from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import jwt_required, create_access_token, get_jwt_identity, set_access_cookies, unset_jwt_cookies
import re

from api.models import db, User, SessionMeta
import api.config as config
from api.auth_utils import get_current_user_id

auth_bp = Blueprint('auth', __name__)
users_bp = Blueprint('users', __name__)

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    email = data.get('email')
    password = data.get('password')
    name = data.get('name', '')

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters long"}), 400
    if password.lower() == password:
        if not any(c.isdigit() for c in password):
            return jsonify({"error": "Password must contain at least one number or uppercase letter"}), 400

    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return jsonify({"error": "Please provide a valid email address"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 400

    user = User(email=email, name=name, is_approved=False)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify({"success": True, "message": "Registration successful! Your account is pending admin approval. You will be able to login once an admin approves your account. For help, contact support@racesense.in"}), 201

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "Invalid login request. Please ensure you have provided your credentials."}), 400
        
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "Please provide both an email address and a password."}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "The email or password you entered is incorrect. Please try again."}), 400

    if not user.is_approved:
        return jsonify({"error": "Your account is pending admin approval. Please wait for an admin to approve your account, or contact support@racesense.in for help."}), 403

    access_token = create_access_token(identity=str(user.id))
    response = jsonify({"success": True, "user": user.to_dict()})
    set_access_cookies(response, access_token)
    return response

@auth_bp.route('/logout', methods=['POST'])
def logout():
    response = jsonify({"success": True})
    unset_jwt_cookies(response)
    return response

@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def me():
    user_id = get_current_user_id()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user.to_dict())

@auth_bp.route('/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    user_id = get_current_user_id()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()
    if 'name' in data: user.name = data['name']
    if 'bike_info' in data: user.bike_info = data['bike_info']
    if 'home_track' in data: user.home_track = data['home_track']
    
    db.session.commit()
    return jsonify(user.to_dict())

@auth_bp.route('/profile/photo', methods=['POST'])
@jwt_required()
def upload_profile_photo():
    user_id = get_current_user_id()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    if 'photo' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['photo']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    allowed = {'jpg', 'jpeg', 'png', 'webp'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed:
        return jsonify({"error": "Only JPG, PNG, and WebP files are allowed"}), 400

    user_dir = config.get_user_dir(int(user_id))
    photo_filename = f"profile.{ext}"
    photo_path = user_dir / photo_filename

    if user.profile_photo:
        old_path = user_dir / user.profile_photo
        if old_path.exists():
            old_path.unlink()

    file.save(str(photo_path))

    try:
        from PIL import Image
        img = Image.open(str(photo_path))
        img = img.convert('RGB')
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        img = img.crop((left, top, left + side, top + side))
        img = img.resize((256, 256), Image.LANCZOS)
        photo_filename = "profile.jpg"
        photo_path = user_dir / photo_filename
        img.save(str(photo_path), "JPEG", quality=85)
    except ImportError:
        pass

    user.profile_photo = photo_filename
    db.session.commit()
    return jsonify({"success": True, "profile_photo": photo_filename, "user": user.to_dict()})

@auth_bp.route('/profile/photo', methods=['DELETE'])
@jwt_required()
def delete_profile_photo():
    user_id = get_current_user_id()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.profile_photo:
        photo_path = config.get_user_dir(int(user_id)) / user.profile_photo
        if photo_path.exists():
            photo_path.unlink()
        user.profile_photo = None
        db.session.commit()

    return jsonify({"success": True, "user": user.to_dict()})

@users_bp.route('/<int:uid>/photo', methods=['GET'])
def get_user_photo(uid):
    user = User.query.get(uid)
    if not user or not user.profile_photo:
        return '', 204

    user_dir = config.get_user_dir(uid)
    photo_path = user_dir / user.profile_photo
    if not photo_path.exists():
        return '', 204

    return send_file(str(photo_path), mimetype='image/jpeg')

@auth_bp.route('/change-password', methods=['POST'])
@jwt_required()
def change_password():
    user_id = get_current_user_id()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    old_password = data.get('old_password')
    new_password = data.get('new_password')

    if not old_password or not new_password:
        return jsonify({"error": "Both old and new passwords are required"}), 400

    if not user.check_password(old_password):
        return jsonify({"error": "Incorrect current password"}), 401

    if len(new_password) < 8:
        return jsonify({"error": "New password must be at least 8 characters long"}), 400
    if new_password.lower() == new_password:
        if not any(c.isdigit() for c in new_password):
            return jsonify({"error": "New password must contain at least one number or uppercase letter"}), 400

    user.set_password(new_password)
    db.session.commit()

    return jsonify({"success": True, "message": "Password updated successfully!"})

# /api/sessions/limit should go to sessions blueprint later. I'll put it here temporarily as sessions_misc_bp
sessions_misc_bp = Blueprint('sessions_misc', __name__)

@sessions_misc_bp.route('/limit', methods=['GET'])
@jwt_required()
def get_session_limit():
    user_id = get_current_user_id()
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
