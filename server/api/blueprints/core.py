from flask import Blueprint, jsonify, request, send_file, current_app
from api.auth_utils import get_current_user_id
from flask_jwt_extended import jwt_required, get_jwt_identity
import os
import json
import re
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
    """Name sessions using sequential numbers (sess_01.csv) instead of UNIX timestamps."""
    import re
    max_num = 0
    try:
        if learning_dir.exists():
            for fname in os.listdir(learning_dir):
                if fname.startswith("sess_") and fname.endswith(".csv"):
                    match = re.search(r'^sess_(\d+)', fname)
                    if match:
                        num = int(match.group(1))
                        if num > max_num:
                            max_num = num
    except Exception:
        pass

    next_num = max_num + 1
    base_name = f"sess_{next_num:02d}"
    candidate = f"{base_name}.csv"
    counter = 1
    while (learning_dir / candidate).exists():
        candidate = f"sess_{next_num:02d}_{counter}.csv"
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
        "version": config.get_app_version(),
        "timestamp": datetime.now().isoformat(),
        "is_recording": False # Mock for now
    })

@core_bp.route('/api/jobs', methods=['GET'])
@jwt_required()
def get_jobs():
    user_id = get_current_user_id()
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
    user_id = get_current_user_id()
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
            
            # Auto-queue analysis if enabled (treating None as True for migrated tokens)
            auto_enabled = getattr(device_token, 'auto_analyse', True)
            if auto_enabled is not False:
                try:
                    from api.models import Job
                    job = Job(
                        user_id=user_id,
                        type='analysis',
                        input_data=json.dumps({"csv_path": str(config.get_user_learning_dir(user_id) / final_name)})
                    )
                    db.session.add(job)
                    print(f"[Upload] Auto-queued analysis for {final_name}")
                except Exception as auto_err:
                    print(f"[Upload] Failed to auto-queue analysis: {auto_err}")
                    
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

    Fast-path: When chunks arrive in order (chunk 0, 1, 2...), appends
    directly to a .partial staging file — avoids per-chunk file creation
    and the final reassembly step.

    Fallback: Out-of-order or retransmitted chunks use individual chunk
    files for resumability.
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
        learning_dir = config.get_user_learning_dir(user_id)

        data = request.get_data()

        # --- Fast-path: append-mode when chunks arrive in order ---
        partial_path = learning_dir / '.chunks' / (safe_name + '.partial')
        tracker_path = learning_dir / '.chunks' / (safe_name + '.next')
        chunk_dir = learning_dir / '.chunks' / safe_name

        # Read expected next chunk index from tracker
        expected_next = 0
        if tracker_path.exists():
            try:
                expected_next = int(tracker_path.read_text().strip())
            except (ValueError, OSError):
                expected_next = 0

        if chunk_index == expected_next:
            # Fast-path: append directly to .partial file
            (learning_dir / '.chunks').mkdir(parents=True, exist_ok=True)
            with open(partial_path, 'ab') as f:
                f.write(data)
            # Update tracker
            tracker_path.write_text(str(chunk_index + 1))
        else:
            # Fallback: write individual chunk file (out-of-order or retry)
            chunk_dir.mkdir(parents=True, exist_ok=True)
            chunk_path = chunk_dir / f'chunk_{chunk_index:04d}'
            with open(chunk_path, 'wb') as f:
                f.write(data)

        # Record progress for UI
        if device_token:
            device_token.is_syncing = True
            device_token.last_sync_filename = safe_name
            device_token.last_sync_chunk = chunk_index
            total_chunks = request.headers.get('X-Total-Chunks')
            if total_chunks:
                device_token.last_sync_total = int(total_chunks)

            # Global progress tracking (only sent on some chunks)
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


@core_bp.route('/api/upload/batch', methods=['POST'])
def upload_batch():
    """Receive a batch (~512KB) of a file, streamed from ESP32 in 32KB reads.

    The firmware sets Content-Length to the batch size and streams multiple
    small reads from flash into a single HTTP request body.  This eliminates
    the per-chunk round-trip overhead that dominated upload time.

    Headers:
        X-Filename:        session filename
        X-Offset:          byte offset in the file (for resume)
        X-Total-Size:      total file size in bytes
        Content-Length:    size of this batch
        + optional global progress headers (same as chunk endpoint)
    """
    user_id, error, device_token = _resolve_upload_user()
    if error:
        return jsonify({"error": error}), 401

    try:
        filename = request.headers.get('X-Filename', '')
        offset = int(request.headers.get('X-Offset', '0'))
        total_size = int(request.headers.get('X-Total-Size', '0'))
        content_length = request.content_length or 0

        if not filename or content_length <= 0:
            return jsonify({"error": "X-Filename and Content-Length required"}), 400
        if offset < 0 or total_size <= 0 or offset > total_size or \
                content_length > total_size - offset:
            return jsonify({"error": "Invalid upload offset or total size"}), 400

        safe_name = os.path.basename(filename)
        learning_dir = config.get_user_learning_dir(user_id)
        chunks_dir = learning_dir / '.chunks'
        chunks_dir.mkdir(parents=True, exist_ok=True)
        partial_path = chunks_dir / (safe_name + '.partial')

        # Batches are strictly sequential. This prevents a bad resume offset
        # from creating a sparse file or silently corrupting the session.
        if offset > 0:
            if not partial_path.exists() or partial_path.stat().st_size != offset:
                return jsonify({"error": "Upload offset does not match server state"}), 409

        # Stream request body to .partial file at the correct offset
        bytes_written = 0
        mode = 'r+b' if partial_path.exists() and offset > 0 else 'wb'
        with open(partial_path, mode) as f:
            f.seek(offset)
            while bytes_written < content_length:
                read_size = min(65536, content_length - bytes_written)
                block = request.stream.read(read_size)
                if not block:
                    break
                f.write(block)
                bytes_written += len(block)

        if bytes_written != content_length:
            return jsonify({"error": "Request body shorter than Content-Length"}), 400

        new_offset = offset + bytes_written

        # Update tracker for /complete fast-path compatibility
        tracker_path = chunks_dir / (safe_name + '.next')
        tracker_path.write_text(str(new_offset))

        # Update device progress once per batch
        if device_token:
            device_token.is_syncing = True
            device_token.last_sync_filename = safe_name
            device_token.last_sync = datetime.utcnow()

            if total_size > 0:
                device_token.last_sync_total = total_size
                device_token.last_sync_chunk = new_offset

            # Global progress headers (same as chunk endpoint)
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

            db.session.commit()

        return jsonify({"received": True, "offset": new_offset, "bytes": bytes_written})

    except Exception as e:
        print(f"Batch Upload Error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@core_bp.route('/api/upload/status', methods=['GET'])
def upload_status():
    """Return resumable upload state for a given filename."""
    user_id, error, device_token = _resolve_upload_user()
    if error:
        return jsonify({"error": error}), 401

    filename = request.args.get('filename', '')
    if not filename:
        return jsonify({"error": "filename required"}), 400

    safe_name = os.path.basename(filename)
    learning_dir = config.get_user_learning_dir(user_id)
    chunk_dir = learning_dir / '.chunks' / safe_name

    # Check for batch-mode partial file (byte-offset resume)
    partial_path = learning_dir / '.chunks' / (safe_name + '.partial')
    received_bytes = 0
    if partial_path.exists():
        received_bytes = partial_path.stat().st_size

    if not chunk_dir.exists() and received_bytes == 0:
        return jsonify({
            "filename": safe_name,
            "next_chunk": 0,
            "chunk_size": 0,
            "received_chunks": 0,
            "received_bytes": 0,
        })

    chunk_files = sorted(chunk_dir.glob('chunk_*')) if chunk_dir.exists() else []
    present = set()
    chunk_size = 0
    for path in chunk_files:
        try:
            idx = int(path.name.split('_')[1])
            present.add(idx)
            if idx == 0:
                chunk_size = path.stat().st_size
        except Exception:
            continue

    next_chunk = 0
    while next_chunk in present:
        next_chunk += 1

    return jsonify({
        "filename": safe_name,
        "next_chunk": next_chunk,
        "chunk_size": chunk_size,
        "received_chunks": len(present),
        "received_bytes": received_bytes,
    })


@core_bp.route('/api/upload/complete', methods=['POST'])
def upload_complete():
    """Finalize a chunked upload.

    Fast-path: If all chunks were appended in order, the .partial file
    IS the complete file — just rename it. No read/reassembly needed.

    Fallback: If some chunks went through per-file storage, assemble
    from individual chunk files as before.
    """
    user_id, error, device_token = _resolve_upload_user()
    if error:
        return jsonify({"error": error}), 401

    try:
        data = request.get_json()
        filename = data.get('filename', '')
        total_chunks = data.get('total_chunks', 0)
        total_size = data.get('total_size', 0)  # Batch mode sends total_size instead

        if not filename or (total_chunks <= 0 and total_size <= 0):
            return jsonify({"error": "filename and total_chunks (or total_size) required"}), 400

        safe_name = os.path.basename(filename)
        learning_dir = config.get_user_learning_dir(user_id)
        partial_path = learning_dir / '.chunks' / (safe_name + '.partial')
        tracker_path = learning_dir / '.chunks' / (safe_name + '.next')
        chunk_dir = learning_dir / '.chunks' / safe_name

        if not safe_name.lower().endswith('.csv'):
            safe_name += '.csv'

        save_path = learning_dir / safe_name

        # --- Check for fast-path: .partial file has all chunks ---
        partial_complete = False
        if partial_path.exists() and tracker_path.exists():
            try:
                tracker_val = int(tracker_path.read_text().strip())
                if total_size > 0:
                    # Batch mode: tracker stores byte offset
                    if tracker_val == total_size and partial_path.stat().st_size == total_size:
                        partial_complete = True
                elif tracker_val >= total_chunks:
                    # Legacy chunk mode: tracker stores chunk count
                    partial_complete = True
            except (ValueError, OSError):
                pass
        # Also check: batch mode with total_size — partial file size is enough
        if not partial_complete and total_size > 0 and partial_path.exists():
            if partial_path.stat().st_size == total_size:
                partial_complete = True

        if partial_complete:
            # Fast-path: just rename .partial → final file
            os.rename(str(partial_path), str(save_path))
            # Clean up tracker
            try:
                tracker_path.unlink()
            except OSError:
                pass
            print(f"[Upload] Fast-assembled {safe_name} (append-mode, {total_chunks} chunks)")
        else:
            # Fallback: assemble from individual chunk files
            # First, check if any chunks were in the partial file
            partial_chunks = 0
            if tracker_path.exists():
                try:
                    partial_chunks = int(tracker_path.read_text().strip())
                except (ValueError, OSError):
                    partial_chunks = 0

            # Validate remaining chunks exist in chunk_dir
            for i in range(partial_chunks, total_chunks):
                cp = chunk_dir / f'chunk_{i:04d}'
                if not cp.exists():
                    return jsonify({"error": f"Missing chunk {i}"}), 400

            # Build final file: start from partial if it exists, then append remaining
            with open(save_path, 'wb') as out_f:
                if partial_path.exists() and partial_chunks > 0:
                    with open(partial_path, 'rb') as pf:
                        while True:
                            block = pf.read(65536)
                            if not block:
                                break
                            out_f.write(block)
                for i in range(partial_chunks, total_chunks):
                    cp = chunk_dir / f'chunk_{i:04d}'
                    with open(cp, 'rb') as chunk_f:
                        out_f.write(chunk_f.read())

            # Clean up
            if chunk_dir.exists():
                shutil.rmtree(str(chunk_dir), ignore_errors=True)
            try:
                if partial_path.exists():
                    partial_path.unlink()
                if tracker_path.exists():
                    tracker_path.unlink()
            except OSError:
                pass

            print(f"[Upload] Assembled {safe_name} from {total_chunks} chunks (hybrid mode) for user {user_id}")

        # Rename to session timestamp
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

            # Auto-queue analysis if enabled (treating None as True for migrated tokens)
            auto_enabled = getattr(device_token, 'auto_analyse', True)
            if auto_enabled is not False:
                try:
                    from api.models import Job
                    job = Job(
                        user_id=user_id,
                        type='analysis',
                        input_data=json.dumps({"csv_path": str(learning_dir / final_name)})
                    )
                    db.session.add(job)
                    print(f"[Upload] Auto-queued analysis for {final_name}")
                except Exception as auto_err:
                    print(f"[Upload] Failed to auto-queue analysis: {auto_err}")

            db.session.commit()

        return jsonify({"success": True, "filename": final_name})

    except Exception as e:
        print(f"Upload Complete Error: {e}"
        )
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
