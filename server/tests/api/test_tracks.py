import pytest
import sys
import os
import json
import shutil

from flask_jwt_extended import create_access_token
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from api.models import db, User, TrackMeta, GlobalTrack, SessionMeta, DeviceToken
from api.track_catalog import _centerline_from_package, _extract_explicit_sector_gates, _first_package_trace_point
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


def test_device_active_track_includes_device_layout_and_tbl(client, app):
    with app.app_context():
        user = User.query.filter_by(email='track@racesense.in').first()
        global_track = GlobalTrack(
            track_id=1000001,
            slug='layouttrack',
            track_name='Layout Track',
            folder_name='layouttrack',
            package_version=1,
            layout_width=1000,
            layout_height=800,
            has_canonical_layout=True
        )
        db.session.add(global_track)
        user.active_track_id = 1000001
        device_token = DeviceToken(token='rsk_testtoken', user_id=user.id, device_name='Bench Device')
        db.session.add(device_token)
        db.session.commit()

        global_dir = config.get_global_track_dir('layouttrack')
        with open(global_dir / 'track.json', 'w') as f:
            json.dump({
                'track_id': 1000001,
                'track_name': 'Layout Track',
                'track_scope': 'global',
                'track_source': 'global_package',
                'has_canonical_layout': True,
                'start_line': {
                    'center': {'lat': 11.1001, 'lon': 77.1001},
                    'lat': 11.1001,
                    'lon': 77.1001,
                    'radius_m': 20
                },
                'centerline': [
                    {'lat': 11.1001, 'lon': 77.1001},
                    {'lat': 11.1002, 'lon': 77.1006},
                    {'lat': 11.0999, 'lon': 77.1009},
                    {'lat': 11.0996, 'lon': 77.1003},
                ],
                'sectors': [
                    {'id': 'S1', 'end_lat': 11.1002, 'end_lon': 77.1006, 'radius_m': 15},
                    {'id': 'S2', 'end_lat': 11.0999, 'end_lon': 77.1009, 'radius_m': 15},
                    {'id': 'S3', 'end_lat': 11.0996, 'end_lon': 77.1003, 'radius_m': 15},
                ]
            }, f)

        user_track_dir = config.get_user_tracks_dir(user.id) / 'global_track_1000001'
        user_track_dir.mkdir(parents=True, exist_ok=True)
        with open(user_track_dir / 'tbl.json', 'w') as f:
            json.dump({
                'sectors': [
                    {'sector_index': 2, 'best_time': 12.8},
                    {'sector_index': 0, 'best_time': 11.5},
                    {'sector_index': 1, 'best_time': 12.2},
                ]
            }, f)

    resp = client.get(
        '/api/device/active_track',
        headers={'Authorization': 'Bearer rsk_testtoken'}
    )
    assert resp.status_code == 200
    active_track = resp.json['active_track']
    assert active_track['sector_count'] == 3
    assert active_track['tbl']['sectors'] == [11.5, 12.2, 12.8]
    assert active_track['tbl']['lap_time'] == 36.5
    assert 'device_layout' in active_track
    assert len(active_track['device_layout']['polyline']) >= 2
    assert active_track['device_layout']['start_marker'] is not None
    assert len(active_track['device_layout']['sector_markers']) == 3


def test_device_active_track_builds_layout_from_fallback_geometry(client, app):
    with app.app_context():
        user = User.query.filter_by(email='track@racesense.in').first()
        user.active_track_id = 101
        device_token = DeviceToken(token='rsk_fallbacktoken', user_id=user.id, device_name='Bench Device')
        db.session.add(device_token)
        db.session.commit()

        track_dir = config.get_user_tracks_dir(user.id) / 'silverstone_101'
        with open(track_dir / 'track.json', 'w') as f:
            json.dump({
                'track_id': 101,
                'track_name': 'Silverstone',
                'track_scope': 'user_fallback',
                'track_source': 'session_generated',
                'has_canonical_layout': False,
                'start_line': {'lat': 52.0000, 'lon': -1.0000, 'radius_m': 20},
                'sectors': [
                    {'id': 'S1', 'end_lat': 52.0002, 'end_lon': -0.9996, 'radius_m': 15},
                    {'id': 'S2', 'end_lat': 51.9999, 'end_lon': -0.9992, 'radius_m': 15},
                    {'id': 'S3', 'end_lat': 51.9997, 'end_lon': -0.9998, 'radius_m': 15},
                ]
            }, f)
        with open(track_dir / 'geometry.json', 'w') as f:
            json.dump({
                'coordinates': [
                    [52.0000, -1.0000],
                    [52.0002, -0.9996],
                    [51.9999, -0.9992],
                    [51.9997, -0.9998],
                    [52.0000, -1.0000],
                ],
                'sector_indices': [1, 2, 3]
            }, f)

    resp = client.get(
        '/api/device/active_track',
        headers={'Authorization': 'Bearer rsk_fallbacktoken'}
    )
    assert resp.status_code == 200
    active_track = resp.json['active_track']
    assert active_track['track_id'] == 101
    assert active_track['track_scope'] == 'user_fallback'
    assert active_track['sector_count'] == 3
    assert 'centerline' not in active_track
    assert 'device_layout' in active_track
    assert len(active_track['device_layout']['polyline']) >= 4
    assert active_track['device_layout']['start_marker'] is not None
    assert len(active_track['device_layout']['sector_markers']) == 3


def test_centerline_from_package_uses_original_sample_order():
    centerline = _centerline_from_package({
        'telemetry': {
            'sampledGpsPoints': [
                {'index': 30, 'lat': 11.30, 'lon': 77.30},
                {'index': 10, 'lat': 11.10, 'lon': 77.10},
                {'index': 20, 'lat': 11.20, 'lon': 77.20},
            ]
        }
    })
    assert centerline == [
        {'lat': 11.10, 'lon': 77.10},
        {'lat': 11.20, 'lon': 77.20},
        {'lat': 11.30, 'lon': 77.30},
    ]


def test_centerline_from_package_prefers_ordered_gps_points():
    centerline = _centerline_from_package({
        'telemetry': {
            'orderedGpsPoints': [
                {'index': 0, 'lat': 11.01, 'lon': 77.01},
                {'index': 1, 'lat': 11.02, 'lon': 77.02},
                {'index': 2, 'lat': 11.03, 'lon': 77.03},
            ],
            'sampledGpsPoints': [
                {'index': 30, 'lat': 99.0, 'lon': 99.0},
                {'index': 10, 'lat': 98.0, 'lon': 98.0},
            ]
        }
    })
    assert centerline == [
        {'lat': 11.01, 'lon': 77.01},
        {'lat': 11.02, 'lon': 77.02},
        {'lat': 11.03, 'lon': 77.03},
    ]


def test_first_package_trace_point_prefers_ordered_gps_points():
    point = _first_package_trace_point({
        'telemetry': {
            'orderedGpsPoints': [
                {'index': 0, 'lat': 11.01, 'lon': 77.01},
                {'index': 1, 'lat': 11.02, 'lon': 77.02},
            ],
            'sampledGpsPoints': [
                {'index': 50, 'lat': 99.0, 'lon': 99.0},
            ],
        }
    })
    assert point == {'lat': 11.01, 'lon': 77.01}


def test_explicit_canonical_sector_gates_are_sorted_along_track():
    package = {
        'telemetry': {
            'geoReference': {
                'lat0': 11.0,
                'lon0': 77.0,
                'metersPerDegLat': 111320,
                'metersPerDegLon': 109000,
            },
            'autoAlign': {
                'scale': 1,
                'rotationDeg': 0,
                'translateX': 0,
                'translateY': 0,
            },
            'sampledGpsPoints': [
                {'index': 0, 'lat': 11.0000, 'lon': 77.0000},
                {'index': 1, 'lat': 11.0001, 'lon': 77.0001},
                {'index': 2, 'lat': 11.0002, 'lon': 77.0002},
                {'index': 3, 'lat': 11.0003, 'lon': 77.0003},
                {'index': 4, 'lat': 11.0004, 'lon': 77.0004},
                {'index': 5, 'lat': 11.0005, 'lon': 77.0005},
                {'index': 6, 'lat': 11.0006, 'lon': 77.0006},
            ],
        },
        'sectors': [
            {'id': 'gate_7', 'sector_index': 7, 'end_lat': 11.0006, 'end_lon': 77.0006, 'radius_m': 15},
            {'id': 'gate_1', 'sector_index': 1, 'end_lat': 11.0000, 'end_lon': 77.0000, 'radius_m': 15},
            {'id': 'gate_4', 'sector_index': 4, 'end_lat': 11.0003, 'end_lon': 77.0003, 'radius_m': 15},
            {'id': 'gate_2', 'sector_index': 2, 'end_lat': 11.0001, 'end_lon': 77.0001, 'radius_m': 15},
            {'id': 'gate_5', 'sector_index': 5, 'end_lat': 11.0004, 'end_lon': 77.0004, 'radius_m': 15},
            {'id': 'gate_3', 'sector_index': 3, 'end_lat': 11.0002, 'end_lon': 77.0002, 'radius_m': 15},
            {'id': 'gate_6', 'sector_index': 6, 'end_lat': 11.0005, 'end_lon': 77.0005, 'radius_m': 15},
        ],
    }

    sectors = _extract_explicit_sector_gates(package)
    assert [sector['id'] for sector in sectors] == ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7']
    assert [(sector['end_lat'], sector['end_lon']) for sector in sectors] == [
        (11.0000, 77.0000),
        (11.0001, 77.0001),
        (11.0002, 77.0002),
        (11.0003, 77.0003),
        (11.0004, 77.0004),
        (11.0005, 77.0005),
        (11.0006, 77.0006),
    ]
    assert [sector['progress_m'] for sector in sectors] == sorted(sector['progress_m'] for sector in sectors)


def test_generated_canonical_sectors_include_monotonic_progress_markers():
    centerline = [
        {'lat': 11.0000, 'lon': 77.0000},
        {'lat': 11.0001, 'lon': 77.0000},
        {'lat': 11.0002, 'lon': 77.0000},
        {'lat': 11.0003, 'lon': 77.0000},
        {'lat': 11.0004, 'lon': 77.0000},
        {'lat': 11.0005, 'lon': 77.0000},
        {'lat': 11.0006, 'lon': 77.0000},
        {'lat': 11.0007, 'lon': 77.0000},
    ]
    start_line = {'lat': 11.0000, 'lon': 77.0000, 'radius_m': 20.0}

    sectors = _generate_sectors_from_centerline(centerline, start_line, 4)

    assert [sector['id'] for sector in sectors] == ['S1', 'S2', 'S3', 'S4']
    assert all(sector.get('progress_m') is not None for sector in sectors)
    assert [sector['progress_m'] for sector in sectors] == sorted(sector['progress_m'] for sector in sectors)


def test_explicit_package_sector_numbers_are_preserved_when_start_finish_is_sector_seven():
    package = {
        'telemetry': {
            'geoReference': {
                'lat0': 11.0,
                'lon0': 77.0,
                'metersPerDegLat': 111000.0,
                'metersPerDegLon': 109000.0,
            },
            'autoAlign': {
                'rotationDeg': 0,
                'scale': 1,
                'translateX': 0,
                'translateY': 0,
            },
        },
        'startFinishLine': {
            'a': {'x': 0, 'y': 0},
            'b': {'x': 1, 'y': 0},
        },
        'sampledGpsPoints': [
            {'index': 0, 'lat': 11.0000, 'lon': 77.0000},
            {'index': 1, 'lat': 11.0001, 'lon': 77.0000},
            {'index': 2, 'lat': 11.0002, 'lon': 77.0000},
            {'index': 3, 'lat': 11.0003, 'lon': 77.0000},
            {'index': 4, 'lat': 11.0004, 'lon': 77.0000},
            {'index': 5, 'lat': 11.0005, 'lon': 77.0000},
            {'index': 6, 'lat': 11.0006, 'lon': 77.0000},
        ],
        'sectors': [
            {'id': 'S7', 'sector_index': 7, 'end_lat': 11.0000, 'end_lon': 77.0000, 'radius_m': 15},
            {'id': 'S1', 'sector_index': 1, 'end_lat': 11.0001, 'end_lon': 77.0000, 'radius_m': 15},
            {'id': 'S2', 'sector_index': 2, 'end_lat': 11.0002, 'end_lon': 77.0000, 'radius_m': 15},
            {'id': 'S3', 'sector_index': 3, 'end_lat': 11.0003, 'end_lon': 77.0000, 'radius_m': 15},
            {'id': 'S4', 'sector_index': 4, 'end_lat': 11.0004, 'end_lon': 77.0000, 'radius_m': 15},
            {'id': 'S5', 'sector_index': 5, 'end_lat': 11.0005, 'end_lon': 77.0000, 'radius_m': 15},
            {'id': 'S6', 'sector_index': 6, 'end_lat': 11.0006, 'end_lon': 77.0000, 'radius_m': 15},
        ],
    }

    sectors = _extract_explicit_sector_gates(package)

    assert [sector['id'] for sector in sectors] == ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7']
    assert [sector['sector_index'] for sector in sectors] == [1, 2, 3, 4, 5, 6, 7]
    assert (sectors[0]['end_lat'], sectors[0]['end_lon']) == (11.0001, 77.0000)
    assert (sectors[6]['end_lat'], sectors[6]['end_lon']) == (11.0000, 77.0000)


def test_explicit_package_sectors_are_not_rejected_when_default_sector_count_changes(monkeypatch):
    monkeypatch.setattr(config, 'SECTOR_COUNT', 5)

    package = {
        'telemetry': {
            'geoReference': {
                'lat0': 11.0,
                'lon0': 77.0,
                'metersPerDegLat': 111000.0,
                'metersPerDegLon': 109000.0,
            },
            'autoAlign': {
                'rotationDeg': 0,
                'scale': 1,
                'translateX': 0,
                'translateY': 0,
            },
        },
        'sampledGpsPoints': [
            {'index': 0, 'lat': 11.0000, 'lon': 77.0000},
            {'index': 1, 'lat': 11.0001, 'lon': 77.0000},
            {'index': 2, 'lat': 11.0002, 'lon': 77.0000},
            {'index': 3, 'lat': 11.0003, 'lon': 77.0000},
            {'index': 4, 'lat': 11.0004, 'lon': 77.0000},
            {'index': 5, 'lat': 11.0005, 'lon': 77.0000},
            {'index': 6, 'lat': 11.0006, 'lon': 77.0000},
        ],
        'sectors': [
            {'id': 'S1', 'sector_index': 1, 'end_lat': 11.0001, 'end_lon': 77.0000, 'radius_m': 15},
            {'id': 'S2', 'sector_index': 2, 'end_lat': 11.0002, 'end_lon': 77.0000, 'radius_m': 15},
            {'id': 'S3', 'sector_index': 3, 'end_lat': 11.0003, 'end_lon': 77.0000, 'radius_m': 15},
            {'id': 'S4', 'sector_index': 4, 'end_lat': 11.0004, 'end_lon': 77.0000, 'radius_m': 15},
            {'id': 'S5', 'sector_index': 5, 'end_lat': 11.0005, 'end_lon': 77.0000, 'radius_m': 15},
            {'id': 'S6', 'sector_index': 6, 'end_lat': 11.0006, 'end_lon': 77.0000, 'radius_m': 15},
            {'id': 'S7', 'sector_index': 7, 'end_lat': 11.0000, 'end_lon': 77.0000, 'radius_m': 15},
        ],
    }

    sectors = _extract_explicit_sector_gates(package)

    assert len(sectors) == 7
    assert [sector['sector_index'] for sector in sectors] == [1, 2, 3, 4, 5, 6, 7]
