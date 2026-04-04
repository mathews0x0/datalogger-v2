import pytest
import sys
import os
import json
import shutil

from flask_jwt_extended import create_access_token

# Add server directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from api.models import db, User, UnmatchedTrackReport

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
