import pytest
import sys
import os

# Add server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from api import create_app
from api.models import db

@pytest.fixture(scope="session")
def app():
    """Create and configure a new app instance for the entire test session."""
    test_config = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
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
