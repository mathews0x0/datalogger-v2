# lib/uploader.py - HTTP Uploader for Cloud Sync
import urequests
import secrets

def upload_all(session_mgr):
    """
    Uploads all CSV sessions from internal flash to Cloud Backend.
    Deletes successfully uploaded files to free space.
    """
    print("Starting cloud sync...")
    
    # Get all sessions from flash
    sessions = session_mgr.list_sessions()
    
    if not sessions:
        print("No sessions to upload")
        return 0
    
    print(f"Found {len(sessions)} sessions to upload")
    
    count_success = 0
    count_failed = 0
    
    for filename in sessions:
        print(f"Uploading {filename}...")
        
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
            res = urequests.post(secrets.API_URL, json=payload, headers=headers)
            
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
    
    print(f"\nSync complete: {count_success} uploaded, {count_failed} failed")
    return count_success
