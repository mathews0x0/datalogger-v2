import pytest
import sys
import os

from flask_jwt_extended import create_access_token
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from api.main import app
from api.models import db, User

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
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

def test_process_missing_file(client):
    resp = client.post('/api/process', json={'filename': 'missing.csv'})
    assert resp.status_code == 404
    assert 'error' in resp.json

def test_learning_list(client):
    resp = client.get('/api/learning/list')
    assert resp.status_code == 200
    assert type(resp.json) is list

def test_learning_delete_missing(client):
    resp = client.post('/api/learning/delete', json={'files': ['missing.csv']})
    assert resp.status_code == 200
    assert resp.json['success'] is True
