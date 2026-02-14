# lib/uploader.py - HTTP Uploader for Cloud Sync
import urequests
import secrets

def upload_all(session_mgr, api_url=None, ble=None):
    """
    Uploads all CSV sessions from internal flash to Cloud Backend.
    Deletes successfully uploaded files to free space.
    """
    if not api_url:
        import secrets
        api_url = secrets.API_URL

    print(f"Starting cloud sync to {api_url}...")
    
    # Get all sessions from flash
    sessions = session_mgr.list_sessions()
    
    if not sessions:
        print("No sessions to upload")
        if ble:
            ble.notify_wifi_status(True, "No Data", "STA", progress=100)
        return 0
    
    total = len(sessions)
    print(f"Found {total} sessions to upload")
    
    count_success = 0
    count_failed = 0
    
    for i, filename in enumerate(sessions):
        print(f"Uploading {filename}...")
        
        # Notify progress via BLE
        if ble:
            progress = int((i / total) * 100)
            ble.notify_sync_progress(progress, filename)

        try:
            # Read session content
            content = session_mgr.get_session_data(filename)
            if not content:
                print(f"  Error: Could not read file")
                count_failed += 1
                continue
            
            # Prepare JSON payload
            payload = {
                "filename": filename,
                "content": content
            }
            
            # POST to cloud backend
            headers = {'Content-Type': 'application/json'}
            import urequests
            res = urequests.post(api_url, json=payload, headers=headers)
            
            if res.status_code == 200 or res.status_code == 201:
                print(f"  ✓ Success! Deleting local copy...")
                session_mgr.delete_session(filename)
                count_success += 1
            else:
                print(f"  ✗ Failed: HTTP {res.status_code}")
                count_failed += 1
            
            res.close()
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
            count_failed += 1
    
    if ble:
        ble.notify_sync_progress(100, "Complete")

    print(f"\nSync complete: {count_success} uploaded, {count_failed} failed")
    return count_success
