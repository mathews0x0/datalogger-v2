import pytest
import sys
import os

from flask_jwt_extended import create_access_token
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from run import app
from api.models import db, User, DeviceToken

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
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

def test_get_devices(client):
    resp = client.get('/api/devices')
    assert resp.status_code == 200
    assert type(resp.json) is list
    assert len(resp.json) == 1
    assert resp.json[0]['device_name'] == 'Test Device'

def test_create_device_token(client):
    resp = client.post('/api/devices/token', json={'device_name': 'New Device'})
    assert resp.status_code == 201
    assert 'token' in resp.json
    assert resp.json['token'].startswith('rsk_')

def test_delete_device(client):
    resp = client.delete('/api/devices/1')
    assert resp.status_code == 200
    
    with app.app_context():
        d = DeviceToken.query.get(1)
        assert d.revoked is True
