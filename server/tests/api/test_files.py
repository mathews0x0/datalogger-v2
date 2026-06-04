import pytest
import sys
import os
import json

from flask_jwt_extended import create_access_token
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from api.models import db, User, SessionMeta
import api.config as config
from api.helpers import register_new_sessions

@pytest.fixture
def client(app):
    
    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()
            
            user = User(email='files@racesense.in', name='Files User', is_approved=True)
            user.set_password('Pass123!')
            db.session.add(user)
            db.session.commit()
            
            token = create_access_token(identity=str(user.id))
            client.set_cookie('access_token_cookie', token)
            client.set_cookie('csrf_access_token', 'dummy_csrf')
            client.environ_base['HTTP_X_CSRF_TOKEN'] = 'dummy_csrf'
            
            yield client
            
            db.session.remove()
            db.drop_all()

def test_process_missing_file(client, app):
    resp = client.post('/api/process', json={'filename': 'missing.csv'})
    assert resp.status_code == 404
    assert 'error' in resp.json

def test_learning_list(client, app):
    resp = client.get('/api/learning/list')
    assert resp.status_code == 200
    assert type(resp.json) is list

def test_learning_delete_missing(client, app):
    resp = client.post('/api/learning/delete', json={'files': ['missing.csv']})
    assert resp.status_code == 200
    assert resp.json['success'] is True

def test_register_new_sessions_ignores_playback_sidecar(client, app):
    with app.app_context():
        user = User.query.filter_by(email='files@racesense.in').first()
        sessions_dir = config.get_user_sessions_dir(user.id)

        real_session = {
            'meta': {
                'session_id': 'sess_real',
                'start_time': '2026-05-25 08:50:00',
                'duration_sec': 852.0,
                'source_file': '/tmp/sess_real.csv',
            },
            'track': {
                'track_id': 1000068,
                'track_name': 'track_1000068',
                'track_scope': 'user_fallback',
                'folder_name': 'track_1000068',
            },
            'summary': {
                'total_laps': 6,
                'best_lap_time': 95.434,
            },
            'laps': [{}],
        }
        playback_sidecar = {
            'rows': [],
            'gps_lag_ms_applied': 2200,
        }

        (sessions_dir / 'sess_real.json').write_text(json.dumps(real_session))
        (sessions_dir / 'sess_real_playback.json').write_text(json.dumps(playback_sidecar))

        register_new_sessions(user.id)

        metas = SessionMeta.query.filter_by(user_id=user.id).order_by(SessionMeta.session_id.asc()).all()
        assert [meta.session_id for meta in metas] == ['sess_real']
        assert metas[0].duration_sec == 852.0
        assert metas[0].total_laps == 6

        metas[0].is_public = False
        db.session.commit()
        real_session['meta']['start_time'] = '2026-05-25 09:00:00'
        real_session['meta']['duration_sec'] = 900.0
        real_session['summary']['total_laps'] = 7
        real_session['summary']['best_lap_time'] = 94.123
        (sessions_dir / 'sess_real.json').write_text(json.dumps(real_session))

        register_new_sessions(user.id)

        refreshed = SessionMeta.query.filter_by(user_id=user.id, session_id='sess_real').one()
        assert refreshed.start_time == '2026-05-25 09:00:00'
        assert refreshed.duration_sec == 900.0
        assert refreshed.total_laps == 7
        assert refreshed.best_lap_time == 94.123
        assert refreshed.is_public is False
