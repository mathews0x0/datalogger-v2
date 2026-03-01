import pytest
import sys
import os

from flask_jwt_extended import create_access_token

# Add server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from api.models import db, User, SessionMeta
import api.config as config

@pytest.fixture
def client(app):
    
    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()
            
            # Create a user
            user = User(email='user@racesense.in', name='Test User', is_approved=True)
            user.set_password('Pass123!')
            db.session.add(user)
            db.session.commit()
            
            # Create a session meta
            sm = SessionMeta(
                session_id='test-session-123',
                user_id=user.id,
                session_name='Test Track Day',
                is_public=False
            )
            db.session.add(sm)
            db.session.commit()
            
            # Create a dummy session file on disk
            import json
            sessions_dir = config.get_user_sessions_dir(user.id)
            sessions_dir.mkdir(parents=True, exist_ok=True)
            with open(sessions_dir / 'test-session-123.json', 'w') as f:
                json.dump({'meta': {'session_name': 'Test Session'}}, f)
            
            # Set jwt
            token = create_access_token(identity=str(user.id))
            client.set_cookie('access_token_cookie', token)
            client.set_cookie('csrf_access_token', 'dummy_csrf')
            client.environ_base['HTTP_X_CSRF_TOKEN'] = 'dummy_csrf'
            
            yield client
            
            # Cleanup
            import shutil
            if sessions_dir.exists():
                shutil.rmtree(config.get_user_dir(user.id))
            
            db.session.remove()
            db.drop_all()

def test_list_sessions(client, app):
    resp = client.get('/api/sessions')
    assert resp.status_code == 200
    assert len(resp.json) == 1
    assert resp.json[0]['session_id'] == 'test-session-123'

def test_rename_session(client, app):
    resp = client.post('/api/sessions/test-session-123/rename', json={'new_name': 'Renamed Session'})
    print("Rename response:", resp.json)
    assert resp.status_code == 200
    
    with app.app_context():
        import json
        sessions_dir = config.get_user_sessions_dir(1)
        with open(sessions_dir / 'test-session-123.json', 'r') as f:
            data = json.load(f)
        assert data['meta']['session_name'] == 'Renamed Session'

def test_set_privacy(client, app):
    resp = client.put('/api/sessions/test-session-123/privacy', json={'is_public': True})
    assert resp.status_code == 200
    assert resp.json['is_public'] is True
    
    resp_feed = client.get('/api/public/sessions')
    assert resp_feed.status_code == 200
    assert len(resp_feed.json) == 1

def test_update_notes(client, app):
    resp = client.put('/api/sessions/test-session-123/notes', json={
        'notes': 'Sunny race'
    })
    print("Notes response:", resp.json)
    assert resp.status_code == 200

    with app.app_context():
        import json
        sessions_dir = config.get_user_sessions_dir(1)
        with open(sessions_dir / 'test-session-123.json', 'r') as f:
            data = json.load(f)

        assert data['mode']['notes'] == 'Sunny race'
