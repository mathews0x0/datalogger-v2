# session_manager.py - Manages onboard flash storage only
import os
import time

class SessionManager:
    def __init__(self):
        """Initialize session storage on ESP32 internal flash"""
        self.base_dir = '/data'
        self.internal_dir = '/data/learning'
        self.metadata_dir = '/data/metadata'
        
        # Ensure directory structure exists
        self._ensure_dir_exists()
        # Migrate old data if necessary
        self._migrate_legacy_data()
        
        print(f"SessionManager initialized: {self.internal_dir}")
            
    def _ensure_dir_exists(self):
        """Recursively ensure /data/learning, metadata, and tracks exist"""
        for d in [self.base_dir, self.internal_dir, self.metadata_dir, '/data/tracks']:
            try:
                os.mkdir(d)
            except OSError:
                pass  # Already exists

    def _migrate_legacy_data(self):
        """Move files from root-level /sessions and /track.json to new /data structure"""
        # 1. Migrate tracks
        try:
            os.rename('/track.json', self.metadata_dir + '/track.json')
            print("Migrated /track.json -> /data/metadata/track.json")
        except OSError:
            pass

        # 2. Migrate WiFi creds
        try:
            os.rename('/wifi_credentials.json', self.metadata_dir + '/wifi.json')
            print("Migrated /wifi_credentials.json -> /data/metadata/wifi.json")
        except OSError:
            pass

        # 3. Migrate sessions
        try:
            old_sessions = os.listdir('/sessions')
            for f in old_sessions:
                os.rename('/sessions/' + f, self.internal_dir + '/' + f)
                print(f"Migrated session: {f}")
            # Try to remove old dir
            try:
                # os.rmdir('/sessions') # Some micropython versions don't support rmdir on non-empty, even if it is empty
                pass
            except:
                pass
        except OSError:
            pass

    def get_log_file(self):
        """Returns file path for new session on internal flash"""
        # Generate filename based on timestamp
        # ESP32 time() starts from boot, but GPS will update it
        fname = f"sess_{time.time()}.csv"
        return f"{self.internal_dir}/{fname}"

    def list_sessions(self):
        """List all session files stored on flash"""
        try:
            files = os.listdir(self.internal_dir)
            return [f for f in files if f.endswith('.csv')]
        except OSError:
            return []
    
    def get_session_data(self, filename):
        """Read session file content for cloud upload"""
        fpath = f"{self.internal_dir}/{filename}"
        try:
            with open(fpath, 'r') as f:
                return f.read()
        except Exception as e:
            print(f"Error reading {filename}: {e}")
            return None
    
    def delete_session(self, filename):
        """Delete session after successful cloud sync"""
        fpath = f"{self.internal_dir}/{filename}"
        try:
            os.remove(fpath)
            print(f"Deleted synced session: {filename}")
            return True
        except Exception as e:
            print(f"Error deleting {filename}: {e}")
            return False
    
    def get_storage_info(self):
        """Get flash storage statistics"""
        try:
            stat = os.statvfs('/')
            block_size = stat[0]
            total_blocks = stat[2]
            free_blocks = stat[3]
            
            total_kb = (total_blocks * block_size) // 1024
            free_kb = (free_blocks * block_size) // 1024
            used_kb = total_kb - free_kb
            
            return {
                'total_kb': total_kb,
                'used_kb': used_kb,
                'free_kb': free_kb,
                'sessions': len(self.list_sessions())
            }
        except Exception as e:
            print(f"Storage info error: {e}")
            return None
