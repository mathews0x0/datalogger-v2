import requests
import sys

BASE_URL = "http://localhost:6969"

def test_delete_track(track_id):
    print(f"Attempting to delete track {track_id}...")
    try:
        url = f"{BASE_URL}/api/tracks/{track_id}"
        response = requests.delete(url)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        if response.status_code == 200:
            print("SUCCESS: Track deleted.")
            return True
        else:
            print("FAILURE: Track deletion failed.")
            return False
    except Exception as e:
        print(f"ERROR: Could not connect to server: {e}")
        return False

if __name__ == "__main__":
    # Use a dummy track ID for testing (assume ID 2 exists or similar, or just trigger the code path)
    # If ID 2 doesn't exist, it might return 404, but we want to hit the 500 error if possible.
    # To catch the NameError, we need to pass the "get_track_by_id" check.
    # Since we can't easily fetch a valid ID without querying, checking the list first might be wise.
    
    # 1. Get list of tracks
    # Target Track 2 explicitly for verification
    print("Targeting Track 2...")
    test_delete_track(2)
