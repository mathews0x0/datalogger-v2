import pytest
import sys
import os

# Add server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from api.models import db, User

@pytest.fixture
def client(app):
    
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()

def test_register_and_login(client, app):
    # Test registration
    resp = client.post('/api/auth/register', json={
        'email': 'test@example.com',
        'password': 'Password123!',
        'name': 'Test User'
    })
    print("Response:", resp.json)
    assert resp.status_code == 201
    
    # Needs to be approved to login
    with app.app_context():
        u = User.query.filter_by(email='test@example.com').first()
        u.is_approved = True
        db.session.commit()
    
    # Test login
    resp = client.post('/api/auth/login', json={
        'email': 'test@example.com',
        'password': 'Password123!'
    })
    assert resp.status_code == 200
    assert 'user' in resp.json
    
    # Test me
    resp = client.get('/api/auth/me')
    assert resp.status_code == 200
    assert resp.json['email'] == 'test@example.com'
    
    # Test logout
    resp = client.post('/api/auth/logout')
    assert resp.status_code == 200
    
    # Test me again (should fail)
    resp = client.get('/api/auth/me')
    assert resp.status_code == 401
