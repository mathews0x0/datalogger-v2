# lib/track_engine.py - Minimal Track & Sector Feedback for ESP32
import json
import os
import math
import time

TRACK_FILE = "/data/metadata/track.json"
GATE_RADIUS_M = 15  # Meters to trigger sector crossing

class TrackEngine:
    """
    Lightweight track identification and sector timing engine.
    Designed for ESP32 resource constraints.
    """
    
    def __init__(self):
        self.track = None
        self.track_identified = False
        self.current_sector = 0
        self.sector_start_ts = 0.0
        self.lap_start_ts = 0.0
        self.current_lap_sectors = {}  # {0: 12.34, 1: 15.67}
        self._pending_event = None  # Event to be consumed by LED manager
        
    def load_track(self):
        """Load track definition from flash storage."""
        if not self._file_exists(TRACK_FILE):
            self.track = None
            return False
            
        try:
            with open(TRACK_FILE, 'r') as f:
                self.track = json.load(f)
            print(f"[TrackEngine] Loaded: {self.track.get('name', 'Unknown')}")
            return True
        except Exception as e:
            print(f"[TrackEngine] Load Error: {e}")
            self.track = None
            return False
    
    def save_track(self, track_data):
        """Save track definition to flash storage."""
        try:
            with open(TRACK_FILE, 'w') as f:
                json.dump(track_data, f)
            self.track = track_data
            self.reset()
            print(f"[TrackEngine] Saved: {track_data.get('name', 'Unknown')}")
            return True
        except Exception as e:
            print(f"[TrackEngine] Save Error: {e}")
            return False
    
    def reset(self):
        """Reset state for new session."""
        self.track_identified = False
        self.current_sector = 0
        self.sector_start_ts = 0.0
        self.lap_start_ts = 0.0
        self.current_lap_sectors = {}
        self._pending_event = None
    
    def get_pending_event(self):
        """Get and clear pending LED event."""
        evt = self._pending_event
        self._pending_event = None
        return evt
    
    def update(self, lat, lon, timestamp):
        """
        Main update loop. Call with each GPS sample.
        
        Returns:
            None - No event
            "TRACK_FOUND" - Just identified track
            "SECTOR_FAST" - Sector completed faster than TBL
            "SECTOR_NEUTRAL" - Sector within threshold
            "SECTOR_SLOW" - Sector slower than TBL
        """
        if not self.track:
            return None
            
        # Phase 1: Track Identification
        if not self.track_identified:
            sl = self.track.get('start_line')
            if sl:
                dist = self._haversine_m(lat, lon, sl['lat'], sl['lon'])
                radius = sl.get('radius_m', 20)
                if dist < radius:
                    self.track_identified = True
                    self.sector_start_ts = timestamp
                    self.lap_start_ts = timestamp
                    self.current_sector = 0
                    self._pending_event = "TRACK_FOUND"
                    print(f"[TrackEngine] Track Identified: {self.track.get('name')}")
                    return "TRACK_FOUND"
            return None
        
        # Phase 2: Sector Crossing Detection
        sectors = self.track.get('sectors', [])
        if self.current_sector < len(sectors):
            gate = sectors[self.current_sector]
            gate_lat = gate.get('end_lat')
            gate_lon = gate.get('end_lon')
            
            if gate_lat and gate_lon:
                dist = self._haversine_m(lat, lon, gate_lat, gate_lon)
                
                if dist < GATE_RADIUS_M:
                    # Sector Complete
                    sector_time = timestamp - self.sector_start_ts
                    self.current_lap_sectors[self.current_sector] = sector_time
                    
                    # Compare with TBL
                    tbl = self.track.get('tbl', {})
                    tbl_time = tbl.get(str(self.current_sector))
                    
                    event = self._calc_delta_event(sector_time, tbl_time)
                    
                    print(f"[TrackEngine] S{self.current_sector+1}: {sector_time:.2f}s (TBL: {tbl_time}, Delta: {event})")
                    
                    # Advance
                    self.current_sector += 1
                    self.sector_start_ts = timestamp
                    
                    # Check lap complete (back to sector 0)
                    if self.current_sector >= len(sectors):
                        self.current_sector = 0
                        self.lap_start_ts = timestamp
                        self.current_lap_sectors = {}
                    
                    self._pending_event = event
                    return event
        
        return None
    
    def _calc_delta_event(self, sector_time, tbl_time):
        """Determine feedback color based on delta."""
        if tbl_time is None:
            return "SECTOR_NEUTRAL"  # No TBL data
            
        delta = sector_time - tbl_time
        
        # Thresholds (in seconds)
        if delta <= 0.2:
            return "SECTOR_FAST"  # Green
        elif delta <= 0.6:
            return "SECTOR_NEUTRAL"  # Orange
        else:
            return "SECTOR_SLOW"  # Red
    
    def _haversine_m(self, lat1, lon1, lat2, lon2):
        """Calculate distance in meters between two GPS points."""
        R = 6371000  # Earth radius in meters
        
        lat1_r = math.radians(lat1)
        lat2_r = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        
        a = math.sin(dlat/2)**2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    def _file_exists(self, path):
        try:
            os.stat(path)
            return True
        except OSError:
            return False
    
    def get_status(self):
        """Return current state for API."""
        return {
            "track_loaded": self.track is not None,
            "track_name": self.track.get('name') if self.track else None,
            "track_identified": self.track_identified,
            "current_sector": self.current_sector,
            "sector_count": len(self.track.get('sectors', [])) if self.track else 0
        }
