import os
import sys
import json
import time
from datetime import datetime, timedelta
import subprocess

# Ensure server module is in path
server_path = os.path.abspath(os.path.join(os.path.dirname(__file__)))
if server_path not in sys.path:
    sys.path.insert(0, server_path)

from api.models import db, Job
from api.main import app, register_new_sessions
import api.config as config

print("="*50)
print(" Datalogger Background Job Worker ")
print("="*50)
print(f"Time: {datetime.now()}")
print(f"Using server path: {server_path}")

STALL_TIMEOUT_MINUTES = 5

def check_stalled_jobs():
    """Mark jobs that have been running for too long as failed."""
    cutoff = datetime.utcnow() - timedelta(minutes=STALL_TIMEOUT_MINUTES)
    stalled_jobs = Job.query.filter(Job.status == 'running', Job.started_at < cutoff).all()
    
    for job in stalled_jobs:
        print(f"[Worker] Failing stalled job {job.id}")
        job.status = 'failed'
        job.error = f"Job timed out after {STALL_TIMEOUT_MINUTES} minutes"
        job.completed_at = datetime.utcnow()
    
    if stalled_jobs:
        db.session.commit()

def process_job(job):
    print(f"[Worker] Processing job {job.id} (user={job.user_id}, type={job.type})")
    job.status = 'running'
    job.started_at = datetime.utcnow()
    db.session.commit()
    
    try:
        if job.type == 'analysis':
            input_data = json.loads(job.input_data)
            csv_path = input_data.get('csv_path')
            user_id = job.user_id
            
            # Paths
            script_path = os.path.join(server_path, 'core', 'run_analysis.py')
            output_dir = str(config.get_user_sessions_dir(user_id))
            tracks_dir = str(config.get_user_tracks_dir(user_id))
            
            # Execute subprocess identically as before
            print(f"[Worker] Running analysis on {csv_path}...")
            result = subprocess.run([
                sys.executable, script_path, csv_path,
                '--output', output_dir,
                '--tracks', tracks_dir
            ], capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                print(f"[Worker] Job {job.id} completed successfully.")
                job.status = 'complete'
                job.result = json.dumps({
                    "message": "Session processed successfully",
                    "output": result.stdout
                })
                # Register the session directly through the main.py method
                try:
                    register_new_sessions(user_id)
                except Exception as reg_err:
                    print(f"[Worker] register_new_sessions failed for user {user_id}: {reg_err}")
                
            else:
                print(f"[Worker] Job {job.id} failed with return code {result.returncode}")
                job.status = 'failed'
                job.error = result.stderr
        
        else:
            job.status = 'failed'
            job.error = f"Unknown job type: {job.type}"
            
    except subprocess.TimeoutExpired:
        print(f"[Worker] Job {job.id} timed out during subprocess execution")
        job.status = 'failed'
        job.error = "Processing timeout (exceeded 60 seconds)"
    except Exception as e:
        print(f"[Worker] Job {job.id} encountered exception: {e}")
        job.status = 'failed'
        job.error = str(e)
    
    finally:
        job.completed_at = datetime.utcnow()
        try:
            db.session.commit()
            print(f"[Worker] Job {job.id} finalized with status {job.status}")
        except Exception as e:
            print(f"[Worker] DB commit failed finalizing job {job.id}: {e}")
            db.session.rollback()

def run_worker():
    with app.app_context():
        # Make sure DB schema contains Job
        db.create_all()
        
        while True:
            try:
                # 1. Clean up stalled jobs
                check_stalled_jobs()
                
                # 2. Pick up the next job
                job = Job.query.filter_by(status='queued').order_by(Job.created_at.asc()).first()
                
                if job:
                    process_job(job)
                else:
                    # Sleep briefly to avoid high CPU usage
                    time.sleep(2)
                    
            except KeyboardInterrupt:
                print("[Worker] Shutting down...")
                break
            except Exception as e:
                print(f"[Worker] Error in worker loop: {e}")
                time.sleep(5) # Backoff

if __name__ == '__main__':
    run_worker()
