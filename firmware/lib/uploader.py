# lib/uploader.py - Token-based CSV uploader for RS-Core
import json
import os
import gc

DEVICE_CONFIG_PATH = '/data/metadata/device.json'


def _load_config():
    """Load device config (token + API URL)."""
    try:
        with open(DEVICE_CONFIG_PATH, 'r') as f:
            return json.load(f)
    except:
        return {}


import time

def background_task(session_mgr, led=None):
    """
    Continuous background loop that sends a heartbeat every 15 seconds
    and uploads any pending CSV session files to the cloud.
    """
    config = _load_config()
    token = config.get('token', '')
    api_url = config.get('api_url', '')
    
    if not token or not api_url:
        print('[Background] No token or API URL configured, skipping task')
        return
        
    import urequests
    ping_url = api_url.replace('/api/upload', '/api/device/ping')
    
    print('[Background] Task started (15s heartbeat + auto-upload)')
    
    while True:
        # 1. Heartbeat Ping
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + token
            }
            resp = urequests.post(ping_url, json={}, headers=headers)
            resp.close()
            gc.collect()
        except Exception as e:
            # Silent fail for heartbeat to avoid spamming serial
            pass
            
        # 2. Upload Pending Sessions
        files = session_mgr.list_sessions()
        if files:
            print(f'[Upload] Found {len(files)} file(s) to upload')
            for fname in files:
                try:
                    filepath = session_mgr.active_dir + '/' + fname
                    with open(filepath, 'r') as f:
                        content = f.read()
                    
                    if not content:
                        print(f'[Upload] Skipping empty file: {fname}')
                        continue
                    
                    payload = json.dumps({'filename': fname, 'content': content})
                    print(f'[Upload] Uploading: {fname} ({len(content)} bytes)')
                    
                    resp = urequests.post(api_url, data=payload, headers=headers)
                    if resp.status_code == 200:
                        print(f'[Upload] Success: {fname}')
                        session_mgr.delete_session(fname)
                    else:
                        print(f'[Upload] Failed ({resp.status_code}): {fname}')
                    
                    resp.close()
                    gc.collect()
                    time.sleep(1) # Breath between files
                    
                except Exception as e:
                    print(f'[Upload] Error uploading {fname}: {e}')
                    gc.collect()
                    
        # 3. Sleep until next heartbeat
        time.sleep(15)
