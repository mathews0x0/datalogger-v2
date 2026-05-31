import pytest
import sys
import os

from flask_jwt_extended import create_access_token

# Add server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from api.models import db, User, SessionMeta, TrackMeta, AppSetting
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
                is_public=False,
                track_id=101,
            )
            db.session.add(sm)
            db.session.add(TrackMeta(track_id=101, user_id=user.id, track_name='Test Track', folder_name='test_track_101'))
            db.session.commit()
            
            # Create a dummy session file on disk
            import json
            sessions_dir = config.get_user_sessions_dir(user.id)
            sessions_dir.mkdir(parents=True, exist_ok=True)
            with open(sessions_dir / 'test-session-123.json', 'w') as f:
                json.dump({'meta': {'session_name': 'Test Session'}}, f)
            with open(sessions_dir / 'test-session-123_playback.json', 'w') as f:
                json.dump({
                    'config': {'leanSign': -1, 'smoothingSamples': 5, 'longitudinalGain': 0.85, 'gpsLagMs': 1800, 'graphLeanDisplaySign': -1},
                    'meta': {'gps_lag_ms_applied': 1800},
                    'rows': [
                        {
                            'time': 0.0,
                            'lat': 10.0,
                            'lon': 77.0,
                            'speed_kmh': 100.0,
                            'lean_deg': -5.0,
                            'long_g': 0.2,
                            'lat_g': 0.1,
                            'display_lean_deg': -5.0,
                            'display_long_g': 0.2,
                            'display_lat_g': 0.1,
                            'display_lat': 10.0,
                            'display_lon': 77.0,
                            'display_speed_kmh': 100.0,
                            'imu_lean_base_deg': -5.0,
                            'imu_long_base_g': 0.2,
                            'imu_lat_base_g': 0.1,
                            'gps_lean_base_deg': 4.0,
                            'gps_long_base_g': -0.2,
                            'gps_is_valid': True,
                            'gps_is_fix': True,
                        }
                    ],
                    'laps': [],
                }, f)
            tracks_dir = config.get_user_tracks_dir(user.id) / 'test_track_101'
            tracks_dir.mkdir(parents=True, exist_ok=True)
            with open(tracks_dir / 'tbl.json', 'w') as f:
                json.dump({'track_id': 101, 'total_best_time': 19.757}, f)
            
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


def test_session_meta_defaults_public_when_unspecified(app):
    with app.app_context():
        db.drop_all()
        db.create_all()

        user = User(email='default-public@racesense.in', name='Default Public', is_approved=True)
        user.set_password('Pass123!')
        db.session.add(user)
        db.session.commit()

        sm = SessionMeta(
            session_id='default-public-session',
            user_id=user.id,
            session_name='Default Public Session',
        )
        db.session.add(sm)
        db.session.commit()

        saved = SessionMeta.query.filter_by(session_id='default-public-session', user_id=user.id).first()
        assert saved is not None
        assert saved.is_public is True

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

def test_delete_last_session_resets_tbl(client, app):
    resp = client.delete('/api/sessions/test-session-123')
    assert resp.status_code == 200

    with app.app_context():
        tracks_dir = config.get_user_tracks_dir(1) / 'test_track_101'
        assert not (tracks_dir / 'tbl.json').exists()


def test_get_playback_uses_saved_tune_only_when_enabled(client, app):
    with app.app_context():
        db.session.add(AppSetting(key='playback_tuner_enabled', value='true'))
        db.session.add(AppSetting(key='playback_tuner_active_tune', value='{"leanSign":1,"leanOffsetDeg":2,"smoothingSamples":1,"longitudinalGain":1.5,"gpsLagMs":1800,"graphLeanDisplaySign":1}'))
        db.session.commit()

    resp = client.get('/api/sessions/test-session-123/playback')
    assert resp.status_code == 200
    assert resp.json['meta']['tune_source'] == 'saved'
    assert resp.json['rows'][0]['display_lean_deg'] == -3.0
