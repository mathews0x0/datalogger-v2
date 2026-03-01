from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
import os
import uuid
import requests
from datetime import datetime

from api.models import db, User, DeviceToken

devices_bp = Blueprint('devices', __name__)

@devices_bp.route('/api/devices/token', methods=['POST'])
@jwt_required()
def create_device_token():
    """Generate a new device upload token"""
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    device_name = data.get('device_name', 'RS-Core')

    token_str = 'rsk_' + str(uuid.uuid4()).replace('-', '')
    dt = DeviceToken(token=token_str, user_id=user_id, device_name=device_name)
    db.session.add(dt)
    db.session.commit()

    return jsonify({"success": True, "token": token_str, "device": dt.to_dict()}), 201

@devices_bp.route('/api/devices')
@jwt_required()
def list_device_tokens():
    """List all device tokens for the current user"""
    user_id = get_jwt_identity()
    tokens = DeviceToken.query.filter_by(user_id=user_id).order_by(DeviceToken.created_at.desc()).all()
    return jsonify([t.to_dict() for t in tokens])

@devices_bp.route('/api/devices/<int:token_id>', methods=['DELETE'])
@jwt_required()
def revoke_device_token(token_id):
    """Revoke a device token"""
    user_id = get_jwt_identity()
    dt = DeviceToken.query.filter_by(id=token_id, user_id=user_id).first()
    if not dt:
        return jsonify({"error": "Token not found"}), 404
    dt.revoked = True
    db.session.commit()
    return jsonify({"success": True})

# ============================================================================
# CSV UPLOAD (Dual-Auth: JWT or Device Token)
# ============================================================================

def _resolve_upload_user():
    """Resolve user_id from either JWT or Device Token in Authorization header.
    Returns: (user_id, error_message, device_token_obj_or_None)
    """
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer rsk_'):
        token_str = auth_header.split('Bearer ', 1)[1]
        dt = DeviceToken.query.filter_by(token=token_str, revoked=False).first()
        if not dt:
            return None, 'Invalid or revoked device token', None
            
        if dt.expires_at and dt.expires_at < datetime.utcnow():
            return None, 'Device token has expired', None
            
        return dt.user_id, None, dt
    else:
        try:
            verify_jwt_in_request()
            return get_jwt_identity(), None, None
        except Exception as e:
            import traceback
            traceback.print_exc()
            return None, 'Authentication required', None



# --- LOCAL DEVICE ENDPOINTS ---
from api.helpers import get_local_firmware_version, is_compatible
from api.decorators import local_only
from api.helpers import robust_get_json
from api.update_manager import UpdateManager
update_mgr = UpdateManager(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../firmware')))
MIN_ESP_VERSION = '0.0.0'
import socket
import subprocess
@devices_bp.route('/api/device/configure', methods=['POST'])
@local_only
@jwt_required()
def configure_device():
    """Configure ESP32 WiFi (Proxy)"""
    import requests
    data = request.get_json()
    device_ip = data.get('ip', '192.168.4.1')

    import ipaddress
    try:
        addr = ipaddress.ip_address(device_ip)
        # Block cloud metadata, loopback, and link-local
        if addr.is_loopback or addr.is_link_local or str(addr).startswith('169.254'):
            return jsonify({"error": "Invalid device IP"}), 400
    except ValueError:
        return jsonify({"error": "Invalid IP address format"}), 400

    ssid = data.get('ssid')
    password = data.get('password')
    
    if not ssid or not password:
        return jsonify({"error": "Missing ssid or password"}), 400
        
    try:
        # Send to ESP32
        print(f"Configuring device at {device_ip}...")
        resp = requests.post(
            f"http://{device_ip}/wifi/add", 
            json={"ssid": ssid, "password": password},
            timeout=5
        )
        
        if resp.status_code == 200:
             return jsonify({"success": True, "message": "Configuration sent. Device rebooting..."})
        else:
             return jsonify({"error": f"Device rejected config: {resp.status_code}"}), 400
             
    except Exception as e:
        return jsonify({"error": "We couldn't reach the device. Please check its power and network connection."}), 400

@devices_bp.route('/api/device/scan', methods=['GET'])
@local_only
@jwt_required()
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
                    data = robust_get_json(f"http://{ip}/status", timeout=2.0)
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

@devices_bp.route('/api/device/check', methods=['GET'])
@local_only
@jwt_required()
def check_device():
    """Check if specific device IP is reachable"""
    ip = request.args.get('ip')
    if not ip:
        print("[Check] No IP provided")
        return jsonify({"reachable": False})

    import ipaddress
    try:
        addr = ipaddress.ip_address(ip)
        # Block cloud metadata, loopback, and link-local
        if addr.is_loopback or addr.is_link_local or str(addr).startswith('169.254'):
            return jsonify({"error": "Invalid device IP"}), 400
    except ValueError:
        return jsonify({"error": "Invalid IP address format"}), 400
    
    try:
        print(f"[Check] Testing {ip}...")
        r = requests.get(f"http://{ip}/status", timeout=5)
        print(f"[Check] Response: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            did = data.get('device_id', 'Unknown')
            w_mode = data.get('wifi_mode', 'Unknown')
            ssid = data.get('wifi_ssid', 'Unknown')
            f_pct = data.get('flash_used_pct', 0)
            s_mnt = data.get('sd_mounted', False)
            s_pct = data.get('sd_used_pct', 0)
            
            print(f"[Check] Connected to {did} ({ip})")
            print(f"        WiFi: {w_mode} | SSID: {ssid}")
            print(f"        Flash Used: {f_pct}%")
            if s_mnt:
                print(f"        SD Used: {s_pct}%")
            else:
                print(f"        SD Card: Not inserted")
                
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

@devices_bp.route('/api/device/version-check', methods=['GET'])
@local_only
@jwt_required()
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

@devices_bp.route('/api/device/update-ota', methods=['POST'])
@local_only
@jwt_required()
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

