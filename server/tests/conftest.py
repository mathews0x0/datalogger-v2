import pytest
import sys
import os
from pathlib import Path

# Add server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from api import create_app
from api.models import db


def require_test_database_url():
    url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        env_file = Path(__file__).resolve().parents[2] / 'env' / 'test.env'
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                os.environ.setdefault(key, value)
            url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        raise RuntimeError('TEST_DATABASE_URL must be set, or env/test.env must exist, for PostgreSQL tests.')
    return url

@pytest.fixture(scope="session")
def app():
    """Create and configure a new app instance for the entire test session."""
    test_config = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': require_test_database_url(),
        'JWT_SECRET_KEY': 'test-secret',
        'SERVER_NAME': 'localhost:5000'
    }
    
    app = create_app(config_overrides=test_config)
    
    with app.app_context():
        yield app

@pytest.fixture(scope="function")
def client(app):
    """A test client for the app."""
    # Create the database schema before each test function
    with app.app_context():
        db.create_all()
    
    with app.test_client() as client:
        yield client
        
    # Clean up the database schema after the test completes
    with app.app_context():
        db.session.remove()
        db.drop_all()
