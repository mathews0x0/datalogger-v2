import pytest
import sys
import os
import json
import shutil

from flask_jwt_extended import create_access_token

# Add server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from api.models import db, User, UnmatchedTrackReport, GlobalTrack, SessionMeta, AppSetting
import api.config as config

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
            
            global_dir = os.path.join(os.path.dirname(__file__), '../../data/tracks/coastt')
            if os.path.exists(global_dir):
                shutil.rmtree(global_dir)
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


def test_admin_get_settings_returns_default_sector_count(client):
    resp = client.get('/api/admin/settings')
    assert resp.status_code == 200
    assert resp.json['default_sector_count'] == config.SECTOR_COUNT


def test_admin_can_update_default_sector_count(client, app):
    resp = client.put('/api/admin/settings/default-sector-count', json={'value': 5})
    assert resp.status_code == 200
    assert resp.json['default_sector_count'] == 5

    with app.app_context():
        setting = AppSetting.query.filter_by(key=config.DEFAULT_SECTOR_COUNT_SETTING_KEY).first()
        assert setting is not None
        assert setting.value == '5'

def test_admin_upload_track_package(client):
    package = {
        "version": 1,
        "layout": {
            "fileName": "CoASTT layout.svg",
            "width": 1000,
            "height": 800,
            "embeddedDataUrl": "data:image/svg+xml;base64,PHN2Zy8+"
        },
        "telemetry": {
            "geoReference": {
                "lat0": 11.1272873,
                "lon0": 77.1845110,
                "metersPerDegLat": 111320,
                "metersPerDegLon": 109227.28
            },
            "autoAlign": {
                "scale": 1.5,
                "rotationDeg": 0.5,
                "translateX": 120,
                "translateY": 220
            },
            "sampledGpsPoints": [
                {"lat": 11.1, "lon": 77.1, "canonical": {"x": 0, "y": 0}},
                {"lat": 11.11, "lon": 77.11, "canonical": {"x": 100, "y": 50}},
                {"lat": 11.12, "lon": 77.12, "canonical": {"x": 200, "y": 120}},
                {"lat": 11.13, "lon": 77.13, "canonical": {"x": 300, "y": 200}}
            ]
        }
    }

    resp = client.post('/api/admin/tracks/package', json={
        'track_name': 'CoASTT',
        'slug': 'coastt',
        'package': package
    })
    assert resp.status_code == 200
    assert resp.json['track']['track_name'] == 'CoASTT'
    assert resp.json['track']['track_id'] >= 1000000


def test_admin_reupload_track_package_rebuilds_centerline_from_new_package(client):
    base_package = {
        "version": 1,
        "layout": {
            "fileName": "CoASTT layout.svg",
            "width": 1000,
            "height": 800,
            "embeddedDataUrl": "data:image/svg+xml;base64,PHN2Zy8+"
        },
        "telemetry": {
            "geoReference": {
                "lat0": 11.1272873,
                "lon0": 77.1845110,
                "metersPerDegLat": 111320,
                "metersPerDegLon": 109227.28
            },
            "autoAlign": {
                "scale": 1.5,
                "rotationDeg": 0.5,
                "translateX": 120,
                "translateY": 220
            },
            "sampledGpsPoints": [
                {"index": 30, "lat": 11.13, "lon": 77.13, "canonical": {"x": 300, "y": 200}},
                {"index": 10, "lat": 11.11, "lon": 77.11, "canonical": {"x": 100, "y": 50}},
                {"index": 20, "lat": 11.12, "lon": 77.12, "canonical": {"x": 200, "y": 120}},
                {"index": 0, "lat": 11.10, "lon": 77.10, "canonical": {"x": 0, "y": 0}}
            ]
        }
    }

    first_resp = client.post('/api/admin/tracks/package', json={
        'track_name': 'CoASTT',
        'slug': 'coastt',
        'package': base_package
    })
    assert first_resp.status_code == 200
    track_id = first_resp.json['track']['track_id']

    upgraded_package = json.loads(json.dumps(base_package))
    upgraded_package["telemetry"]["orderedGpsPoints"] = [
        {"index": 0, "lat": 11.1000, "lon": 77.1000, "canonical": {"x": 0, "y": 0}},
        {"index": 1, "lat": 11.1005, "lon": 77.1005, "canonical": {"x": 50, "y": 25}},
        {"index": 2, "lat": 11.1010, "lon": 77.1010, "canonical": {"x": 100, "y": 50}},
        {"index": 3, "lat": 11.1015, "lon": 77.1015, "canonical": {"x": 150, "y": 75}},
        {"index": 4, "lat": 11.1020, "lon": 77.1020, "canonical": {"x": 200, "y": 100}},
    ]

    second_resp = client.post('/api/admin/tracks/package', json={
        'track_name': 'CoASTT',
        'slug': 'coastt',
        'track_id': track_id,
        'package': upgraded_package
    })
    assert second_resp.status_code == 200

    track_path = config.get_global_track_dir('coastt') / 'track.json'
    with open(track_path, 'r') as f:
        track_json = json.load(f)

    assert len(track_json['centerline']) == 5
    assert track_json['centerline'][0] == {'lat': 11.1, 'lon': 77.1}
    assert track_json['centerline'][-1] == {'lat': 11.102, 'lon': 77.102}

def test_admin_resolve_unmatched_track(client, app):
    package = {
        "version": 1,
        "layout": {
            "fileName": "CoASTT layout.svg",
            "width": 1000,
            "height": 800,
            "embeddedDataUrl": "data:image/svg+xml;base64,PHN2Zy8+"
        },
        "telemetry": {
            "geoReference": {
                "lat0": 11.1272873,
                "lon0": 77.1845110,
                "metersPerDegLat": 111320,
                "metersPerDegLon": 109227.28
            },
            "autoAlign": {
                "scale": 1.5,
                "rotationDeg": 0.5,
                "translateX": 120,
                "translateY": 220
            },
            "sampledGpsPoints": [
                {"lat": 11.1, "lon": 77.1, "canonical": {"x": 0, "y": 0}},
                {"lat": 11.11, "lon": 77.11, "canonical": {"x": 100, "y": 50}},
                {"lat": 11.12, "lon": 77.12, "canonical": {"x": 200, "y": 120}},
                {"lat": 11.13, "lon": 77.13, "canonical": {"x": 300, "y": 200}}
            ]
        }
    }
    upload_resp = client.post('/api/admin/tracks/package', json={
        'track_name': 'CoASTT',
        'slug': 'coastt',
        'package': package
    })
    track_id = upload_resp.json['track']['track_id']

    with app.app_context():
        user = User.query.filter_by(email='user@racesense.in').first()
        report = UnmatchedTrackReport(
            user_id=user.id,
            session_id='sess_01',
            fallback_track_id=22,
            fallback_track_name='track_22',
            status='open'
        )
        db.session.add(report)
        db.session.commit()
        report_id = report.id

    resp = client.post(f'/api/admin/tracks/unmatched/{report_id}/resolve', json={
        'global_track_id': track_id,
        'status': 'resolved'
    })
    assert resp.status_code == 200
    assert resp.json['report']['resolved_global_track_id'] == track_id


def test_admin_delete_global_track_with_matched_sessions(client, app):
    with app.app_context():
        normal = User.query.filter_by(email='user@racesense.in').first()
        global_track = GlobalTrack(
            track_id=1000005,
            slug='deletable-master',
            track_name='Deletable Master',
            folder_name='deletable-master',
            package_version=1,
            layout_width=1000,
            layout_height=800,
            has_canonical_layout=True
        )
        db.session.add(global_track)
        db.session.add(SessionMeta(
            session_id='matched-session-1',
            user_id=normal.id,
            track_id=1000005,
            session_name='Matched Session',
            start_time='2026-04-28 10:00:00'
        ))
        report = UnmatchedTrackReport(
            user_id=normal.id,
            session_id='report-session-1',
            fallback_track_id=55,
            fallback_track_name='fallback_55',
            status='resolved',
            resolved_global_track_id=1000005
        )
        normal.active_track_id = 1000005
        db.session.add(report)
        db.session.commit()

        track_dir = config.get_global_track_dir('deletable-master')
        with open(track_dir / 'track.json', 'w') as f:
            json.dump({'track_id': 1000005, 'track_name': 'Deletable Master'}, f)

    resp = client.delete('/api/admin/tracks/1000005')
    assert resp.status_code == 200
    assert resp.json['success'] is True

    with app.app_context():
        normal = User.query.filter_by(email='user@racesense.in').first()
        assert GlobalTrack.query.filter_by(track_id=1000005).first() is None
        assert normal.active_track_id is None
        report = UnmatchedTrackReport.query.filter_by(session_id='report-session-1').first()
        assert report.resolved_global_track_id is None
        assert SessionMeta.query.filter_by(track_id=1000005).count() == 1
