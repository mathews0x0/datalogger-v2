"""
Datalogger Companion API Server
Flask backend for companion app
"""

from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
import os
import json
import subprocess
from datetime import datetime
from pathlib import Path
import shutil

# Point to UI folder in same server directory
static_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../ui'))
app = Flask(__name__, static_folder=static_path, static_url_path='')
CORS(app)  # Enable CORS for development

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# Base directory
import config


import time
import sys

# Add core to path for imports
CORE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../core'))
if CORE_PATH not in sys.path:
    sys.path.insert(0, CORE_PATH)

import requests  # Required for device scanning and checking

MIN_ESP_VERSION = "0.0.0"

from update_manager import UpdateManager
FIRMWARE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../firmware'))
update_mgr = UpdateManager(FIRMWARE_DIR)

def get_local_firmware_version():
    try:
        p = os.path.join(FIRMWARE_DIR, 'lib/miniserver.py')
        with open(p, 'r') as f:
            for line in f:
                if 'VERSION =' in line:
                    return line.split('=')[1].strip().replace('"', '').replace("'", "")
    except:
        pass
    return "Unknown"

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def is_compatible(esp_version):
    """Check if ESP firmware meets minimum requirements"""
    if not esp_version: return False
    try:
        # Simple version comparison (e.g. 1.0.2)
        v_parts = [int(p) for p in esp_version.split('.')]
        min_parts = [int(p) for p in MIN_ESP_VERSION.split('.')]
        return v_parts >= min_parts
    except:
        return False



def load_registry():
    """Load registry.json from metadata folder"""
    registry_file = config.METADATA_DIR / "registry.json"
    if not registry_file.exists():
        return {"next_id": 1, "tracks": []}
    
    with open(registry_file, 'r') as f:
        return json.load(f)

def get_track_folder(track_id):
    """Get folder name for track ID from registry"""
    registry = load_registry()
    for track in registry['tracks']:
        if track['track_id'] == track_id:
            return track['folder_name']
    return None

# ============================================================================
# NETWORK HELPERS
# ============================================================================

def robust_get_json(url, timeout=2.0):
    """
    Attempt to get JSON from a URL using curl (subprocess) to avoid python-requests issues.
    """
    # Fallback to subprocess curl
    try:
        # -s = silent, --connect-timeout = seconds
        cmd = ['curl', '-s', '--connect-timeout', str(int(timeout) or 1), url]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+1)
        
        if result.returncode == 0 and result.stdout.strip():
            try:
                return json.loads(result.stdout)
            except:
                pass
    except Exception as e:
        pass
        
    return None

# ============================================================================
# API ROUTES
# ============================================================================

@app.route('/')
def index():
    """Serve the companion app"""
    return send_file(os.path.join(app.static_folder, 'index.html'))

@app.route('/api/health')
@app.route('/api/status') # Alias for frontend
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "ok",
        "version": "1.0",
        "timestamp": datetime.now().isoformat(),
        "is_recording": False # Mock for now
    })

@app.route('/api/tracks')
def get_tracks():
    """Get all tracks from registry"""
    registry = load_registry()
    
    # Enrich with session count
    for track in registry['tracks']:
        folder = track['folder_name']
        session_pattern = f"{folder}_session_"
        sessions_dir = config.SESSIONS_DIR
        
        if sessions_dir.exists():
            sessions = [f for f in os.listdir(sessions_dir) 
                       if f.startswith(session_pattern) and f.endswith('.json')]
            track['sessions_count'] = len(sessions)
        else:
            track['sessions_count'] = 0
    
    return jsonify(registry)

@app.route('/api/tracks/<int:track_id>')
def get_track(track_id):
    """Get track details including TBL"""
    folder = get_track_folder(track_id)
    if not folder:
        return jsonify({"error": "Track not found"}), 404
    
    track_dir = config.TRACKS_DIR / folder
    
    # Load track.json
    track_file = track_dir / "track.json"
    if not track_file.exists():
        return jsonify({"error": "Track data not found"}), 404
    
    with open(track_file, 'r') as f:
        track_data = json.load(f)
    
    # Load tbl.json
    tbl_file = track_dir / "tbl.json"
    tbl_data = None
    if tbl_file.exists():
        with open(tbl_file, 'r') as f:
            tbl_data = json.load(f)
    
    # Count sessions and find all-time best lap
    session_pattern = f"{folder}_session_"
    sessions_dir = config.SESSIONS_DIR
    sessions = []
    best_lap_time = None
    
    if sessions_dir.exists():
        sessions = [f for f in os.listdir(sessions_dir) 
                   if f.startswith(session_pattern) and f.endswith('.json') and not f.endswith('_telemetry.json')]
        
        # Find best lap across all sessions
        for session_file in sessions:
            try:
                session_path = sessions_dir / session_file
                with open(session_path, 'r') as sf:
                    session_data = json.load(sf)
                    if 'summary' in session_data and session_data['summary'].get('best_lap_time'):
                        lap_time = session_data['summary']['best_lap_time']
                        if best_lap_time is None or lap_time < best_lap_time:
                            best_lap_time = lap_time
            except Exception:
                pass  # Skip corrupted session files
    
    return jsonify({
        **track_data,
        "tbl": tbl_data,
        "sessions_count": len(sessions),
        "best_lap_time": best_lap_time
    })

@app.route('/api/tracks/<int:track_id>/map')
def get_track_map(track_id):
    """Get track map image"""
    folder = get_track_folder(track_id)
    if not folder:
        return jsonify({"error": "Track not found"}), 404
    
    map_file = config.TRACKS_DIR / folder / "track_map.png"
    if not map_file.exists():
        return jsonify({"error": "Map not found"}), 404
    
    return send_file(map_file, mimetype='image/png')

@app.route('/api/sessions')
def get_sessions():
    """Get all sessions, optionally filtered by track_id"""
    track_id = request.args.get('track_id', type=int)
    
    sessions_dir = config.SESSIONS_DIR
    if not sessions_dir.exists():
        return jsonify([])
    
    sessions = []
    for filename in os.listdir(sessions_dir):
        if not filename.endswith('.json'):
            continue
        # Skip telemetry files - they're not proper sessions
        if filename.endswith('_telemetry.json'):
            continue
        
        filepath = sessions_dir / filename
        try:
            with open(filepath, 'r') as f:
                session = json.load(f)
            
            # Filter by track_id if provided
            if track_id and session.get('track', {}).get('track_id') != track_id:
                continue
            
            # Extract summary info (handle both old and new formats)
            # Old format: uses 'aggregates', new format: uses 'summary'
            summary = session.get('summary', session.get('aggregates', {}))
            total_laps = summary.get('total_laps', len(session.get('laps', [])))
            best_lap_time = summary.get('best_lap_time', 0)
            tbl_improved = summary.get('tbl_improved', False)
            
            sessions.append({
                'session_id': session.get('meta', {}).get('session_id', filename.replace('.json', '')),
                'session_name': session.get('meta', {}).get('session_name', filename),
                'start_time': session.get('meta', {}).get('start_time', ''),
                'duration_sec': session.get('meta', {}).get('duration_sec', 0),
                'track_id': session.get('track', {}).get('track_id', 0),
                'track_name': session.get('track', {}).get('track_name', 'Unknown'),
                'total_laps': total_laps,
                'best_lap_time': best_lap_time,
                'tbl_improved': tbl_improved
            })
        except Exception as e:
            # Skip malformed session files
            print(f"Warning: Failed to load session {filename}: {e}")
            continue
    
    # Sort by date (newest first)
    sessions.sort(key=lambda x: x['start_time'], reverse=True)
    
    return jsonify(sessions)

@app.route('/api/sessions/<path:session_id>')
def get_session(session_id):
    """Get full session data"""
    sessions_dir = config.SESSIONS_DIR
    
    if not sessions_dir.exists():
        return jsonify({"error": "Sessions directory not found"}), 404
    
    session_data = None
    
    # Try direct match first
    session_file = sessions_dir / f"{session_id}.json"
    
    if session_file.exists():
        with open(session_file, 'r') as f:
            session_data = json.load(f)
    else:
        # Search all files for matching session_id field
        for filename in os.listdir(sessions_dir):
            if not filename.endswith('.json'):
                continue
            
            filepath = sessions_dir / filename
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    if data.get('meta', {}).get('session_id') == session_id:
                        session_data = data
                        break
            except:
                continue
    
    if not session_data:
        return jsonify({"error": "Session not found"}), 404
    
    # Transform old format to new format for frontend compatibility
    if 'summary' not in session_data and 'aggregates' in session_data:
        session_data['summary'] = {
            'total_laps': len(session_data.get('laps', [])),
            'best_lap_time': session_data.get('aggregates', {}).get('best_lap_time', 0),
            'tbl_improved': False
        }
    
    return jsonify(session_data)

@app.route('/api/sessions/<path:session_id>/telemetry')
def get_session_telemetry(session_id):
    """Get full telemetry data for a session"""
    sessions_dir = config.SESSIONS_DIR
    
    # Sanitize inputs? path:session_id usually safe in flask but good to be careful
    # The session_id normally comes from the session filename without .json
    
    telemetry_file = sessions_dir / f"{session_id}_telemetry.json"
    
    if telemetry_file.exists():
        return send_file(telemetry_file, mimetype='application/json')
    
    return jsonify({"error": "Telemetry data not found"}), 404


@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Receiver for ESP32 raw CSV uploads"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        content = data.get('content')
        
        if not filename or not content:
            return jsonify({"error": "filename and content required"}), 400
            
        safe_name = os.path.basename(filename)
        # Enforce .csv extension for safety
        if not safe_name.lower().endswith('.csv'):
             safe_name += '.csv'
             
        save_path = config.LEARNING_DIR / safe_name
        
        # Determine write mode (append if chunked? No, typical upload is one shot for now)
        # ESP32 sends whole file string.
        
        with open(save_path, 'w') as f:
            f.write(content)
            
        return jsonify({"success": True, "filename": safe_name})
        
    except Exception as e:
        print(f"Upload Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/process', methods=['POST'])
def process_session():
    """Process a learning CSV file"""
    data = request.get_json()
    filename = data.get('filename') or data.get('csv_file') # support legacy
    
    if not filename:
        return jsonify({"error": "filename required"}), 400
    
    # Sandbox enforcement
    safe_name = os.path.basename(filename)
    csv_path = config.LEARNING_DIR / safe_name
    
    if not csv_path.exists():
        return jsonify({"error": "File not found"}), 404
    
    # Run analysis script
    try:
        # Locate script in our core folder
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../core/run_analysis.py'))
        
        result = subprocess.run([
            'python3', script_path, str(csv_path)
        ], capture_output=True, text=True, timeout=30)

        
        if result.returncode == 0:
            return jsonify({
                "status": "complete",
                "message": "Session processed successfully",
                "output": result.stdout
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Processing failed",
                "error": result.stderr
            }), 500
    
    except subprocess.TimeoutExpired:
        return jsonify({
            "status": "error",
            "message": "Processing timeout"
        }), 500
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/api/sync/device', methods=['POST'])
def sync_device():
    """Pull CSV files from ESP32 Device"""
    import requests
    data = request.get_json() or {}
    device_ip = data.get('ip', '192.168.4.1') # Default to AP IP
    
    # 1. Get List
    try:
        print(f"Syncing from {device_ip}...")
        resp = requests.get(f"http://{device_ip}/list", timeout=10)
        if resp.status_code != 200:
            return jsonify({"error": f"Device Error: {resp.status_code}"}), 400
            
        files = resp.json().get('files', [])
    except Exception as e:
        return jsonify({"error": f"Failed to connect to device: {e}"}), 500

    synced = []
    failed = []
    
    # 2. Download Each
    for fname in files:
        try:
            print(f"Downloading {fname}...")
            r = requests.get(f"http://{device_ip}/download/{fname}", stream=True, timeout=10)
            if r.status_code == 200:
                save_path = config.LEARNING_DIR / fname
                with open(save_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024):
                        if chunk: f.write(chunk)
                        
                synced.append(fname)
                
                # 3. Delete from Device (Move from ESP to Pi)
                try:
                    time.sleep(0.2) # Small breather for ESP32
                    del_resp = requests.get(f"http://{device_ip}/delete/{fname}", timeout=5)
                    if del_resp.status_code == 200:
                        print(f"[Sync] Successfully deleted {fname} from ESP32")
                    else:
                        print(f"[Sync] Failed to delete {fname} from ESP32: {del_resp.status_code}")
                except Exception as de:
                    print(f"[Sync] Error deleting {fname} from ESP32: {de}")
            else:
                failed.append(fname)
        except Exception as e:
            print(f"Error downloading {fname}: {e}")
            failed.append(fname)
            
    return jsonify({
        "success": True,
        "synced": synced,
        "failed": failed,
        "device_ip": device_ip
    })
def rename_track(track_id):
    """Rename a track"""
    data = request.get_json()
    new_name = data.get('new_name')
    
    if not new_name:
        return jsonify({"error": "new_name required"}), 400
    
    # Run rename script
    try:
        # Use echo to auto-confirm
        result = subprocess.run([
            'python3', 'scripts/rename_track.py',
            '--track_id', str(track_id),
            '--new_name', new_name
        ], capture_output=True, text=True, input='y\n', cwd=BASE_DIR, timeout=10)
        
        if result.returncode == 0:
            return jsonify({
                "success": True,
                "message": f"Renamed to {new_name}"
            })
        else:
            return jsonify({
                "success": False,
                "error": result.stderr
            }), 400
    
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# ============================================================================
# FILE MANAGEMENT
# ============================================================================
from file_manager import FileManager
file_mgr = FileManager(base_dir=config.LEARNING_DIR)

@app.route('/api/learning/list')
def list_learning_files():
    """List learning CSV files with metadata"""
    archived = request.args.get('archived', 'false').lower() == 'true'
    return jsonify(file_mgr.get_files(archived=archived))

@app.route('/api/learning/<filename>/lock', methods=['POST'])
def lock_learning_file(filename):
    data = request.json
    locked = data.get('locked', True)
    if file_mgr.set_lock(filename, locked):
        return jsonify({"success": True, "locked": locked})
    return jsonify({"error": "Failed to update lock"}), 500

@app.route('/api/learning/delete', methods=['POST'])
def delete_learning_files():
    """Permanent Bulk Delete"""
    data = request.json
    filenames = data.get('files', [])
    from_archive = data.get('from_archive', False)
    if not filenames:
        return jsonify({"error": "No files specified"}), 400
        
    result = file_mgr.delete_files(filenames, from_archive=from_archive)
    return jsonify(result)

@app.route('/api/learning/archive', methods=['POST'])
def archive_learning_files():
    """Soft delete - Move to archive"""
    data = request.json
    filenames = data.get('files', [])
    if not filenames:
        return jsonify({"error": "No files specified"}), 400
        
    result = file_mgr.archive_files(filenames)
    return jsonify(result)

@app.route('/api/learning/restore', methods=['POST'])
def restore_learning_files():
    """Restore from archive"""
    data = request.json
    filenames = data.get('files', [])
    if not filenames:
        return jsonify({"error": "No files specified"}), 400
        
    result = file_mgr.restore_files(filenames)
    return jsonify(result)

@app.route('/api/learning/<filename>/raw')
def get_learning_file_raw(filename):
    """Get raw head of file"""
    lines = request.args.get('lines', 100, type=int)
    return jsonify(file_mgr.read_file_head(filename, lines))

@app.route('/api/learning/<filename>/geo')
def get_learning_file_geo(filename):
    """Get Geo Path for Visualization"""
    return jsonify(file_mgr.extract_geo_path(filename))

@app.route('/api/device/configure', methods=['POST'])
def configure_device():
    """Configure ESP32 WiFi (Proxy)"""
    import requests
    data = request.get_json()
    device_ip = data.get('ip', '192.168.4.1')
    ssid = data.get('ssid')
    password = data.get('password')
    
    if not ssid or not password:
        return jsonify({"error": "Missing ssid or password"}), 400
        
    try:
        # Send to ESP32
        print(f"Configuring device at {device_ip}...")
        resp = requests.post(
            f"http://{device_ip}/config/wifi", 
            json={"ssid": ssid, "password": password},
            timeout=5
        )
        
        if resp.status_code == 200:
             return jsonify({"success": True, "message": "Configuration sent. Device rebooting..."})
        else:
             return jsonify({"error": f"Device rejected config: {resp.status_code}"}), 400
             
    except Exception as e:
        return jsonify({"error": f"Failed to connect to device: {e}"}), 500

@app.route('/api/device/scan', methods=['GET'])
def scan_devices():
    """Scan local network for ESP32 Datalogger"""
    import threading
    from queue import Queue
    
    # Accept optional subnet parameter
    custom_subnet = request.args.get('subnet', None)
    
    # 1. Detect Subnets to scan
    subnets_to_scan = []
    
    if custom_subnet:
        subnets_to_scan.append(custom_subnet if custom_subnet.endswith('.') else custom_subnet + '.')
    else:
        # Auto-detect local subnet
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            subnets_to_scan.append(".".join(local_ip.split('.')[:3]) + ".")
        except:
            subnets_to_scan.append("192.168.1.")
        
        # Also check ESP32 default AP subnet
        if "192.168.4." not in subnets_to_scan:
            subnets_to_scan.append("192.168.4.")
    
    print(f"[Scanner] Scanning subnets: {subnets_to_scan}")

    found_devices = []
    print_lock = threading.Lock()
    
    # helper to run a batch of IPs
    def run_batch(ips):
        q = Queue()
        for ip in ips:
            q.put(ip)
            
        def threader():
            while True:
                try:
                    ip = q.get_nowait()
                except:
                    # Queue is empty
                    break
                    
                try:
                    # Check IP
                    data = robust_get_json(f"http://{ip}/status", timeout=1.0)
                    if data and "storage" in data:
                        with print_lock:
                            v = data.get('version', '0.0.0')
                            info = {
                                "ip": ip, 
                                "info": data,
                                "compatible": is_compatible(v),
                                "min_required": MIN_ESP_VERSION
                            }
                            print(f"Found device at {ip}: {info}")
                            found_devices.append(info)
                except Exception:
                    # Ignore errors checking IP
                    pass
                finally:
                    q.task_done()

        threads = []
        # Adjust thread count based on batch size
        count = min(50, len(ips))
        for _ in range(count):
            t = threading.Thread(target=threader)
            t.daemon = True
            t.start()
            threads.append(t)
        
        q.join()

    # --- PHASE 1: Priority Scan (ARP + Hostnames) ---
    priority_ips = set()
    try:
        # Get ARP table (use -n to avoid slow DNS lookups)
        arp_out = subprocess.check_output(['arp', '-an'], text=True)
        import re
        for line in arp_out.splitlines():
            # Extract IP from format "? (192.168.1.41) at ..."
            match = re.search(r'\(([\d\.]+)\)', line)
            if match:
                ip = match.group(1)
                if any(ip.startswith(s) for s in subnets_to_scan):
                    priority_ips.add(ip)
    except:
        pass

    priority_ips.add("datalogger.local")
    priority_ips.add("datalogger")
    
    print(f"[Scanner] Phase 1: Checking {len(priority_ips)} priority targets...")
    run_batch(list(priority_ips))
    
    # If found, return early!
    if found_devices:
        print(f"Scan complete (Fast). Found {len(found_devices)} devices")
        return jsonify({"devices": found_devices, "subnets_scanned": subnets_to_scan})

    # --- PHASE 2: Subnet Brute Force ---
    print("[Scanner] Phase 2: Brute force subnets...")
    subnet_ips = []
    for subnet in subnets_to_scan:
        for i in range(1, 255):
            ip = f"{subnet}{i}"
            if ip not in priority_ips:
                subnet_ips.append(ip)
    
    run_batch(subnet_ips)
    
    print(f"Scan complete. Found {len(found_devices)} devices: {[d['ip'] for d in found_devices]}")
    return jsonify({"devices": found_devices, "subnets_scanned": subnets_to_scan})

@app.route('/api/device/check', methods=['GET'])
def check_device():
    """Check if specific device IP is reachable"""
    ip = request.args.get('ip')
    if not ip:
        print("[Check] No IP provided")
        return jsonify({"reachable": False})
    
    try:
        print(f"[Check] Testing {ip}...")
        r = requests.get(f"http://{ip}/status", timeout=5)
        print(f"[Check] Response: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(f"[Check] Data: {data}")
            v = data.get('version', '0.0.0')
            return jsonify({
                "reachable": True, 
                "info": data,
                "compatible": is_compatible(v),
                "min_required": MIN_ESP_VERSION
            })
        else:
            print(f"[Check] Non-200 status: {r.status_code}")
            return jsonify({"reachable": False})
    except Exception as e:
        print(f"[Check] Exception: {type(e).__name__}: {e}")
        return jsonify({"reachable": False})

@app.route('/api/device/version-check', methods=['GET'])
def device_version_check():
    """Detailed version comparison for a specific device"""
    ip = request.args.get('ip')
    if not ip:
        return jsonify({"error": "No IP provided"}), 400
        
    local_v = get_local_firmware_version()
    
    try:
        r = requests.get(f"http://{ip}/status", timeout=5)
        if r.status_code == 200:
            data = r.json()
            device_v = data.get('version', '0.0.0')
            return jsonify({
                "device_version": device_v,
                "server_version": local_v,
                "update_available": device_v != local_v,
                "is_compatible": is_compatible(device_v)
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/device/update-ota', methods=['POST'])
def device_update_ota():
    """Trigger WiFi OTA update for a device"""
    data = request.get_json()
    ip = data.get('ip')
    if not ip:
        return jsonify({"error": "No IP provided"}), 400
        
    print(f"[OTA] Starting update for {ip}...")
    result = update_mgr.push_update(ip)
    print(f"[OTA] Result: {result}")
    
    return jsonify(result)

@app.route('/api/learning/processed')
def get_processed_files():
    """Returns set of source filenames that have already been processed into sessions."""
    processed = set()
    sessions_dir = config.SESSIONS_DIR
    
    if sessions_dir.exists():
        for filename in os.listdir(sessions_dir):
            if filename.endswith('.json') and not filename.endswith('_telemetry.json'):
                try:
                    with open(sessions_dir / filename, 'r') as f:
                        data = json.load(f)
                        source_file = data.get('meta', {}).get('source_file')
                        if source_file:
                            processed.add(source_file)
                except Exception:
                    continue
    
    return jsonify(list(processed))

@app.route('/api/process/all', methods=['POST'])
def process_all_files():
    """Process all unprocessed learning files, or specific files if provided."""
    # Check if specific files were requested
    data = request.get_json() or {}
    requested_files = data.get('files', None)  # Optional list of specific files
    
    # Get list of learning files
    files = file_mgr.get_files()
    
    # Get already processed files
    processed = set()
    sessions_dir = config.SESSIONS_DIR
    if sessions_dir.exists():
        for filename in os.listdir(sessions_dir):
            if filename.endswith('.json') and not filename.endswith('_telemetry.json'):
                try:
                    with open(sessions_dir / filename, 'r') as f:
                        data = json.load(f)
                        source_file = data.get('meta', {}).get('source_file')
                        if source_file:
                            processed.add(source_file)
                except Exception:
                    continue
    
    # Determine which files to process
    if requested_files:
        # Process only specifically requested files that aren't already processed
        to_process = [f for f in requested_files if f not in processed]
    else:
        # Process all unprocessed files
        to_process = [f['filename'] for f in files if f['filename'] not in processed]
    
    if not to_process:
        return jsonify({
            "status": "complete",
            "message": "No new files to process",
            "processed": 0,
            "skipped": len(files)
        })
    
    results = {"success": [], "failed": []}
    
    for filename in to_process:
        csv_path = OUTPUT_DIR / "learning" / filename
        try:
            # Locate script relative to project root
            script_path = os.path.abspath(os.path.join(BASE_DIR, "../../core-analysis/datalogger_core/run_analysis.py"))
            
            result = subprocess.run([
                'python3', script_path, str(csv_path)
            ], capture_output=True, text=True, cwd=BASE_DIR, timeout=60)
            
            if result.returncode == 0:
                results["success"].append(filename)
            else:
                results["failed"].append({"filename": filename, "error": result.stderr[:200]})
        except subprocess.TimeoutExpired:
            results["failed"].append({"filename": filename, "error": "Timeout"})
        except Exception as e:
            results["failed"].append({"filename": filename, "error": str(e)})
    
    return jsonify({
        "status": "complete",
        "message": f"Processed {len(results['success'])} files",
        "processed": len(results["success"]),
        "failed": len(results["failed"]),
        "details": results
    })

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error"}), 500

@app.route('/api/tracks/<int:track_id>/geometry')
def get_track_geometry(track_id):
    """Serve the geometry.json file for a track."""
    folder_name = get_track_folder(track_id)
    if not folder_name:
         return jsonify({"error": "Track not found"}), 404
         
    geo_path = OUTPUT_DIR / "tracks" / folder_name / "geometry.json"
    if geo_path.exists():
        return send_file(geo_path)
    
    return jsonify({"error": "Geometry not found. Please regenerate track."}), 404
def delete_session(session_id):
    """Delete a processed session (JSON only, not raw data)"""
    try:
        # Sanitize ID to prevent directory traversal
        session_id = os.path.basename(session_id)
        if not session_id.endswith('.json'):
            session_id += '.json'
            
        s_path = OUTPUT_DIR / "sessions" / session_id
        
        if s_path.exists():
            os.remove(s_path)
            return jsonify({"success": True, "message": f"Deleted {session_id}"})
        else:
            return jsonify({"error": "Session not found"}), 404
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/tracks/<int:track_id>', methods=['DELETE'])
def delete_track_endpoint(track_id):
    """Delete a track, its folder, and all associated sessions."""
    try:
        from datalogger_core.core.registry_manager import RegistryManager
        import time
        import stat
        
        registry = RegistryManager()
        
        track = registry.get_track_by_id(track_id)
        if not track:
            return jsonify({"error": "Track not found"}), 404
            
        folder_name = track['folder_name']
        print(f"[API] Deleting track {track_id} ({folder_name})...")
        
        # 1. Delete associated processed sessions
        session_glob = f"{folder_name}_session_*.json"
        
        deleted_sessions = 0
        for s_file in (OUTPUT_DIR / "sessions").glob(session_glob):
            try:
                os.remove(s_file)
                deleted_sessions += 1
            except Exception as e:
                print(f"Failed to delete session {s_file}: {e}")
        
        # 2. Delete Track Folder (Robust Handling)
        track_dir = OUTPUT_DIR / "tracks" / folder_name
        
        def on_rm_error(func, path, exc_info):
            # Attempt to fix read-only files
            os.chmod(path, stat.S_IWRITE)
            try:
                func(path)
            except Exception:
                pass # Ignore if still fails, handled by parent try/catch usually or left as artifact

        if track_dir.exists():
            # Retry loop for potential file locks
            for i in range(3):
                try:
                    shutil.rmtree(track_dir, onerror=on_rm_error)
                    break
                except Exception as e:
                   if i == 2: raise e # Propagate error on last attempt
                   time.sleep(0.5) # Wait for lock release
            
        # 3. Remove from Registry
        if not registry.delete_track(track_id):
            print(f"[API] Warning: Track ID {track_id} not found in registry during delete.")
        
        return jsonify({
            "success": True, 
            "message": f"Deleted track '{folder_name}' and {deleted_sessions} sessions."
        })
        
    except Exception as e:
        print(f"[API] Delete Track Error: {e}")
        return jsonify({"error": f"Failed to delete: {str(e)}"}), 500

@app.route('/api/learning/rename', methods=['POST'])
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
            
        src = OUTPUT_DIR / "learning" / old_name
        dst = OUTPUT_DIR / "learning" / new_name
        
        if not src.exists():
            return jsonify({"error": "Source file not found"}), 404
            
        if dst.exists():
            return jsonify({"error": "A file with that name already exists"}), 400
            
        os.rename(src, dst)
        return jsonify({"success": True, "new_name": new_name})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions/<session_id>/rename', methods=['POST'])
def rename_session(session_id):
    """Rename a session (updates meta.session_name)"""
    data = request.get_json()
    new_name = data.get('new_name')
    if not new_name:
        return jsonify({"error": "new_name required"}), 400

    sessions_dir = OUTPUT_DIR / "sessions"
    safe_id = os.path.basename(session_id).replace('.json', '')
    json_path = sessions_dir / f"{safe_id}.json"
    
    if not json_path.exists():
        return jsonify({"error": "Session not found"}), 404
        
    try:
        with open(json_path, 'r') as f:
            session_data = json.load(f)
            
        session_data['meta']['session_name'] = new_name
        
        with open(json_path, 'w') as f:
            json.dump(session_data, f, indent=2)
            
        return jsonify({"success": True, "new_name": new_name})
    except FileNotFoundError:
        return jsonify({"error": "Session file not found on disk"}), 404
    except Exception:
        # Do not expose raw exception (paths)
        return jsonify({"error": "Failed to rename session due to an internal error"}), 500

@app.route('/api/sessions/<session_id>/notes', methods=['PUT'])
def update_session_notes(session_id):
    """Update session notes"""
    data = request.get_json()
    notes = data.get('notes', '')
    
    sessions_dir = OUTPUT_DIR / "sessions"
    safe_id = os.path.basename(session_id).replace('.json', '')
    json_path = sessions_dir / f"{safe_id}.json"
    
    if not json_path.exists():
        return jsonify({"error": "Session not found"}), 404
        
    try:
        with open(json_path, 'r') as f:
            session_data = json.load(f)
            
        # Ensure mode section exists
        if 'mode' not in session_data:
            session_data['mode'] = {}
            
        session_data['mode']['notes'] = notes
        
        with open(json_path, 'w') as f:
            json.dump(session_data, f, indent=2)
            
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Failed to save notes: {e}")
        return jsonify({"error": "Failed to save notes"}), 500

@app.route('/api/sessions/<session_id>/export')
def export_session(session_id):
    """
    Export session data as a ZIP file.
    Includes: session.json and _telemetry.json (if present)
    """
    import zipfile
    import io
    
    # 1. Locate Files
    sessions_dir = OUTPUT_DIR / "sessions"
    
    # Sanitize ID
    safe_id = os.path.basename(session_id).replace('.json', '')
    json_filename = f"{safe_id}.json"
    json_path = sessions_dir / json_filename
    
    if not json_path.exists():
        # Try searching by name? No, ID is safer.
        return jsonify({"error": "Session file not found"}), 404

    # Load data for metadata
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
            
        session_name = data.get('meta', {}).get('session_name', safe_id)
        start_time = data.get('meta', {}).get('start_time', '')
        track_name = data.get('track', {}).get('track_name', 'Unknown')
        best_lap = data.get('summary', {}).get('best_lap_time', 0)
        
        # Format Timestamp
        try:
            dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            date_str = dt.strftime('%Y-%m-%d_%H%M')
            readable_date = dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            date_str = "unknown_date"
            readable_date = start_time
            
        # Create Filename: session_DATE_NAME.zip
        # Sanitize Name
        clean_name = "".join([c for c in session_name if c.isalnum() or c in (' ', '_', '-')]).strip().replace(' ', '_')
        download_name = f"session_{date_str}_{clean_name}.zip"
        
        # README Content
        readme_content = f"""SESSION EXPORT
--------------------------------
Session:  {session_name}
Track:    {track_name}
Date:     {readable_date}
ID:       {safe_id}
--------------------------------
Best Lap: {best_lap}s
Laps:     {len(data.get('laps', []))}
--------------------------------
Generated by Datalogger Companion
"""

    except Exception:
         # Log internally but sanitize output
        print(f"Export Error for {session_id}") 
        return jsonify({"error": "Failed to read session metadata"}), 500

    # 2. Create ZIP in Memory
    mem_zip = io.BytesIO()
    
    try:
        with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Add Main Session JSON
            zf.write(json_path, arcname=json_filename)
            
            # Add README
            zf.writestr("README.txt", readme_content)
            
    except Exception:
        return jsonify({"error": "Failed to create backup archive"}), 500

    # 3. Serve File
    mem_zip.seek(0)
    return send_file(
        mem_zip,
        mimetype='application/zip',
        as_attachment=True,
        download_name=download_name
    )

# ============================================================================
# TRACKDAY AGGREGATION
# ============================================================================

def load_trackdays():
    """Load trackdays.json or return empty list"""
    trackdays_file = OUTPUT_DIR / "trackdays.json"
    if trackdays_file.exists():
        with open(trackdays_file, 'r') as f:
            return json.load(f)
    return []

def save_trackdays(trackdays):
    """Save trackdays to JSON file"""
    trackdays_file = OUTPUT_DIR / "trackdays.json"
    with open(trackdays_file, 'w') as f:
        json.dump(trackdays, f, indent=2)

@app.route('/api/trackdays', methods=['GET'])
def get_trackdays():
    """Get all trackdays with summary info"""
    trackdays = load_trackdays()
    
    # Enrich with session counts and quick stats
    for td in trackdays:
        sessions = td.get('session_ids', [])
        td['session_count'] = len(sessions)
        
        # Calculate aggregate stats
        total_laps = 0
        best_lap = None
        
        for sid in sessions:
            try:
                session_path = OUTPUT_DIR / "sessions" / f"{sid}.json"
                if session_path.exists():
                    with open(session_path, 'r') as f:
                        sdata = json.load(f)
                        if 'summary' in sdata:
                            total_laps += sdata['summary'].get('total_laps', 0)
                            slap = sdata['summary'].get('best_lap_time')
                            if slap and (best_lap is None or slap < best_lap):
                                best_lap = slap
            except Exception:
                pass
        
        td['total_laps'] = total_laps
        td['best_lap_time'] = best_lap
    
    return jsonify(trackdays)

@app.route('/api/trackdays', methods=['POST'])
def create_trackday():
    """Create a new trackday"""
    data = request.get_json()
    
    trackdays = load_trackdays()
    
    # Generate unique ID
    import uuid
    trackday_id = f"td_{uuid.uuid4().hex[:8]}"
    
    new_trackday = {
        'id': trackday_id,
        'name': data.get('name', 'Untitled Trackday'),
        'date': data.get('date', datetime.now().strftime('%Y-%m-%d')),
        'organizer': data.get('organizer', ''),
        'rider_name': data.get('rider_name', ''),
        'track_id': data.get('track_id'),
        'track_name': data.get('track_name', ''),
        'notes': data.get('notes', ''),
        'session_ids': [],
        'created_at': datetime.now().isoformat()
    }
    
    trackdays.append(new_trackday)
    save_trackdays(trackdays)
    
    return jsonify(new_trackday), 201

@app.route('/api/trackdays/<trackday_id>', methods=['GET'])
def get_trackday(trackday_id):
    """Get full trackday details with aggregated data from all sessions"""
    trackdays = load_trackdays()
    
    trackday = next((td for td in trackdays if td['id'] == trackday_id), None)
    if not trackday:
        return jsonify({"error": "Trackday not found"}), 404
    
    # Aggregate all sessions
    all_laps = []
    all_sector_times = []
    total_duration = 0
    best_lap_time = None
    sessions_data = []
    sector_count = 0
    
    for sid in trackday.get('session_ids', []):
        try:
            session_path = OUTPUT_DIR / "sessions" / f"{sid}.json"
            if session_path.exists():
                with open(session_path, 'r') as f:
                    sdata = json.load(f)
                    
                sessions_data.append({
                    'session_id': sid,
                    'session_name': sdata.get('meta', {}).get('session_name', sid),
                    'start_time': sdata.get('meta', {}).get('start_time'),
                    'total_laps': sdata.get('summary', {}).get('total_laps', 0),
                    'best_lap_time': sdata.get('summary', {}).get('best_lap_time')
                })
                
                total_duration += sdata.get('meta', {}).get('duration_sec', 0)
                
                # Get sector count
                if 'track' in sdata:
                    sector_count = max(sector_count, sdata['track'].get('sector_count', 0))
                
                # Collect laps
                for lap in sdata.get('laps', []):
                    lap_copy = lap.copy()
                    lap_copy['session_id'] = sid
                    lap_copy['session_name'] = sdata.get('meta', {}).get('session_name', sid)
                    all_laps.append(lap_copy)
                    
                    if lap.get('lap_time') and lap.get('valid'):
                        if best_lap_time is None or lap['lap_time'] < best_lap_time:
                            best_lap_time = lap['lap_time']
        except Exception as e:
            logger.error(f"Error loading session {sid}: {e}")
    
    # Sort laps by lap time
    all_laps.sort(key=lambda x: x.get('lap_time') or 999999)
    
    # Mark best lap in trackday
    if all_laps and all_laps[0].get('lap_time'):
        all_laps[0]['is_trackday_best'] = True
    
    # Calculate sector medians
    sector_medians = []
    for i in range(sector_count):
        times = [l['sector_times'][i] for l in all_laps if l.get('sector_times') and len(l['sector_times']) > i and l['sector_times'][i] > 0]
        sector_medians.append(sum(times) / len(times) if times else 0)
    
    # Calculate consistency
    valid_times = [l['lap_time'] for l in all_laps if l.get('lap_time') and l.get('valid')]
    consistency = 0
    if len(valid_times) > 1:
        import statistics
        consistency = statistics.stdev(valid_times)
    
    # Calculate TBL (Theoretical Best Lap) - best sector times across all laps
    tbl_sectors = []
    tbl_total = 0
    for i in range(sector_count):
        sector_times = [l['sector_times'][i] for l in all_laps 
                       if l.get('sector_times') and len(l['sector_times']) > i and l['sector_times'][i] > 0]
        if sector_times:
            best_sector = min(sector_times)
            tbl_sectors.append(best_sector)
            tbl_total += best_sector
        else:
            tbl_sectors.append(0)
    
    result = {
        **trackday,
        'sessions': sessions_data,
        'laps': all_laps,
        'summary': {
            'total_sessions': len(sessions_data),
            'total_laps': len(all_laps),
            'total_duration': total_duration,
            'best_lap_time': best_lap_time,
            'consistency': round(consistency, 3)
        },
        'sector_count': sector_count,
        'sector_medians': sector_medians,
        'tbl': {
            'total': round(tbl_total, 3) if tbl_total > 0 else None,
            'sectors': tbl_sectors
        } if tbl_total > 0 else None
    }
    
    return jsonify(result)

@app.route('/api/trackdays/<trackday_id>', methods=['PUT'])
def update_trackday(trackday_id):
    """Update trackday details"""
    data = request.get_json()
    trackdays = load_trackdays()
    
    for td in trackdays:
        if td['id'] == trackday_id:
            td['name'] = data.get('name', td['name'])
            td['date'] = data.get('date', td['date'])
            td['organizer'] = data.get('organizer', td['organizer'])
            td['rider_name'] = data.get('rider_name', td.get('rider_name', ''))
            td['notes'] = data.get('notes', td['notes'])
            save_trackdays(trackdays)
            return jsonify(td)
    
    return jsonify({"error": "Trackday not found"}), 404

@app.route('/api/trackdays/<trackday_id>', methods=['DELETE'])
def delete_trackday(trackday_id):
    """Delete a trackday (does not delete sessions)"""
    trackdays = load_trackdays()
    
    original_len = len(trackdays)
    trackdays = [td for td in trackdays if td['id'] != trackday_id]
    
    if len(trackdays) == original_len:
        return jsonify({"error": "Trackday not found"}), 404
    
    save_trackdays(trackdays)
    return jsonify({"success": True})

@app.route('/api/trackdays/<trackday_id>/sessions/<session_id>', methods=['POST'])
def tag_session_to_trackday(trackday_id, session_id):
    """Add a session to a trackday"""
    trackdays = load_trackdays()
    
    for td in trackdays:
        if td['id'] == trackday_id:
            if session_id not in td.get('session_ids', []):
                if 'session_ids' not in td:
                    td['session_ids'] = []
                td['session_ids'].append(session_id)
                save_trackdays(trackdays)
            return jsonify({"success": True, "session_ids": td['session_ids']})
    
    return jsonify({"error": "Trackday not found"}), 404

@app.route('/api/trackdays/<trackday_id>/sessions/<session_id>', methods=['DELETE'])
def untag_session_from_trackday(trackday_id, session_id):
    """Remove a session from a trackday"""
    trackdays = load_trackdays()
    
    for td in trackdays:
        if td['id'] == trackday_id:
            if session_id in td.get('session_ids', []):
                td['session_ids'].remove(session_id)
                save_trackdays(trackdays)
            return jsonify({"success": True, "session_ids": td['session_ids']})
    
    return jsonify({"error": "Trackday not found"}), 404











# ============================================================================
# CLOUD / API SERVER ENTRY POINT
# ============================================================================

if __name__ == '__main__':
    # Development mode
    print("=" * 60)
    print("Datalogger Cloud API Server")
    print("=" * 60)
    print(f"Output directory: {OUTPUT_DIR}")
    print()
    print("Starting server on http://localhost:5000")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5001, debug=False)
