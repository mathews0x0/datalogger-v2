from flask import Blueprint, jsonify, request, send_file, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
import os
import json
from datetime import datetime
import threading

from api.models import db, User, Job
from api.blueprints.devices import _resolve_upload_user
import api.config as config
import subprocess
import sys
from api.helpers import register_new_sessions
import traceback

core_bp = Blueprint('core_bp', __name__)


def _pick_session_name(content, learning_dir):
    """Name sessions using current server time once the CSV matches the current firmware shape."""
    try:
        for raw_line in content.splitlines()[1:]:
            parts = raw_line.split(',')
            if len(parts) < 13:
                continue

            row_type = parts[1].strip()
            lat = parts[8].strip()
            lon = parts[9].strip()
            if row_type == 'G' and lat and lon:
                break
    except Exception:
        pass

    session_ts = int(datetime.utcnow().timestamp())

    base_name = f"sess_{session_ts}"
    candidate = f"{base_name}.csv"
    counter = 1
    while (learning_dir / candidate).exists():
        candidate = f"{base_name}_{counter}.csv"
        counter += 1
    return candidate

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

        final_name = safe_name
        try:
            new_name = _pick_session_name(content, config.get_user_learning_dir(user_id))
            if new_name != safe_name:
                new_path = config.get_user_learning_dir(user_id) / new_name
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


import shutil

@core_bp.route('/api/upload/chunk', methods=['POST'])
def upload_chunk():
    """Receive a single chunk of a session file from ESP32.
    Metadata is passed in headers to avoid JSON overhead on the device.
    """
    user_id, error, device_token = _resolve_upload_user()
    if error:
        return jsonify({"error": error}), 401

    try:
        filename = request.headers.get('X-Filename', '')
        chunk_index = request.headers.get('X-Chunk-Index', '')
        total_size = request.headers.get('X-Total-Size', '0')

        if not filename or chunk_index == '':
            return jsonify({"error": "X-Filename and X-Chunk-Index headers required"}), 400

        chunk_index = int(chunk_index)
        safe_name = os.path.basename(filename)

        # Create temp chunk directory: learning/.chunks/<filename>/
        chunk_dir = config.get_user_learning_dir(user_id) / '.chunks' / safe_name
        chunk_dir.mkdir(parents=True, exist_ok=True)

        # Write chunk file (idempotent — re-sending same index overwrites)
        chunk_path = chunk_dir / f'chunk_{chunk_index:04d}'
        data = request.get_data()

        with open(chunk_path, 'wb') as f:
            f.write(data)

        # Record progress for UI
        if device_token:
            device_token.is_syncing = True
            device_token.last_sync_filename = safe_name
            device_token.last_sync_chunk = chunk_index
            # We assume the caller might send total chunks in a header if we updated it,
            # otherwise we just track the index.
            total_chunks = request.headers.get('X-Total-Chunks')
            if total_chunks:
                device_token.last_sync_total = int(total_chunks)
                
            # Global progress tracking
            global_prog = request.headers.get('X-Global-Progress')
            if global_prog:
                device_token.sync_global_current = int(global_prog)
            global_tot = request.headers.get('X-Global-Total')
            if global_tot:
                device_token.sync_global_total = int(global_tot)
            tot_files = request.headers.get('X-Total-Files')
            if tot_files:
                device_token.sync_total_files = int(tot_files)
            file_idx = request.headers.get('X-File-Index')
            if file_idx:
                device_token.sync_current_file_index = int(file_idx)
            
            device_token.last_sync = datetime.utcnow()
            
            last_chunk_index = -1
            if device_token.last_sync_total:
                last_chunk_index = device_token.last_sync_total - 1
                
            if chunk_index % 20 == 0 or chunk_index == last_chunk_index:
                db.session.commit()

        return jsonify({"received": True, "chunk_index": chunk_index, "bytes": len(data)})

    except Exception as e:
        print(f"Chunk Upload Error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@core_bp.route('/api/upload/complete', methods=['POST'])
def upload_complete():
    """Reassemble chunks into final CSV file.
    Called by ESP32 after all chunks are sent.
    """
    user_id, error, device_token = _resolve_upload_user()
    if error:
        return jsonify({"error": error}), 401

    try:
        data = request.get_json()
        filename = data.get('filename', '')
        total_chunks = data.get('total_chunks', 0)

        if not filename or total_chunks <= 0:
            return jsonify({"error": "filename and total_chunks required"}), 400

        safe_name = os.path.basename(filename)
        learning_dir = config.get_user_learning_dir(user_id)
        chunk_dir = learning_dir / '.chunks' / safe_name

        # Validate all chunks exist
        for i in range(total_chunks):
            chunk_path = chunk_dir / f'chunk_{i:04d}'
            if not chunk_path.exists():
                return jsonify({"error": f"Missing chunk {i}"}), 400

        # Reassemble into final file
        if not safe_name.lower().endswith('.csv'):
            safe_name += '.csv'

        save_path = learning_dir / safe_name

        with open(save_path, 'wb') as out_f:
            for i in range(total_chunks):
                chunk_path = chunk_dir / f'chunk_{i:04d}'
                with open(chunk_path, 'rb') as chunk_f:
                    out_f.write(chunk_f.read())

        # Clean up chunk dir
        shutil.rmtree(str(chunk_dir), ignore_errors=True)

        final_name = safe_name
        try:
            with open(save_path, 'r') as f:
                content = f.read()
            new_name = _pick_session_name(content, learning_dir)
            if new_name != safe_name:
                new_path = learning_dir / new_name
                os.rename(str(save_path), str(new_path))
                final_name = new_name
                print(f"[Upload] Renamed {safe_name} -> {new_name}")
        except Exception as rename_err:
            print(f"[Upload] Rename skipped: {rename_err}")

        print(f"[Upload] Assembled {final_name} from {total_chunks} chunks for user {user_id}")

        # Update last_sync on device token
        if device_token:
            device_token.last_sync = datetime.utcnow()
            
            # Reset global progress if this is the last file (or if we lost track)
            if device_token.sync_current_file_index is not None and device_token.sync_total_files:
                if device_token.sync_current_file_index >= device_token.sync_total_files - 1:
                    device_token.is_syncing = False
                    device_token.sync_global_current = 0
                    device_token.sync_global_total = 0
            else:
                 device_token.is_syncing = False
                 
            db.session.commit()

        return jsonify({"success": True, "filename": final_name})

    except Exception as e:
        print(f"Upload Complete Error: {e}")
        traceback.print_exc()
        if device_token:
            try:
                device_token.is_syncing = False
                db.session.commit()
            except Exception as reset_err:
                print(f"Failed to reset is_syncing: {reset_err}")
                db.session.rollback()
        if os.environ.get('FLASK_ENV', 'development') == 'production':
            return jsonify({"error": "Assembly failed"}), 500
        return jsonify({"error": str(e)}), 500
