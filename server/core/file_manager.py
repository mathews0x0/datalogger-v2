import os
import json
import logging
from pathlib import Path
from datetime import datetime

METADATA_FILE = ".metadata.json"
ARCHIVE_DIR_NAME = "archive"

class FileManager:
    def __init__(self, base_dir):
        """
        Initialize FileManager.
        :param base_dir: Path object or string to the learning/data directory.
        """
        self.base_dir = Path(base_dir)
        self.archive_dir = self.base_dir / ARCHIVE_DIR_NAME
        self.metadata_path = self.base_dir / METADATA_FILE
        self.log = logging.getLogger("file_mgr")
        self._ensure_dir()

    def _ensure_dir(self):
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def _load_metadata(self):
        if not self.metadata_path.exists():
            return {}
        try:
            with open(self.metadata_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.log.error(f"Failed to load metadata: {e}")
            return {}

    def _save_metadata(self, data):
        try:
            with open(self.metadata_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.log.error(f"Failed to save metadata: {e}")

    def get_files(self, archived=False):
        """List all CSV files with metadata. If archived=True, list from archive dir."""
        meta = self._load_metadata()
        files = []
        
        target_dir = self.archive_dir if archived else self.base_dir
        
        if not target_dir.exists():
            return []

        for f in target_dir.glob("*.csv"):
            stat = f.stat()
            fname = f.name
            m = meta.get(fname, {})
            
            files.append({
                "filename": fname,
                "size_kb": round(stat.st_size / 1024, 2),
                "modified_ts": stat.st_mtime,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "locked": m.get("locked", False),
                "notes": m.get("notes", ""),
                "archived": archived
            })
            
        # Sort by modified desc
        files.sort(key=lambda x: x["modified_ts"], reverse=True)
        return files

    def set_lock(self, filename, locked: bool):
        """Toggle lock status."""
        meta = self._load_metadata()
        if filename not in meta:
            meta[filename] = {}
        
        meta[filename]["locked"] = locked
        self._save_metadata(meta)
        return True

    def archive_files(self, filenames):
        """Move files to archive directory."""
        import shutil
        meta = self._load_metadata()
        moved = []
        failed = []
        
        for fname in filenames:
            src = self.base_dir / fname
            dst = self.archive_dir / fname
            
            if not src.exists():
                failed.append({"filename": fname, "reason": "Not Found"})
                continue
                
            # Check Lock
            is_locked = meta.get(fname, {}).get("locked", False)
            if is_locked:
                failed.append({"filename": fname, "reason": "File is Locked"})
                continue
                
            try:
                shutil.move(str(src), str(dst))
                moved.append(fname)
            except Exception as e:
                failed.append({"filename": fname, "reason": str(e)})
                
        return {"success": True, "moved": moved, "failed": failed}

    def restore_files(self, filenames):
        """Restore files from archive to main directory."""
        import shutil
        moved = []
        failed = []
        
        for fname in filenames:
            src = self.archive_dir / fname
            dst = self.base_dir / fname
            
            if not src.exists():
                failed.append({"filename": fname, "reason": "Not Found in Archive"})
                continue
                
            if dst.exists():
                failed.append({"filename": fname, "reason": "File already exists in main"})
                continue
                
            try:
                shutil.move(str(src), str(dst))
                moved.append(fname)
            except Exception as e:
                failed.append({"filename": fname, "reason": str(e)})
                
        return {"success": True, "restored": moved, "failed": failed}

    def delete_files(self, filenames, from_archive=False):
        """Delete multiple files. If from_archive=True, delete from archive dir."""
        meta = self._load_metadata()
        deleted = []
        failed = [] # {filename: reason}
        
        target_dir = self.archive_dir if from_archive else self.base_dir
        
        for fname in filenames:
            # Check Lock
            is_locked = meta.get(fname, {}).get("locked", False)
            if is_locked:
                failed.append({"filename": fname, "reason": "File is Locked"})
                continue
                
            path = target_dir / fname
            if path.exists():
                try:
                    os.remove(path)
                    deleted.append(fname)
                    # Cleanup metadata
                    if fname in meta:
                        del meta[fname]
                except Exception as e:
                    failed.append({"filename": fname, "reason": str(e)})
            else:
                failed.append({"filename": fname, "reason": "Not Found"})
        
        # Save metadata after changes
        if deleted:
             self._save_metadata(meta)
             
        return {"success": True, "deleted": deleted, "failed": failed}

    def read_file_head(self, filename, lines=100):
        """Read first N lines of a file."""
        path = self.base_dir / filename
        if not path.exists():
            return {"error": "File not found"}
            
        content = []
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for _ in range(lines):
                    line = f.readline()
                    if not line: break
                    content.append(line)
            return {"lines": content, "filename": filename}
        except Exception as e:
            return {"error": str(e)}

    def extract_geo_path(self, filename, max_points=1000):
        """Extract Lat/Lon path from CSV."""
        path = self.base_dir / filename
        if not path.exists():
            return {"error": "File not found"}
            
        points = []
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                header = f.readline().lower().split(',')
                
                # Find columns
                lat_idx = -1
                lon_idx = -1
                
                for i, h in enumerate(header):
                    h = h.strip()
                    if 'lat' in h: lat_idx = i
                    if 'lon' in h: lon_idx = i
                    
                if lat_idx == -1 or lon_idx == -1:
                    return {"error": "No GPS columns found (lat/lon)"}
                
                # Read Data
                raw_points = []
                for line in f:
                    parts = line.split(',')
                    if len(parts) > max(lat_idx, lon_idx):
                        try:
                            lat = float(parts[lat_idx])
                            lon = float(parts[lon_idx])
                            if lat != 0 and lon != 0: # Filter empty 0,0
                                raw_points.append((lat, lon))
                        except ValueError:
                            continue
                            
                # Decimate
                total = len(raw_points)
                if total > max_points:
                    step = total // max_points
                    points = raw_points[::step]
                else:
                    points = raw_points
                    
            return {"points": points, "total_recorded": total}
        except Exception as e:
            return {"error": str(e)}
