import os
import time
import _thread

class SessionManager:
    def __init__(self, sd_mounted=False):
        """Initialize session storage on ESP32 or SD Card"""
        self.lock = _thread.allocate_lock()
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
        """Returns file path for new session using incrementing counter.
        Scans existing files to find the next available number.
        """
        with self.lock:
            max_num = 0
            try:
                for f in os.listdir(self.active_dir):
                    if f.startswith('sess_') and f.endswith('.csv'):
                        try:
                            num = int(f[5:-4])  # sess_NNN.csv -> NNN
                            if num > max_num:
                                max_num = num
                        except ValueError:
                            pass
            except OSError:
                pass
            fname = f"sess_{max_num + 1:03d}.csv"
            return f"{self.active_dir}/{fname}"

    def list_sessions(self):
        """List all session files stored on active storage"""
        with self.lock:
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
        """Archive session to uploaded/ folder after successful cloud sync"""
        fpath = f"{self.active_dir}/{filename}"
        archive_dir = f"{self.active_dir}/uploaded"
        with self.lock:
            try:
                try: os.mkdir(archive_dir)
                except OSError: pass  # Already exists
                os.rename(fpath, f"{archive_dir}/{filename}")
                print(f"Archived synced session: {filename}")
                return True
            except Exception as e:
                print(f"Error archiving {filename}: {e}")
                return False
    
    def get_storage_info(self):
        """Get storage statistics for flash and SD card"""
        info = {}
        
        # Flash Stats
        try:
            stat_flash = os.statvfs('/')
            tb_f = stat_flash[2] * stat_flash[0] // 1024
            fb_f = stat_flash[3] * stat_flash[0] // 1024
            info['flash'] = {
                'total_kb': tb_f,
                'used_kb': tb_f - fb_f,
                'free_kb': fb_f
            }
        except:
            info['flash'] = {'total_kb': 0, 'used_kb': 0, 'free_kb': 0}
            
        # SD Stats
        info['sd'] = {'mounted': self.sd_mounted, 'total_kb': 0, 'used_kb': 0, 'free_kb': 0}
        if self.sd_mounted:
            try:
                stat_sd = os.statvfs('/sd')
                tb_s = stat_sd[2] * stat_sd[0] // 1024
                fb_s = stat_sd[3] * stat_sd[0] // 1024
                info['sd'].update({
                    'total_kb': tb_s,
                    'used_kb': tb_s - fb_s,
                    'free_kb': fb_s
                })
            except:
                pass
                
        return info

    def get_active_storage_info(self):
        """Get storage stats for the active medium as a flat dict.
        Returns: {'total_kb': N, 'used_kb': N, 'free_kb': N} or None
        """
        try:
            mount = '/sd' if self.sd_mounted else '/'
            stat = os.statvfs(mount)
            total = stat[2] * stat[0] // 1024
            free = stat[3] * stat[0] // 1024
            return {'total_kb': total, 'used_kb': total - free, 'free_kb': free}
        except:
            return None
