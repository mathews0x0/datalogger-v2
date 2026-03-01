import os
import sys
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Add server directory to path
server_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if server_path not in sys.path:
    sys.path.insert(0, server_path)

from api.models import db, Job, User
from api.main import app
from worker import check_stalled_jobs, process_job

class TestJobs(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app_context = app.app_context()
        self.app_context.push()
        db.create_all()

        # Create a dummy user
        self.user = User(email='test@example.com', name='Test User')
        self.user.set_password('password123')
        db.session.add(self.user)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_job_fields(self):
        job = Job(user_id=self.user.id, type='analysis', input_data='{"foo": "bar"}')
        db.session.add(job)
        db.session.commit()

        fetched = Job.query.first()
        self.assertEqual(fetched.status, 'queued')
        self.assertEqual(fetched.type, 'analysis')
        self.assertEqual(fetched.user_id, self.user.id)
        self.assertIsNotNone(fetched.id)
        self.assertIsNotNone(fetched.created_at)
        
    def test_stalled_jobs(self):
        # Create a job that has been running for 10 minutes
        job = Job(user_id=self.user.id, type='analysis', status='running', started_at=datetime.utcnow() - timedelta(minutes=10))
        db.session.add(job)
        db.session.commit()
        
        check_stalled_jobs()
        
        fetched = Job.query.first()
        self.assertEqual(fetched.status, 'failed')
        self.assertIn("timed out", fetched.error)

    @patch('worker.subprocess.run')
    @patch('worker.register_new_sessions')
    def test_process_job_success(self, mock_register, mock_subprocess):
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = "Success"
        
        job = Job(user_id=self.user.id, type='analysis', input_data=json.dumps({"csv_path": "dummy.csv"}))
        db.session.add(job)
        db.session.commit()
        
        process_job(job)
        
        fetched = Job.query.first()
        self.assertEqual(fetched.status, 'complete')
        self.assertIn("Success", fetched.result)
        mock_register.assert_called_once_with(self.user.id)

    @patch('worker.subprocess.run')
    def test_process_job_failure(self, mock_subprocess):
        mock_subprocess.return_value.returncode = 1
        mock_subprocess.return_value.stderr = "Error output details"
        
        job = Job(user_id=self.user.id, type='analysis', input_data=json.dumps({"csv_path": "dummy.csv"}))
        db.session.add(job)
        db.session.commit()
        
        process_job(job)
        
        fetched = Job.query.first()
        self.assertEqual(fetched.status, 'failed')
        self.assertIn("Error output", fetched.error)

if __name__ == '__main__':
    unittest.main()
