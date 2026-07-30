import os
import sys
import json
import subprocess
import unittest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Add server directory to path
server_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if server_path not in sys.path:
    sys.path.insert(0, server_path)

from api import create_app
from api.models import db, Job, User
from worker import check_stalled_jobs, process_job


def require_test_database_url():
    url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        env_file = Path(__file__).resolve().parents[2] / 'env' / 'test.env'
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                os.environ.setdefault(key, value)
            url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        raise RuntimeError('TEST_DATABASE_URL must be set, or env/test.env must exist, for PostgreSQL tests.')
    return url


class TestJobs(unittest.TestCase):
    def setUp(self):
        self.app = create_app(config_overrides={
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': require_test_database_url()
        })
        self.app_context = self.app.app_context()
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

    @patch('worker.subprocess.run')
    @patch('worker.register_new_sessions')
    def test_process_job_retries_once_after_timeout(self, mock_register, mock_subprocess):
        success = MagicMock()
        success.returncode = 0
        success.stdout = "Success after retry"
        mock_subprocess.side_effect = [
            subprocess.TimeoutExpired(cmd=["analysis"], timeout=120),
            success,
        ]

        job = Job(user_id=self.user.id, type='analysis', input_data=json.dumps({"csv_path": "dummy.csv"}))
        db.session.add(job)
        db.session.commit()

        process_job(job)

        fetched = Job.query.first()
        self.assertEqual(fetched.status, 'complete')
        self.assertIsNone(fetched.error)
        self.assertIn("Success after retry", fetched.result)
        self.assertEqual(mock_subprocess.call_count, 2)
        mock_register.assert_called_once_with(self.user.id)

    @patch('worker.subprocess.run')
    def test_process_job_fails_after_timeout_retry_exhausted(self, mock_subprocess):
        mock_subprocess.side_effect = [
            subprocess.TimeoutExpired(cmd=["analysis"], timeout=120),
            subprocess.TimeoutExpired(cmd=["analysis"], timeout=120),
        ]

        job = Job(user_id=self.user.id, type='analysis', input_data=json.dumps({"csv_path": "dummy.csv"}))
        db.session.add(job)
        db.session.commit()

        process_job(job)

        fetched = Job.query.first()
        self.assertEqual(fetched.status, 'failed')
        self.assertIn("exceeded 120 seconds", fetched.error)
        self.assertIn("2 attempts", fetched.error)
        self.assertEqual(mock_subprocess.call_count, 2)

if __name__ == '__main__':
    unittest.main()
