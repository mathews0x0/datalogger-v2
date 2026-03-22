from flask import Blueprint, jsonify, request
from api.auth_utils import get_current_user_id
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request, jwt_required
import requests
import json
import os
import ipaddress

from api.models import db, Job
from api.decorators import local_only
import api.config as config

sync_bp = Blueprint('sync', __name__)

@sync_bp.route('/api/sync/device', methods=['POST'])
@local_only
@jwt_required()
def sync_from_device():
    """Pull session files from the ESP32 MiniServer and save them locally.
    
    The web UI sends: { "ip": "192.168.1.X" }
    This endpoint:
      1. Hits http://<ip>/list to get available session files
      2. Downloads each file via http://<ip>/download/<filename>
      3. Saves to LEARNING_DIR
      4. Deletes from ESP32 via http://<ip>/delete/<filename>
      5. Triggers auto-analysis on each file
    """
    data = request.get_json()
    ip = data.get('ip') if data else None

    if not ip:
        return jsonify({"error": "Missing device IP"}), 400

    import ipaddress
    try:
        addr = ipaddress.ip_address(ip)
        # Block cloud metadata, loopback, and link-local
        if addr.is_loopback or addr.is_link_local or str(addr).startswith('169.254'):
            return jsonify({"error": "Invalid device IP"}), 400
    except ValueError:
        return jsonify({"error": "Invalid IP address format"}), 400

    base_url = f"http://{ip}"
    synced = []
    failed = []

    try:
        # 1. Get file list from ESP32
        list_resp = requests.get(f"{base_url}/list", timeout=5)
        if list_resp.status_code != 200:
            return jsonify({"error": "The device returned an unexpected error. Please try restarting it."}), 400
        
        files = list_resp.json().get('files', [])
        if not files:
            return jsonify({"success": True, "synced": [], "failed": [], "message": "No files on device"})

        # Resolve user from session/JWT (optional - allow anonymous in dev)
        user_id = None
        try:
            verify_jwt_in_request(optional=True)
            user_id = get_current_user_id()
            if user_id:
                user_id = int(user_id)
        except:
            pass

        # 2. Download each file
        for fname in files:
            try:
                dl_resp = requests.get(f"{base_url}/download/{fname}", timeout=10)
                if dl_resp.status_code != 200:
                    failed.append(fname)
                    continue
                
                content = dl_resp.text
                if not content or len(content.strip()) < 10:
                    # Skip empty/header-only files
                    # Still delete from device to clean up
                    try:
                        requests.get(f"{base_url}/delete/{fname}", timeout=5)
                    except:
                        pass
                    continue

                # Save to user-specific learning directory
                safe_name = os.path.basename(fname)
                if not safe_name.lower().endswith('.csv'):
                    safe_name += '.csv'
                
                save_path = config.get_user_learning_dir(user_id) / safe_name
                with open(save_path, 'w') as f:
                    f.write(content)
                
                print(f"[Sync] Downloaded: {fname} ({len(content)} bytes)")

                # Queue analysis job
                if user_id:
                    try:
                        job = Job(
                            user_id=user_id,
                            type='analysis',
                            input_data=json.dumps({"csv_path": str(save_path)})
                        )
                        db.session.add(job)
                        db.session.commit()
                        print(f"[Sync] Queued job {job.id} for {fname}")
                    except Exception as ae:
                        print(f"[Sync] Job queue error for {fname}: {ae}")

                # Delete from device after successful save
                try:
                    requests.get(f"{base_url}/delete/{fname}", timeout=5)
                except:
                    pass

                synced.append(fname)

            except Exception as e:
                print(f"[Sync] Failed to download {fname}: {e}")
                failed.append(fname)

        return jsonify({
            "success": True,
            "synced": synced,
            "failed": failed,
            "total": len(files)
        })

    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Unable to establish a connection with the device. Please verify it is powered on and in range."}), 400
    except requests.exceptions.Timeout:
        return jsonify({"error": "The device connection timed out. Please bring it closer to the router and try again."}), 400
    except Exception as e:
        print(f"[Sync] Error: {e}")
        return jsonify({"error": "An unexpected error occurred while communicating with the device."}), 400



