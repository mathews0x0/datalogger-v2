import json
import os
from typing import Optional, Dict
from src.analysis.core.models import Session
from src.analysis.processing.geo import haversine_distance

class TrackManager:
    """
    Manages track metadata and identification (Folder Aware).
    """
    def __init__(self, db_path: str = None):
        if db_path is None:
            # Load from default TRACKS_DIR
             import src.config as config
             self.tracks_dir = config.TRACKS_DIR
             self.tracks = self._load_all_tracks(self.tracks_dir)
        else:
            # Single file mode (legacy)
            self.tracks = self._load_tracks_file(db_path)

    def _load_all_tracks(self, directory: str) -> list:
        tracks = []
        if not os.path.exists(directory):
            return []
            
        # Scan subdirectories for track.json
        for entry in os.scandir(directory):
            if entry.is_dir():
                track_json_path = os.path.join(entry.path, "track.json")
                if os.path.exists(track_json_path):
                    try:
                        with open(track_json_path, 'r') as f:
                            data = json.load(f)
                            # Normalize metadata
                            if 'track_id' in data and 'id' not in data: data['id'] = data['track_id']
                            if 'track_name' in data and 'name' not in data: data['name'] = data['track_name']
                            
                            if isinstance(data, list):
                                tracks.extend(data)
                            else:
                                tracks.append(data)
                    except Exception as e:
                        print(f"Warning: Failed to load track from {track_json_path}: {e}")

        # Legacy Support: Scan flat files
        for filename in os.listdir(directory):
            if filename.endswith(".json") and not filename.endswith("tbl.json") and not filename == "README.md":
                # Check if it's a file
                path = os.path.join(directory, filename)
                if os.path.isfile(path):
                    # Only load if we haven't loaded this ID already? 
                    # For simplicity, we just load.
                    try:
                        with open(path, 'r') as f:
                            data = json.load(f)
                            if 'track_id' in data and 'id' not in data: data['id'] = data['track_id']
                            if 'track_name' in data and 'name' not in data: data['name'] = data['track_name']
                            tracks.append(data)
                    except:
                        pass
        return tracks

    def _load_tracks_file(self, path: str) -> list:
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print(f"Warning: Could not load track database from {path}")
            return []

    def identify_track(self, session: Session) -> Optional[Dict]:
        """
        Identify which track this session belongs to.
        Returns the track dict or None.
        Strategy: Check if any sample is within start line radius of known tracks.
        """
        for track in self.tracks:
            sl = track.get("start_line")
            if not sl:
                continue
                
            radius_km = sl.get("radius_m", 20.0) / 1000.0
            target_lat = sl["lat"]
            target_lon = sl["lon"]
            
            # Check samples
            for sample in session.samples:
                dist = haversine_distance(sample.gps.lat, sample.gps.lon, target_lat, target_lon)
                if dist < radius_km:
                    return track
                    
        return None

    def identify_track_point(self, lat: float, lon: float) -> Optional[Dict]:
        """
        Identify track from a single GPS point (Real-time).
        """
        for track in self.tracks:
            sl = track.get("start_line")
            if not sl: continue
                
            radius_km = sl.get("radius_m", 20.0) / 1000.0
            target_lat = sl["lat"]
            target_lon = sl["lon"]
            
            dist = haversine_distance(lat, lon, target_lat, target_lon)
            if dist < radius_km:
                return track
        return None

    def save_track(self, track_data: Dict):
        """
        Persist updated track data (e.g. metadata repairs).
        In new architecture, track.json is largely immutable, but we allow edits here.
        """
        if not track_data or "id" not in track_data:
            return
            
        track_id = track_data['id']
        
        # New Folder Structure
        import src.config as config
        track_dir = os.path.join(config.TRACKS_DIR, track_id)
        os.makedirs(track_dir, exist_ok=True)
        
        out_path = os.path.join(track_dir, "track.json")
        
        try:
            with open(out_path, 'w') as f:
                json.dump(track_data, f, indent=4)
        except Exception as e:
            print(f"Error saving track {track_id}: {e}")
