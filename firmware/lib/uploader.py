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


def upload_all(session_mgr, led=None):
    """
    Upload all CSV session files to the cloud API using Device Token auth.
    Deletes files after successful upload.
    
    Returns: (uploaded_count, failed_count)
    """
    config = _load_config()
    token = config.get('token', '')
    api_url = config.get('api_url', '')
    
    if not token or not api_url:
        print('[Upload] No token or API URL configured, skipping upload')
        return (0, 0)
    
    files = session_mgr.list_sessions()
    if not files:
        print('[Upload] No session files to upload')
        return (0, 0)
    
    print(f'[Upload] Found {len(files)} file(s) to upload')
    
    uploaded = 0
    failed = 0
    
    import urequests
    
    for fname in files:
        try:
            filepath = session_mgr.active_dir + '/' + fname
            
            # Read file content
            with open(filepath, 'r') as f:
                content = f.read()
            
            if not content:
                print(f'[Upload] Skipping empty file: {fname}')
                continue
            
            # Toggle LED for visual feedback
            if led:
                led.value(not led.value())
            
            payload = json.dumps({
                'filename': fname,
                'content': content
            })
            
            headers = {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + token
            }
            
            print(f'[Upload] Uploading: {fname} ({len(content)} bytes)')
            resp = urequests.post(api_url, data=payload, headers=headers)
            
            if resp.status_code == 200:
                print(f'[Upload] Success: {fname}')
                session_mgr.delete_session(fname)
                uploaded += 1
            else:
                print(f'[Upload] Failed ({resp.status_code}): {fname}')
                failed += 1
            
            resp.close()
            gc.collect()
            
        except Exception as e:
            print(f'[Upload] Error uploading {fname}: {e}')
            failed += 1
            gc.collect()
    
    print(f'[Upload] Done: {uploaded} uploaded, {failed} failed')
    return (uploaded, failed)
