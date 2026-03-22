from flask_jwt_extended import get_jwt_identity


def get_current_user_id():
    return int(get_jwt_identity())
