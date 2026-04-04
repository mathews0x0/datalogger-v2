import pytest
import sys
import os
import json
import shutil

from flask_jwt_extended import create_access_token
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from api.models import db, User, TrackMeta, GlobalTrack, SessionMeta
import api.config as config

@pytest.fixture
def client(app):
    
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
            global_dir = config.get_global_tracks_dir() / 'coastt'
            if global_dir.exists():
                shutil.rmtree(global_dir)
            db.session.remove()
            db.drop_all()

def test_get_tracks(client, app):
    resp = client.get('/api/tracks')
    assert resp.status_code == 200
    assert len(resp.json['tracks']) == 1
    assert resp.json['tracks'][0]['track_name'] == 'Silverstone'

def test_get_track(client, app):
    resp = client.get('/api/tracks/101')
    assert resp.status_code == 200
    assert resp.json['track_name'] == 'Silverstone'
    assert 'tbl' in resp.json

def test_update_track(client, app):
    resp = client.post('/api/tracks/101', json={'track_name': 'Silverstone GP', 'pit_center_lat': 52.1})
    assert resp.status_code == 200
    
    with app.app_context():
        user = User.query.filter_by(email='track@racesense.in').first()
        tracks_dir = config.get_user_tracks_dir(user.id) / 'silverstone_101'
        with open(tracks_dir / 'track.json', 'r') as f:
            data = json.load(f)
        assert data['track_name'] == 'Silverstone GP'
        assert data['pit_center_lat'] == 52.1

def test_global_track_appears_for_user_and_is_read_only(client, app):
    with app.app_context():
        user = User.query.filter_by(email='track@racesense.in').first()
        global_track = GlobalTrack(
            track_id=1000000,
            slug='coastt',
            track_name='CoASTT',
            folder_name='coastt',
            package_version=1,
            layout_width=1000,
            layout_height=800,
            has_canonical_layout=True
        )
        db.session.add(global_track)
        db.session.add(SessionMeta(
            session_id='global-match-1',
            user_id=user.id,
            track_id=1000000,
            session_name='Matched Session',
            start_time='2026-04-03 10:00:00'
        ))
        db.session.commit()

        global_dir = config.get_global_track_dir('coastt')
        with open(global_dir / 'track.json', 'w') as f:
            json.dump({
                'track_id': 1000000,
                'track_name': 'CoASTT',
                'track_scope': 'global',
                'track_source': 'global_package',
                'has_canonical_layout': True,
                'start_line': {'lat': 11.1, 'lon': 77.1, 'radius_m': 30},
                'sectors': []
            }, f)
        with open(global_dir / 'layout_metadata.json', 'w') as f:
            json.dump({
                'svg_data_url': 'data:image/svg+xml;base64,PHN2Zy8+',
                'layout_width': 1000,
                'layout_height': 800,
                'geo_reference': {'lat0': 11.1, 'lon0': 77.1, 'metersPerDegLat': 111320, 'metersPerDegLon': 109000},
                'auto_align': {'scale': 1, 'rotationDeg': 0, 'translateX': 0, 'translateY': 0}
            }, f)

    resp = client.get('/api/tracks')
    assert resp.status_code == 200
    track_ids = {track['track_id']: track for track in resp.json['tracks']}
    assert 1000000 in track_ids
    assert track_ids[1000000]['track_scope'] == 'global'

    rename_resp = client.post('/api/tracks/1000000/rename', json={'new_name': 'Nope'})
    assert rename_resp.status_code == 403
