import pytest
import sys
import os

from flask_jwt_extended import create_access_token
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from run import app
from api.models import db, User, SessionMeta, TrackMeta

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()
            
            user1 = User(email='user1@racesense.in', name='User One', is_approved=True)
            user1.set_password('Pass123!')
            db.session.add(user1)
            
            user2 = User(email='user2@racesense.in', name='User Two', is_approved=True)
            user2.set_password('Pass123!')
            db.session.add(user2)
            db.session.commit()
                
            token = create_access_token(identity=str(user1.id))
            client.set_cookie('access_token_cookie', token)
            client.set_cookie('csrf_access_token', 'dummy_csrf')
            client.environ_base['HTTP_X_CSRF_TOKEN'] = 'dummy_csrf'
            
            yield client
            
            db.session.remove()
            db.drop_all()

def test_follow_user(client):
    resp = client.post('/api/users/2/follow')
    assert resp.status_code == 200
    assert resp.json['success'] is True
    
    # Check followers
    resp2 = client.get('/api/users/2/followers')
    assert resp2.status_code == 200
    assert type(resp2.json) is list
    assert len(resp2.json) == 1
    assert resp2.json[0]['id'] == 1

def test_unfollow_user(client):
    client.post('/api/users/2/follow')
    
    resp = client.delete('/api/users/2/follow')
    assert resp.status_code == 200
    assert resp.json['success'] is True
    
    resp2 = client.get('/api/users/2/followers')
    assert type(resp2.json) is list
    assert len(resp2.json) == 0

def test_social_counts(client):
    client.post('/api/users/2/follow')
    
    resp = client.get('/api/users/2/social-counts')
    print("Social counts 2:", resp.json)
    assert resp.status_code == 200
    assert resp.json.get('followers_count', resp.json.get('followers', -1)) == 1
    
    resp2 = client.get('/api/users/1/social-counts')
    print("Social counts 1:", resp2.json)
    assert resp2.status_code == 200
    assert resp2.json.get('following_count', resp2.json.get('following', -1)) == 1

def test_user_stats(client):
    resp = client.get('/api/users/2/stats')
    assert resp.status_code == 200
    assert 'total_sessions' in resp.json
    assert 'total_laps' in resp.json
