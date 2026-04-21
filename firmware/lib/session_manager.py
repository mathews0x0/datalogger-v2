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
            return [entry["name"] for entry in self._scan_pending_entries_locked()]

    def list_session_entries(self):
        """List pending session entries across active and fallback storage."""
        with self.lock:
            return self._scan_pending_entries_locked()

    def _candidate_session_dirs(self):
        dirs = [self.active_dir]
        if self.sd_mounted and self.flash_sessions not in dirs:
            dirs.append(self.flash_sessions)
        if '/sessions' not in dirs:
            dirs.append('/sessions')
        return dirs

    def _scan_pending_entries_locked(self):
        entries = []
        seen = set()
        for directory in self._candidate_session_dirs():
            try:
                files = os.listdir(directory)
            except OSError:
                continue
            for fname in files:
                if not fname.endswith('.csv'):
                    continue
                path = directory + '/' + fname
                if path in seen:
                    continue
                seen.add(path)
                try:
                    size = os.stat(path)[6]
                except Exception:
                    size = 0
                entries.append({
                    "name": fname,
                    "path": path,
                    "dir": directory,
                    "size": size,
                })
        return entries

    def get_pending_summary(self):
        """Return pending file count and total size for sync UI."""
        with self.lock:
            entries = self._scan_pending_entries_locked()
            count = len(entries)
            total_bytes = 0
            names = []
            for entry in entries:
                total_bytes += int(entry.get("size", 0) or 0)
                names.append(entry.get("name", ""))
            return {"count": count, "total_bytes": total_bytes, "names": names}
    
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

    def archive_session_entry(self, entry):
        """Archive a session entry after successful sync, preserving source dir."""
        if not entry:
            return False
        fpath = entry.get("path")
        directory = entry.get("dir") or self.active_dir
        filename = entry.get("name") or (fpath.split("/")[-1] if fpath else "")
        if not fpath or not filename:
            return False
        archive_dir = directory + '/uploaded'
        with self.lock:
            try:
                try:
                    os.mkdir(archive_dir)
                except OSError:
                    pass
                os.rename(fpath, archive_dir + '/' + filename)
                print(f"Archived synced session: {filename} ({directory})")
                return True
            except Exception as e:
                print(f"Error archiving {filename} from {directory}: {e}")
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

    def has_flash_sessions(self):
        """Checks if there are any session files on internal flash, including uploaded."""
        try:
            files = os.listdir(self.flash_sessions)
            has_pending = any(f.endswith('.csv') for f in files)
            has_uploaded = False
            if 'uploaded' in files:
                try:
                    up_files = os.listdir(f"{self.flash_sessions}/uploaded")
                    has_uploaded = any(f.endswith('.csv') for f in up_files)
                except OSError:
                    pass
            return has_pending or has_uploaded
        except OSError:
            return False

    def move_flash_to_sd(self):
        """Moves all session files from flash to SD card, including uploaded."""
        if not self.sd_mounted:
            return False
            
        success = True
        moved_any = False
        
        def move_dir_files(src_dir, dst_dir):
            nonlocal success, moved_any
            try:
                try: os.mkdir(dst_dir)
                except OSError: pass
                
                try: files = [f for f in os.listdir(src_dir) if f.endswith('.csv')]
                except OSError: files = []
                
                if not files:
                    return
                    
                print(f"[Storage] Moving {len(files)} sessions from {src_dir} to SD card...")
                moved_any = True
                
                for fname in files:
                    src = f"{src_dir}/{fname}"
                    dst = f"{dst_dir}/{fname}"
                    
                    try: existing_files = os.listdir(dst_dir)
                    except OSError: existing_files = []
                    
                    if fname in existing_files:
                        base, ext = fname.rsplit('.', 1)
                        counter = 1
                        new_fname = f"{base}_{counter}.{ext}"
                        while new_fname in existing_files:
                            counter += 1
                            new_fname = f"{base}_{counter}.{ext}"
                        dst = f"{dst_dir}/{new_fname}"
                        print(f"  ! Conflict: Renaming to {new_fname}")
                    
                    print(f"  -> Copying {fname}...")
                    
                    with open(src, 'rb') as f_src:
                        with open(dst, 'wb') as f_dst:
                            chunk_count = 0
                            while True:
                                chunk = f_src.read(4096)
                                if not chunk:
                                    break
                                f_dst.write(chunk)
                                chunk_count += 1
                                if chunk_count % 32 == 0:
                                    try:
                                        import machine
                                        machine.WDT(timeout=20000).feed()
                                    except:
                                        pass
                    
                    if os.stat(src)[6] == os.stat(dst)[6]:
                        os.remove(src)
                        print(f"  ✓ Moved {fname}")
                    else:
                        print(f"  ! Error: Size mismatch for {fname}")
                        success = False
                        break
            except Exception as e:
                print(f"[Storage] Move failed in {src_dir}: {e}")
                success = False

        move_dir_files(self.flash_sessions, self.active_dir)
        move_dir_files(f"{self.flash_sessions}/uploaded", f"{self.active_dir}/uploaded")
        
        return success and moved_any
