import pytest
import sys
import os
import json

from flask_jwt_extended import create_access_token

# Add server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from api.models import db, User

@pytest.fixture
def client(app):
    
    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()
            
            # Create a super admin user to use the endpoints
            admin = User(email='admin@racesense.in', name='Admin User', is_approved=True, is_admin=True)
            admin.set_password('AdminPass123!')
            db.session.add(admin)
            
            # Create a normal user for testing modification
            normal = User(email='user@racesense.in', name='Normal User', is_approved=False, is_admin=False)
            normal.set_password('UserPass123!')
            db.session.add(normal)
            
            db.session.commit()
            
            # Set jwt cookie on the client
            admin_token = create_access_token(identity=str(admin.id))
            client.set_cookie('access_token_cookie', admin_token)
            client.set_cookie('csrf_access_token', 'dummy_csrf')
            client.environ_base['HTTP_X_CSRF_TOKEN'] = 'dummy_csrf'
            
            yield client
            
            db.session.remove()
            db.drop_all()

def test_admin_list_users(client, app):
    resp = client.get('/api/admin/users')
    assert resp.status_code == 200
    assert resp.json['total'] == 2

def test_admin_approve_user(client, app):
    with app.app_context():
        u = User.query.filter_by(email='user@racesense.in').first()
        uid = u.id

    resp = client.put(f'/api/admin/users/{uid}/approve', json={'approved': True})
    assert resp.status_code == 200
    assert resp.json['user']['is_approved'] is True

def test_admin_update_user_tier(client, app):
    with app.app_context():
        u = User.query.filter_by(email='user@racesense.in').first()
        uid = u.id

    resp = client.put(f'/api/admin/users/{uid}/tier', json={'tier': 'pro'})
    assert resp.status_code == 200
    assert resp.json['user']['subscription_tier'] == 'pro'

def test_admin_get_user(client, app):
    with app.app_context():
        u = User.query.filter_by(email='user@racesense.in').first()
        uid = u.id

    resp = client.get(f'/api/admin/users/{uid}')
    assert resp.status_code == 200
    assert resp.json['email'] == 'user@racesense.in'
