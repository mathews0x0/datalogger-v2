import pytest
import sys
import os

from flask_jwt_extended import create_access_token
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from api.models import db, User, DeviceToken

@pytest.fixture
def client(app):
    
    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()
            
            user = User(email='dev@racesense.in', name='Device User', is_approved=True)
            user.set_password('Pass123!')
            db.session.add(user)
            db.session.commit()
            
            device = DeviceToken(token='rsk_123', user_id=user.id, device_name='Test Device')
            db.session.add(device)
            db.session.commit()
            
            token = create_access_token(identity=str(user.id))
            client.set_cookie('access_token_cookie', token)
            client.set_cookie('csrf_access_token', 'dummy_csrf')
            client.environ_base['HTTP_X_CSRF_TOKEN'] = 'dummy_csrf'
            
            yield client
            
            db.session.remove()
            db.drop_all()

def test_get_devices(client, app):
    resp = client.get('/api/devices')
    assert resp.status_code == 200
    assert type(resp.json) is list
    assert len(resp.json) == 1
    assert resp.json[0]['device_name'] == 'Test Device'

def test_create_device_token(client, app):
    resp = client.post('/api/devices/token', json={'device_name': 'New Device'})
    assert resp.status_code == 201
    assert 'token' in resp.json
    assert resp.json['token'].startswith('rsk_')


def test_device_ping_updates_telemetry(client, app):
    response = client.post(
        '/api/device/ping',
        headers={'Authorization': 'Bearer rsk_123'},
        json={
            'device_uid': 'P4-BENCH-01',
            'vbatt_sense': 3.91,
            'storage_sd_free': 123456,
            'storage_sd_total': 654321,
            'storage_flash_free': 4567,
            'storage_flash_total': 8910,
        },
    )
    assert response.status_code == 200
    assert response.json == {'success': True}

    with app.app_context():
        device = DeviceToken.query.filter_by(token='rsk_123').one()
        assert device.device_uid == 'P4-BENCH-01'
        assert device.vbatt_sense == 3.91
        assert device.storage_sd_free == 123456
        assert device.storage_sd_total == 654321
        assert device.storage_flash_free == 4567
        assert device.storage_flash_total == 8910

def test_delete_device(client, app):
    resp = client.delete('/api/devices/1')
    assert resp.status_code == 200
    
    with app.app_context():
        d = DeviceToken.query.get(1)
        assert d.revoked is True
        assert d.revoked_at is not None


def test_prune_old_revoked_tokens(client, app):
    with app.app_context():
        user = User.query.filter_by(email='dev@racesense.in').first()
        for idx in range(4):
            db.session.add(DeviceToken(
                token=f'rsk_old_{idx}',
                user_id=user.id,
                device_name=f'Old Device {idx}',
                revoked=True
            ))
        db.session.commit()

        revoked_tokens = DeviceToken.query.filter_by(user_id=user.id, revoked=True).order_by(DeviceToken.id.asc()).all()
        for revoked_token in revoked_tokens:
            revoked_token.revoked_at = revoked_token.created_at
        db.session.commit()

        active_token = DeviceToken.query.filter_by(user_id=user.id, revoked=False).first()
        active_token_id = active_token.id

    resp = client.delete(f'/api/devices/{active_token_id}')
    assert resp.status_code == 200

    with app.app_context():
        revoked_tokens = DeviceToken.query.filter_by(user_id=user.id, revoked=True).order_by(DeviceToken.revoked_at.desc(), DeviceToken.id.desc()).all()
        assert len(revoked_tokens) == 3
        assert revoked_tokens[0].id == active_token_id
