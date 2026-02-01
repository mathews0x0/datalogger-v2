# session_manager.py - Manages onboard flash storage only
import os
import time

class SessionManager:
    def __init__(self, sd_mounted=False):
        """Initialize session storage on ESP32 or SD Card"""
        self.sd_mounted = sd_mounted
        
        # Paths
        self.flash_base = '/data'
        self.flash_sessions = '/data/learning'
        self.flash_meta = '/data/metadata'
        
        if self.sd_mounted:
            self.base_dir = '/sd'
            self.active_dir = '/sd/sessions'
            self.metadata_dir = '/sd/metadata' # Prefer metadata on SD if available? Or keep on Flash?
            # Design choice: Keep critical config (WiFi) on Flash usually, but for simplicity let's mirror structure
            # Actually, WiFi creds should stay on Flash to boot. 
            # Let's keep metadata on Flash for reliability, only sessions on SD.
            self.metadata_dir = self.flash_meta 
        else:
            self.base_dir = self.flash_base
            self.active_dir = self.flash_sessions
            self.metadata_dir = self.flash_meta
        
        # Ensure directories exist
        self._ensure_dir_exists()
        
        # If using Flash, migrate old data
        if not self.sd_mounted:
            self._migrate_legacy_data()
        
        print(f"SessionManager initialized: {self.active_dir}")
            
    def _ensure_dir_exists(self):
        """Recursively ensure directories exist"""
        # Flash dirs always needed for metadata/backup
        for d in [self.flash_base, self.flash_sessions, self.flash_meta, '/data/tracks']:
            try: os.mkdir(d)
            except OSError: pass

        # SD dirs if mounted
        if self.sd_mounted:
            try: os.mkdir('/sd/sessions')
            except OSError: pass

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
                os.rename('/sessions/' + f, self.active_dir + '/' + f)
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
        return f"{self.active_dir}/{fname}"

    def list_sessions(self):
        """List all session files stored on active storage"""
        try:
            files = os.listdir(self.active_dir)
            return [f for f in files if f.endswith('.csv')]
        except OSError:
            return []
    
    def get_session_data(self, filename):
        """Read session file content for cloud upload"""
        fpath = f"{self.active_dir}/{filename}"
        try:
            with open(fpath, 'r') as f:
                return f.read()
        except Exception as e:
            print(f"Error reading {filename}: {e}")
            return None
    
    def delete_session(self, filename):
        """Delete session after successful cloud sync"""
        fpath = f"{self.active_dir}/{filename}"
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
