from typing import List, Optional, Dict
from src.analysis.core.models import Lap, Session
from src.analysis.processing.geo import haversine_distance

class StatsEngine:
    """
    Calculates session statistics, best laps, and sector times.
    """
    
    @staticmethod
    def find_best_lap(laps: List[Lap]) -> Optional[Lap]:
        """Returns the lap with the lowest duration."""
        valid_laps = [l for l in laps if l.duration > 0]
        if not valid_laps:
            return None
        return min(valid_laps, key=lambda l: l.duration)

    @staticmethod
    def calculate_sectors(laps: List[Lap], track_info: Dict):
        """
        Populate sector_times for each lap based on track info.
        track_info: Dict from TrackManager (must contain 'sectors')
        """
        if not track_info or "sectors" not in track_info:
            return

        sectors = track_info["sectors"]
        
        for lap in laps:
            # For each sector, find when we crossed the end line
            # Default: Sector 1 starts at Lap Start.
            # Sector 2 starts at Sector 1 End.
            
            previous_split_time = lap.samples[0].timestamp
            last_split_valid = True
            
            for sector in sectors:
                sec_id = sector["id"]
                end_lat = sector["end_lat"]
                end_lon = sector["end_lon"]
                rad_km = sector.get("radius_m", 20.0) / 1000.0
                
                # Scan lap for crossing of this sector point
                # Optimization: In a real engine, we'd use vectorized search or index.
                # Here, we iterate.
                
                if not last_split_valid:
                     lap.sector_times[sec_id] = None
                     continue

                # Special Case: Last Sector (S7)
                if sector == sectors[-1]:
                    # Sum up previous sectors
                    total_so_far = sum([v for k, v in lap.sector_times.items() if v is not None])
                    remainder = lap.duration - total_so_far
                    lap.sector_times[sec_id] = remainder if remainder > 0 else 0.0
                    continue

                crossed_ts = None
                
                # Scan samples
                for sample in lap.samples:
                    if sample.timestamp <= previous_split_time:
                        continue
                        
                    dist = haversine_distance(sample.gps.lat, sample.gps.lon, end_lat, end_lon)
                    if dist < rad_km:
                        crossed_ts = sample.timestamp
                        break
                
                if crossed_ts:
                    # Sector Time = Crossing TS - Previous Split TS
                    duration = crossed_ts - previous_split_time
                    lap.sector_times[sec_id] = duration
                    previous_split_time = crossed_ts
                    last_split_valid = True
                else:
                    # Missed the sector line?
                    lap.sector_times[sec_id] = None
                    last_split_valid = False

    @staticmethod
    def update_track_records(session_name: str, laps: List[Lap], track_data: Dict) -> bool:
        """
        Updates the track's persistent records with data from this session.
        Returns True if something improved (saved).
        """
        if "records" not in track_data:
            # Init if missing (legacy tracks)
            track_data["records"] = {
                "best_real_lap": {"time": None, "session": None},
                "sector_bests": {}
            }
            
        records = track_data["records"]
        updated = False
        
        # 1. Update Best Real Lap
        best_lap = StatsEngine.find_best_lap(laps)
        if best_lap:
            current_best = records["best_real_lap"].get("time")
            if current_best is None or best_lap.duration < current_best:
                records["best_real_lap"] = {
                    "time": best_lap.duration,
                    "session": session_name
                }
                updated = True
                
        # 2. Update Sector Bests
        # Ensure bucket exists for all sectors
        if "sectors" in track_data:
            for s in track_data["sectors"]:
                sid = s["id"]
                if sid not in records["sector_bests"]:
                    records["sector_bests"][sid] = {"time": None, "session": None}

        # Scan all valid laps for sector improvements
        for lap in laps:
            
            for sid, time_val in lap.sector_times.items():
                if time_val is None: continue
                
                # Check stored record
                rec = records["sector_bests"].get(sid, {"time": None})
                current = rec.get("time")
                
                if current is None or time_val < current:
                    records["sector_bests"][sid] = {
                        "time": time_val,
                        "session": session_name
                    }
                    updated = True
                    
        return updated
