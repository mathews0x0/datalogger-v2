# lib/uploader.py - Token-based CSV uploader for RS-Core
import json
import os
import gc

DEVICE_CONFIG_PATH = '/data/metadata/device.json'
MAX_FILE_SIZE = 400 * 1024  # 400KB safety cap for ESP32 RAM


def _load_config():
    """Load device config (token + API URL)."""
    try:
        with open(DEVICE_CONFIG_PATH, 'r') as f:
            return json.load(f)
    except:
        return {}


def _validate_session(filepath):
    """Check if a session file has a valid CSV header.
    Returns True if the file looks like a valid session.
    """
    try:
        with open(filepath, 'r') as f:
            header = f.readline().strip()
        return header.startswith('gps_time,') or header.startswith('time,')
    except:
        return False


def sync_all(session_mgr, led=None):
    """
    Synchronous blocking upload of all pending files.
    Used during the exclusive Upload phase at boot.
    """
    config = _load_config()
    token = config.get('token', '')
    api_url = config.get('api_url', '')
    
    if not token or not api_url:
        print('[Sync] No token or API URL configured')
        return False
        
    import urequests
    import time
    
    files = session_mgr.list_sessions()
    if not files:
        return True  # Nothing to do
        
    print(f'[Sync] Start: {len(files)} file(s)')
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + token
    }
    
    success_count = 0
    for fname in files:
        try:
            filepath = session_mgr.active_dir + '/' + fname
            
            stat = os.stat(filepath)
            size = stat[6]
            
            # Skip empty files
            if size == 0:
                print(f'[Sync] Deleting 0-byte: {fname}')
                session_mgr.delete_session(fname)
                success_count += 1
                continue

            # Integrity check
            if not _validate_session(filepath):
                print(f'[Sync] Skipping corrupt file: {fname}')
                session_mgr.delete_session(fname)
                success_count += 1
                continue

            # RAM safety check
            if size > MAX_FILE_SIZE:
                print(f'[Sync] WARNING: {fname} is {size} bytes, may cause MemoryError')

            print(f'[Sync] Uploading {fname} ({size} bytes)...')
            
            # Free as much RAM as possible before read
            gc.collect()
            
            with open(filepath, 'r') as f:
                content = f.read()
            
            payload = json.dumps({'filename': fname, 'content': content})
            content = None  # Free RAM immediately
            gc.collect()
            
            if led:
                led.update_onboard_led("CONNECTED")
            
            resp = urequests.post(api_url, data=payload, headers=headers)
            payload = None
            gc.collect()
            
            if resp.status_code == 200:
                print(f'[Sync] Done: {fname}')
                session_mgr.delete_session(fname)
                success_count += 1
            else:
                print(f'[Sync] Failed ({resp.status_code}): {fname}')
            
            resp.close()
            gc.collect()
            time.sleep(0.5)
            
        except MemoryError:
            print(f'[Sync] MemoryError on {fname} - file too large')
            gc.collect()
        except Exception as e:
            print(f'[Sync] Error {fname}: {e}')
            gc.collect()
            
    return success_count == len(files)
