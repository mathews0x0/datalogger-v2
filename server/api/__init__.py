import os
from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from api.models import db, bcrypt

jwt = JWTManager()

def create_app(config_name='default'):
    """Application Factory for RaceSense API"""
    
    # Point to UI folder in same server directory
    static_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../ui'))
    app = Flask(__name__, static_folder=static_path, static_url_path='')
    
    # Environment detection
    FLASK_ENV = os.environ.get('FLASK_ENV', 'development')
    IS_PRODUCTION = FLASK_ENV == 'production'

    # CORS configuration
    if IS_PRODUCTION:
        DEFAULT_ORIGINS = [os.environ.get('RACESENSE_DOMAIN', 'https://app.racesense.in')]
    else:
        DEFAULT_ORIGINS = [
            "http://localhost",
            "https://localhost",
            "capacitor://localhost",
            "http://127.0.0.1",
            "http://localhost:6969",
            "http://192.168.1.35:6969"
        ]
        
    cors_origins_env = os.environ.get('CORS_ORIGINS')
    cors_origins = [o.strip() for o in cors_origins_env.split(',')] if cors_origins_env else DEFAULT_ORIGINS
    CORS(app, supports_credentials=True, origins=cors_origins)

    import api.config as config


    
    # App configuration
    # Note: Test cases might override this after create_app() is called
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + str(config.DATA_DIR / 'racesense.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max request size
    
    # JWT Secret
    _jwt_secret = os.environ.get('JWT_SECRET_KEY')
    if IS_PRODUCTION and not _jwt_secret:
        raise RuntimeError('JWT_SECRET_KEY environment variable must be set in production!')
        
    app.config['JWT_SECRET_KEY'] = _jwt_secret or 'racesense-v2-development-secret-key'
    app.config['JWT_TOKEN_LOCATION'] = ['cookies']
    app.config['JWT_COOKIE_CSRF_PROTECT'] = IS_PRODUCTION
    app.config['JWT_ACCESS_COOKIE_PATH'] = '/api/'
    app.config['JWT_REFRESH_COOKIE_PATH'] = '/api/auth/refresh'
    app.config['JWT_COOKIE_HTTPONLY'] = True
    app.config['JWT_COOKIE_SECURE'] = IS_PRODUCTION
    app.config['JWT_COOKIE_SAMESITE'] = 'Lax'
    
    # Init extensions
    db.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)
    
    # Register Middleware / Error handlers
    from api.middleware import add_header, protect_api, not_found, internal_error
    app.after_request(add_header)
    app.before_request(protect_api)
    app.errorhandler(404)(not_found)
    app.errorhandler(500)(internal_error)

    # Register blueprints safely
    from api.blueprints.admin import admin_bp
    from api.blueprints.sessions import sessions_bp
    from api.blueprints.tracks import tracks_bp
    from api.blueprints.social import social_bp
    from api.blueprints.teams import teams_bp
    from api.blueprints.leaderboards import leaderboards_bp
    from api.blueprints.annotations import annotations_bp
    from api.blueprints.devices import devices_bp
    from api.blueprints.sync import sync_bp
    from api.blueprints.files import files_bp
    from api.blueprints.trackdays import trackdays_bp
    from api.blueprints.core import core_bp
    from api.blueprints.auth import auth_bp, users_bp, sessions_misc_bp

    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(sessions_bp)
    app.register_blueprint(tracks_bp)
    app.register_blueprint(social_bp)
    app.register_blueprint(teams_bp)
    app.register_blueprint(leaderboards_bp)
    app.register_blueprint(annotations_bp)
    app.register_blueprint(devices_bp)
    app.register_blueprint(sync_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(trackdays_bp)
    app.register_blueprint(core_bp)
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(users_bp, url_prefix='/api/users')
    app.register_blueprint(sessions_misc_bp, url_prefix='/api/sessions')
    
    return app
