import pytest
import sys
import os

from flask_jwt_extended import create_access_token
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from api.main import app
from api.models import db, User, Team, TeamMember, TeamInvite

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.test_client() as client:
        with app.app_context():
            db.drop_all()
            db.create_all()
            
            user1 = User(email='team1@racesense.in', name='Team Owner', is_approved=True, subscription_tier='team')
            user1.set_password('Pass123!')
            db.session.add(user1)
            
            user2 = User(email='team2@racesense.in', name='Team Member', is_approved=True)
            user2.set_password('Pass123!')
            db.session.add(user2)
            db.session.commit()
            
            team = Team(name='Test Team', owner_id=user1.id)
            db.session.add(team)
            db.session.commit()
            
            member1 = TeamMember(team_id=team.id, user_id=user1.id, role='owner')
            db.session.add(member1)
            
            member2 = TeamMember(team_id=team.id, user_id=user2.id, role='member')
            db.session.add(member2)
            db.session.commit()
                
            token = create_access_token(identity=str(user1.id))
            client.set_cookie('access_token_cookie', token)
            client.set_cookie('csrf_access_token', 'dummy_csrf')
            client.environ_base['HTTP_X_CSRF_TOKEN'] = 'dummy_csrf'
            
            yield client
            
            db.session.remove()
            db.drop_all()

def test_get_teams(client):
    resp = client.get('/api/teams')
    assert resp.status_code == 200
    assert type(resp.json) is list
    assert len(resp.json) == 1
    assert resp.json[0]['name'] == 'Test Team'

def test_create_team(client):
    resp = client.post('/api/teams', json={'name': 'New Team'})
    assert resp.status_code == 201
    assert resp.json['name'] == 'New Team'

def test_update_team(client):
    resp = client.put('/api/teams/1', json={'name': 'Updated Team'})
    assert resp.status_code == 200
    
    with app.app_context():
        t = Team.query.get(1)
        assert t.name == 'Updated Team'

def test_invite_member(client):
    resp = client.post('/api/teams/1/invite', json={'email': 'new@racesense.in'})
    assert resp.status_code == 200
    assert 'token' in resp.json
    
    with app.app_context():
        invites = TeamInvite.query.all()
        assert len(invites) == 1
