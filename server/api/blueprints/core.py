from flask import Blueprint, jsonify, request, send_file, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
import os
import json
from datetime import datetime

from api.models import db, User, Job
from api.blueprints.devices import _resolve_upload_user
import api.config as config
import subprocess
import sys
from api.helpers import register_new_sessions
import traceback

core_bp = Blueprint('core_bp', __name__)

@core_bp.route('/')
@core_bp.route('/shared/<token>')
@core_bp.route('/community')
def index(token=None):
    """Serve the companion app"""
    return send_file(os.path.join(current_app.static_folder, 'index.html'))

@core_bp.route('/api/health')
@core_bp.route('/api/status') # Alias for frontend
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "version": "1.0",
        "timestamp": datetime.now().isoformat(),
        "is_recording": False # Mock for now
    })

@core_bp.route('/api/jobs', methods=['GET'])
@jwt_required()
def get_jobs():
    user_id = get_jwt_identity()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    jobs = Job.query.filter_by(user_id=user_id).order_by(Job.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        "jobs": [j.to_dict() for j in jobs.items],
        "total": jobs.total,
        "page": page,
        "pages": jobs.pages
    })

@core_bp.route('/api/jobs/<job_id>', methods=['GET'])
@jwt_required()
def get_job(job_id):
    user_id = get_jwt_identity()
    job = Job.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "Job not found"}), 404
        
    return jsonify(job.to_dict())

@core_bp.route('/api/upload', methods=['POST'])
def upload_file():
    """Receiver for CSV uploads from ESP32 (Device Token) or Browser (JWT)"""
    user_id, error, device_token = _resolve_upload_user()
    if error:
        return jsonify({"error": error}), 401

    try:
        data = request.get_json()
        filename = data.get('filename')
        content = data.get('content')

        if not filename or not content:
            return jsonify({"error": "filename and content required"}), 400

        safe_name = os.path.basename(filename)
        if not safe_name.lower().endswith('.csv'):
             safe_name += '.csv'

        save_path = config.get_user_learning_dir(user_id) / safe_name

        with open(save_path, 'w') as f:
            f.write(content)

        # Server-side rename: extract first GPS timestamp from CSV data
        # Device sends simple counter names (sess_001.csv), server renames
        # to sess_<unix_timestamp>.csv using the first GPS timestamp
        final_name = safe_name
        try:
            lines = content.strip().split('\n')
            if len(lines) >= 2:
                first_data = lines[1].split(',')
                gps_ts = first_data[0]  # e.g., "070226_123519" (ddmmyy_HHMMSS)
                if '_' in gps_ts and len(gps_ts) >= 13:
                    dd, mm, yy = int(gps_ts[0:2]), int(gps_ts[2:4]), int(gps_ts[4:6])
                    hh, mi, ss = int(gps_ts[7:9]), int(gps_ts[9:11]), int(gps_ts[11:13])
                    year = 2000 + yy
                    dt = datetime(year, mm, dd, hh, mi, ss)
                    unix_ts = int(dt.timestamp())
                    new_name = f"sess_{unix_ts}.csv"
                    new_path = config.get_user_learning_dir(user_id) / new_name
                    if not new_path.exists():
                        os.rename(str(save_path), str(new_path))
                        final_name = new_name
                        print(f"[Upload] Renamed {safe_name} -> {new_name}")
        except Exception as rename_err:
            print(f"[Upload] Rename skipped: {rename_err}")

        # Phase 2: Save the file for manual processing on the 'Analyze' tab.
        print(f"[Upload] Saved {final_name} to learning folder for user {user_id}")

        # Update last_sync on device token
        if device_token:
            device_token.last_sync = datetime.utcnow()
            db.session.commit()

        return jsonify({"success": True, "filename": final_name})

    except Exception as e:
        print(f"Upload Error: {e}")
        if os.environ.get('FLASK_ENV', 'development') == 'production':
            return jsonify({"error": "Upload failed"}), 500
        return jsonify({"error": str(e)}), 500


