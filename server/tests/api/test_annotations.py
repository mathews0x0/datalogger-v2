import pytest
import sys
import os
import json

from flask_jwt_extended import create_access_token
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from run import app
from api.models import db, User, SessionMeta, Annotation

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()
            
            user = User(email='ano@racesense.in', name='Ano User', is_approved=True)
            user.set_password('Pass123!')
            db.session.add(user)
            db.session.commit()
            
            session1 = SessionMeta(session_id='ano-s1', user_id=user.id, track_id=999, session_name='Ano S1')
            db.session.add(session1)
            
            ann1 = Annotation(session_id='ano-s1', author_id=user.id, lap_number=2, sector_number=1, text='Test annotation')
            db.session.add(ann1)

            db.session.commit()
            
            token = create_access_token(identity=str(user.id))
            client.set_cookie('access_token_cookie', token)
            client.set_cookie('csrf_access_token', 'dummy_csrf')
            client.environ_base['HTTP_X_CSRF_TOKEN'] = 'dummy_csrf'
            
            yield client
            
            db.session.remove()
            db.drop_all()

def test_get_annotations(client):
    resp = client.get('/api/sessions/ano-s1/annotations')
    assert resp.status_code == 200
    assert type(resp.json) is list
    assert len(resp.json) == 1
    assert resp.json[0]['text'] == 'Test annotation'

def test_add_annotation(client):
    resp = client.post('/api/sessions/ano-s1/annotations', json={
        'lap_number': 3,
        'sector_number': 2,
        'text': 'Another annotation'
    })
    assert resp.status_code == 201
    assert resp.json['text'] == 'Another annotation'

def test_delete_annotation(client):
    resp = client.delete('/api/annotations/1')
    assert resp.status_code == 200
    
    with app.app_context():
        ann = Annotation.query.get(1)
        assert ann is None
