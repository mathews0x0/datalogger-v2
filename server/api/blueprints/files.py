from flask import Blueprint, jsonify, request, send_file, Response, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from api.auth_utils import get_current_user_id
import os
import io
import json

import sys
import subprocess
import uuid

from api.models import db, User, Job, SessionMeta
from core.file_manager import FileManager
import api.config as config
from api.helpers import get_track_folder

files_bp = Blueprint('files', __name__)

@files_bp.route('/api/process', methods=['POST'])
@jwt_required()
def process_session():
    """Process a learning CSV file"""
    user_id = get_current_user_id()
    user = User.query.get(user_id)
    
    # Check session limit for free users
    if user.subscription_tier == 'free':
        count = SessionMeta.query.filter_by(user_id=user_id).count()
        if count >= 5:
            return jsonify({
                "error": "Limit reached",
                "message": "Free tier is limited to 5 processed sessions. Please upgrade to Pro for unlimited storage.",
                "used": count,
                "max": 5
            }), 403

    data = request.get_json()
    filename = data.get('filename') or data.get('csv_file') # support legacy
    
    if not filename:
        return jsonify({"error": "filename required"}), 400
    
    # Sandbox enforcement
    safe_name = os.path.basename(filename)
    csv_path = config.get_user_learning_dir(user_id) / safe_name
    
    if not csv_path.exists():
        return jsonify({"error": "File not found"}), 404
    
    # Check if already processed (unless force=True)
    force = data.get('force', False)
    if not force:
        # 1. Check if it's currently queued or running
        active_jobs = Job.query.filter(Job.user_id == user_id, Job.status.in_(['queued', 'running'])).all()
        for j in active_jobs:
            try:
                jdata = json.loads(j.input_data)
                if 'csv_path' in jdata and os.path.basename(jdata['csv_path']) == safe_name:
                    return jsonify({
                        "status": "already_processed",
                        "message": f"{safe_name} is currently processing in the background",
                        "job_id": j.id
                    })
            except Exception:
                pass

        # 2. Check completed sessions
        sessions_dir = config.get_user_sessions_dir(user_id)
        if sessions_dir.exists():
            for sfile in os.listdir(sessions_dir):
                if sfile.endswith('.json') and not sfile.endswith('_telemetry.json'):
                    try:
                        with open(sessions_dir / sfile, 'r') as f:
                            sdata = json.load(f)
                            if os.path.basename(sdata.get('meta', {}).get('source_file', '')) == safe_name:
                                return jsonify({
                                    "status": "already_processed",
                                    "message": f"{safe_name} has already been analyzed",
                                    "session_id": sdata.get('meta', {}).get('session_id')
                                })
                    except Exception:
                        continue
    
    # Queue analysis job
    try:
        job = Job(
            user_id=user_id,
            type='analysis',
            input_data=json.dumps({"csv_path": str(csv_path)})
        )
        db.session.add(job)
        db.session.commit()
        return jsonify({
            "status": "queued",
            "job_id": job.id,
            "message": "Analysis queued"
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            "status": "error",
            "message": f"Failed to queue job: {str(e)}"
        }), 500


@files_bp.route('/api/learning/list')
@jwt_required()
def list_learning_files():
    """List learning CSV files with metadata"""
    user_id = get_current_user_id()
    user_file_mgr = FileManager(base_dir=config.get_user_learning_dir(user_id))
    archived = request.args.get('archived', 'false').lower() == 'true'
    return jsonify(user_file_mgr.get_files(archived=archived))

@files_bp.route('/api/learning/<filename>/lock', methods=['POST'])
@jwt_required()
def lock_learning_file(filename):
    user_id = get_current_user_id()
    user_file_mgr = FileManager(base_dir=config.get_user_learning_dir(user_id))
    data = request.json
    locked = data.get('locked', True)
    if user_file_mgr.set_lock(filename, locked):
        return jsonify({"success": True, "locked": locked})
    return jsonify({"error": "Failed to update lock"}), 500

@files_bp.route('/api/learning/delete', methods=['POST'])
@jwt_required()
def delete_learning_files():
    """Permanent Bulk Delete"""
    user_id = get_current_user_id()
    user_file_mgr = FileManager(base_dir=config.get_user_learning_dir(user_id))
    data = request.json
    filenames = data.get('files', [])
    from_archive = data.get('from_archive', False)
    if not filenames:
        return jsonify({"error": "No files specified"}), 400
        
    result = user_file_mgr.delete_files(filenames, from_archive=from_archive)
    return jsonify(result)

@files_bp.route('/api/learning/archive', methods=['POST'])
@jwt_required()
def archive_learning_files():
    """Soft delete - Move to archive"""
    user_id = get_current_user_id()
    user_file_mgr = FileManager(base_dir=config.get_user_learning_dir(user_id))
    data = request.json
    filenames = data.get('files', [])
    if not filenames:
        return jsonify({"error": "No files specified"}), 400
        
    result = user_file_mgr.archive_files(filenames)
    return jsonify(result)

@files_bp.route('/api/learning/restore', methods=['POST'])
@jwt_required()
def restore_learning_files():
    """Restore from archive"""
    user_id = get_current_user_id()
    user_file_mgr = FileManager(base_dir=config.get_user_learning_dir(user_id))
    data = request.json
    filenames = data.get('files', [])
    if not filenames:
        return jsonify({"error": "No files specified"}), 400
        
    result = user_file_mgr.restore_files(filenames)
    return jsonify(result)

@files_bp.route('/api/learning/<filename>/raw')
@jwt_required()
def get_learning_file_raw(filename):
    """Get raw head of file"""
    user_id = get_current_user_id()
    user_file_mgr = FileManager(base_dir=config.get_user_learning_dir(user_id))
    lines = request.args.get('lines', 100, type=int)
    return jsonify(user_file_mgr.read_file_head(filename, lines))

@files_bp.route('/api/learning/<filename>/geo')
@jwt_required()
def get_learning_file_geo(filename):
    """Get Geo Path for Visualization"""
    user_id = get_current_user_id()
    user_file_mgr = FileManager(base_dir=config.get_user_learning_dir(user_id))
    return jsonify(user_file_mgr.extract_geo_path(filename))

@files_bp.route('/api/learning/processed')
@jwt_required()
def get_processed_files():
    """Returns set of source filenames that have already been processed into sessions."""
    user_id = get_current_user_id()
    sessions_dir = config.get_user_sessions_dir(user_id)
    processed = set()
    
    if sessions_dir.exists():
        for filename in os.listdir(sessions_dir):
            if filename.endswith('.json') and not filename.endswith('_telemetry.json'):
                try:
                    with open(sessions_dir / filename, 'r') as f:
                        data = json.load(f)
                        source_file = data.get('meta', {}).get('source_file')
                        if source_file:
                            processed.add(os.path.basename(source_file))
                except Exception:
                    continue
    
    return jsonify(list(processed))

@files_bp.route('/api/process/all', methods=['POST'])
@jwt_required()
def process_all_files():
    """Process all unprocessed learning files, or specific files if provided."""
    user_id = get_current_user_id()
    user = User.query.get(user_id)
    
    # Get already processed files for this user
    processed_count = SessionMeta.query.filter_by(user_id=user_id).count()
    
    # Build set of source filenames that have already been processed or are in queue
    already_processed = set()
    
    # 1. Check actively queued or running jobs
    active_jobs = Job.query.filter(Job.user_id == user_id, Job.status.in_(['queued', 'running'])).all()
    for j in active_jobs:
        try:
            jdata = json.loads(j.input_data)
            if 'csv_path' in jdata:
                already_processed.add(os.path.basename(jdata['csv_path']))
        except Exception:
            pass

    # 2. Check completed sessions
    sessions_dir = config.get_user_sessions_dir(user_id)
    if sessions_dir.exists():
        for fname in os.listdir(sessions_dir):
            if fname.endswith('.json') and not fname.endswith('_telemetry.json'):
                try:
                    with open(sessions_dir / fname, 'r') as f:
                        sdata = json.load(f)
                        source_file = sdata.get('meta', {}).get('source_file')
                        if source_file:
                            already_processed.add(os.path.basename(source_file))
                except Exception:
                    continue
    
    # Check if specific files were requested
    data = request.get_json() or {}
    requested_files = data.get('files', None)  # Optional list of specific files
    force = data.get('force', False)
    
    # Get list of learning files
    user_file_mgr = FileManager(base_dir=config.get_user_learning_dir(user_id))
    files = user_file_mgr.get_files()
    all_files = requested_files if requested_files else [f['filename'] for f in files]
    
    # Filter out already-processed files (unless explicit force flag)
    if not force:
        to_process = [f for f in all_files if f not in already_processed]
    else:
        to_process = all_files
    
    skipped = len(all_files) - len(to_process)

    # Limit check for free tier
    if user.subscription_tier == 'free':
        if processed_count >= 5:
             return jsonify({
                "error": "Limit reached",
                "message": "Free tier is limited to 5 processed sessions.",
                "used": processed_count,
                "max": 5
            }), 403
        
        # Only process up to the limit
        remaining = 5 - processed_count
        if len(to_process) > remaining:
            to_process = to_process[:remaining]
    
    if not to_process:
        return jsonify({
            "status": "complete",
            "message": f"No new files to process ({skipped} already analyzed)",
            "processed": 0,
            "failed": 0,
            "skipped": skipped,
            "details": {"success": [], "failed": []}
        })
    
    results = {"success": [], "failed": [], "job_ids": []}
    
    for filename in to_process:
        csv_path = config.get_user_learning_dir(user_id) / filename
        try:
            job = Job(
                user_id=user_id,
                type='analysis',
                input_data=json.dumps({"csv_path": str(csv_path)})
            )
            db.session.add(job)
            db.session.flush()
            results["success"].append(filename)
            results["job_ids"].append(str(job.id))
        except Exception as e:
            results["failed"].append({"filename": filename, "error": str(e)})
    
    db.session.commit()
    
    return jsonify({
        "status": "queued",
        "message": f"Queued {len(results['success'])} files ({skipped} already analyzed)",
        "queued": len(results["success"]),
        "failed": len(results["failed"]),
        "skipped": skipped,
        "details": results
    })

# ============================================================================
# ERROR HANDLERS
# ============================================================================


@files_bp.route('/api/learning/rename', methods=['POST'])
@jwt_required()
def rename_learning_file():
    """Rename raw CSV file (safely)"""
    try:
        data = request.json
        old_name = data.get('old_name')
        new_name = data.get('new_name')
        
        if not old_name or not new_name:
            return jsonify({"error": "Missing parameters"}), 400
            
        old_name = os.path.basename(old_name)
        new_name = os.path.basename(new_name)
        
        # Prevent extension change? Or enforce .csv?
        if not new_name.lower().endswith('.csv'):
            new_name += '.csv'
            
        user_id = get_current_user_id()
        user_learning_dir = config.get_user_learning_dir(user_id)
        src = user_learning_dir / old_name
        dst = user_learning_dir / new_name
        
        if not src.exists():
            return jsonify({"error": "Source file not found"}), 404
            
        if dst.exists():
            return jsonify({"error": "A file with that name already exists"}), 400
            
        os.rename(src, dst)
        return jsonify({"success": True, "new_name": new_name})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

