import os
import sys
from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate

from api.models import db, bcrypt

jwt = JWTManager()
migrate = Migrate()


def _normalize_database_url(raw_url):
    if not raw_url:
        raise RuntimeError('DATABASE_URL environment variable must be set.')

    if raw_url.startswith('postgresql+'):
        return raw_url

    if raw_url.startswith('postgresql://'):
        return 'postgresql+psycopg://' + raw_url[len('postgresql://'):]

    if raw_url.startswith('postgres://'):
        return 'postgresql+psycopg://' + raw_url[len('postgres://'):]

    return raw_url

def create_app(config_overrides=None):
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
            "http://127.0.0.1",
            "http://localhost:6969",
            "http://192.168.1.35:6969"
        ]
        
    cors_origins_env = os.environ.get('CORS_ORIGINS')
    cors_origins = [o.strip() for o in cors_origins_env.split(',')] if cors_origins_env else DEFAULT_ORIGINS
    CORS(app, supports_credentials=True, origins=cors_origins)

    # App configuration
    database_url = None
    if config_overrides:
        database_url = config_overrides.get('SQLALCHEMY_DATABASE_URI')
    if not database_url:
        database_url = os.environ.get('DATABASE_URL')
    app.config['SQLALCHEMY_DATABASE_URI'] = _normalize_database_url(database_url)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 3600,
    }
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max request size
    
    # JWT Secret
    _jwt_secret = os.environ.get('JWT_SECRET_KEY')
    if IS_PRODUCTION and not _jwt_secret:
        raise RuntimeError('JWT_SECRET_KEY environment variable must be set in production!')
        
    app.config['JWT_SECRET_KEY'] = _jwt_secret or 'racesense-v2-development-secret-key'
    app.config['JWT_TOKEN_LOCATION'] = ['cookies', 'headers']
    app.config['JWT_COOKIE_CSRF_PROTECT'] = IS_PRODUCTION
    app.config['JWT_ACCESS_COOKIE_PATH'] = '/api/'
    app.config['JWT_REFRESH_COOKIE_PATH'] = '/api/auth/refresh'
    app.config['JWT_COOKIE_HTTPONLY'] = True
    app.config['JWT_COOKIE_SECURE'] = IS_PRODUCTION
    app.config['JWT_COOKIE_SAMESITE'] = 'Lax'
    
    if config_overrides:
        app.config.update(config_overrides)
        
    # Init extensions
    db.init_app(app)
    migrate.init_app(app, db)
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
    from api.blueprints.race_view import race_view_bp
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
    app.register_blueprint(race_view_bp)
    app.register_blueprint(core_bp)
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(users_bp, url_prefix='/api/users')
    app.register_blueprint(sessions_misc_bp, url_prefix='/api/sessions')
    
    # Auto-run migrations on startup if running as a web server
    # We skip this during 'flask db' CLI commands to avoid locking issues
    if 'db' not in sys.argv and not app.config.get('TESTING'):
        with app.app_context():
            try:
                from flask_migrate import upgrade
                upgrade()
            except Exception as e:
                print(f"[RaceSense] db upgrade skipped/failed: {e}")

    return app
