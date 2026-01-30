import json
import os
import datetime
from typing import Dict, Optional
import src.config as config
from src.analysis.core.models import Session

class TBLManager:
    """
    Manages persistent Theoretical Best Lap (TBL) data.
    Stores sector bests in a dedicated JSON file (tracks/<track_id>_tbl.json)
    to allow Session JSON generation without parsing historical logs.
    """
    
    def __init__(self, tracks_dir: str = None):
        self.tracks_dir = tracks_dir if tracks_dir else config.TRACKS_DIR

    def _get_tbl_path(self, track_id: int) -> str:
        """Get TBL path using folder_name from registry."""
        from src.analysis.core.registry_manager import RegistryManager
        registry = RegistryManager()
        folder_name = registry.get_folder_name(track_id) or f"track_{track_id}"
        return os.path.join(self.tracks_dir, folder_name, "tbl.json")

    def load_tbl(self, track_id: int) -> Dict:
        """
        Load the TBL data for a given track.
        Returns a default structure if file doesn't exist.
        """
        path = self._get_tbl_path(track_id)
        if not os.path.exists(path):
            return self._create_default_tbl(track_id)
            
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[TBLManager] Error loading {path}: {e}")
            return self._create_default_tbl(track_id)

    def _create_default_tbl(self, track_id: int) -> Dict:
        return {
            "track_id": track_id,
            "sectors": [], # List of {sector_index: int, best_time: float}
            "total_best_time": None,
            "last_updated_session_id": None,
            "last_updated_time": None
        }

    def save_tbl(self, track_id: int, data: Dict):
        """
        Persist TBL data to disk.
        """
        path = self._get_tbl_path(track_id)
        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=4)
        except IOError as e:
             print(f"[TBLManager] Error saving {path}: {e}")

    def update_from_session(self, session: Session, track_info: Dict) -> bool:
        """
        Updates TBL with best sectors from the provided session.
        Returns True if TBL was improved and saved.
        """
        if not track_info or "track_id" not in track_info:
            return False

        track_id = track_info["track_id"]
        tbl_data = self.load_tbl(track_id)
        
        # Ensure we have the basic fields
        tbl_data["track_name"] = track_info.get("track_name", "Unknown")
        tbl_data["sector_count"] = len(track_info.get("sectors", []))

        # 1. Identify best sectors in CURRENT session
        # We need to scan all laps in the session to find the best time for each sector
        session_bests = {} # {sector_index: {'time': float, 'lap': int}}
        
        # Helper to normalize sector ID to index (e.g. "S1" -> 0)
        def get_sec_idx(sid):
            if isinstance(sid, int): return sid
            if isinstance(sid, str) and sid.startswith("S") and sid[1:].isdigit():
                return int(sid[1:]) - 1
            return -1

        for lap in session.laps:
            # if not lap.valid: continue # Lap validity not yet implemented in model
            
            for sec_id, time_val in lap.sector_times.items():
                if time_val is None: continue
                
                idx = get_sec_idx(sec_id)
                if idx < 0: continue
                
                if idx not in session_bests or time_val < session_bests[idx]:
                    session_bests[idx] = time_val

        if not session_bests:
            return False

        # 2. Compare against TBL and Update
        updated = False
        
        # Convert TBL/sectors list to dict for easier lookup
        tbl_sectors = {s["sector_index"]: s["best_time"] for s in tbl_data.get("sectors", [])}
        
        for idx, new_time in session_bests.items():
            current_best = tbl_sectors.get(idx)
            
            if current_best is None or new_time < current_best:
                tbl_sectors[idx] = new_time
                updated = True
                
        if updated:
            # Reconstruct sectors list
            new_sectors_list = [
                {"sector_index": idx, "best_time": time_val}
                for idx, time_val in sorted(tbl_sectors.items())
            ]
            tbl_data["sectors"] = new_sectors_list
            
            # Recalculate total Theoretical Best
            # Only valid if we have ALL sectors? Or sum of what we have? 
            # Usually sum of what we have, but ideally we want complete lap.
            # For now, simple sum of known bests.
            total = sum(s["best_time"] for s in new_sectors_list)
            tbl_data["total_best_time"] = total
            
            # Metadata
            # Use filename as session ID if available, else timestamp
            # Ideally session object should have an ID
            tbl_data["last_updated_session_id"] = getattr(session, "description", "Unknown")
            tbl_data["last_updated_time"] = datetime.datetime.utcnow().isoformat() + "Z"
            
            self.save_tbl(track_id, tbl_data)
            return True
            
        return False
