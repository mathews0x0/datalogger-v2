import pytest
import sys
import os
import json
import shutil

from flask_jwt_extended import create_access_token
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from api.main import app
from api.models import db, User, TrackMeta
import api.config as config

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()
            
            user = User(email='track@racesense.in', name='Track User', is_approved=True)
            user.set_password('Pass123!')
            db.session.add(user)
            db.session.commit()
            
            tm = TrackMeta(track_id=101, user_id=user.id, track_name='Silverstone', folder_name='silverstone_101')
            db.session.add(tm)
            db.session.commit()
            
            tracks_dir = config.get_user_tracks_dir(user.id) / 'silverstone_101'
            tracks_dir.mkdir(parents=True, exist_ok=True)
            
            with open(tracks_dir / 'track.json', 'w') as f:
                json.dump({'track_name': 'Silverstone', 'pit_center_lat': 52.0}, f)
            
            with open(tracks_dir / 'tbl.json', 'w') as f:
                json.dump({'laps': []}, f)
                
            token = create_access_token(identity=str(user.id))
            client.set_cookie('access_token_cookie', token)
            client.set_cookie('csrf_access_token', 'dummy_csrf')
            client.environ_base['HTTP_X_CSRF_TOKEN'] = 'dummy_csrf'
            
            yield client
            
            if tracks_dir.parents[0].exists():
                shutil.rmtree(config.get_user_dir(user.id))
            db.session.remove()
            db.drop_all()

def test_get_tracks(client):
    resp = client.get('/api/tracks')
    assert resp.status_code == 200
    assert len(resp.json['tracks']) == 1
    assert resp.json['tracks'][0]['track_name'] == 'Silverstone'

def test_get_track(client):
    resp = client.get('/api/tracks/101')
    assert resp.status_code == 200
    assert resp.json['track_name'] == 'Silverstone'
    assert 'tbl' in resp.json

def test_update_track(client):
    resp = client.post('/api/tracks/101', json={'track_name': 'Silverstone GP', 'pit_center_lat': 52.1})
    assert resp.status_code == 200
    
    with app.app_context():
        user = User.query.filter_by(email='track@racesense.in').first()
        tracks_dir = config.get_user_tracks_dir(user.id) / 'silverstone_101'
        with open(tracks_dir / 'track.json', 'r') as f:
            data = json.load(f)
        assert data['track_name'] == 'Silverstone GP'
        assert data['pit_center_lat'] == 52.1
