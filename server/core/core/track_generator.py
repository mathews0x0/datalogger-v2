import os
import json
import matplotlib.pyplot as plt
from typing import Dict, Optional, List
import src.config as config
from src.analysis.core.models import Session, Lap
from src.analysis.processing.laps import LapDetector, StartLine
from src.analysis.processing.geo import haversine_distance

class TrackGenerator:
    """
    Modular logic to generate Track JSON (and geometry) from a Session.
    Used for both 'Learning Mode' and 'Auto-Track' generation.
    """

    def __init__(self, output_dir: str = None):
        self.output_dir = output_dir if output_dir else config.TRACKS_DIR
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Initialize Registry Manager for sequential track IDs
        from src.analysis.core.registry_manager import RegistryManager
        self.registry = RegistryManager()

    def generate_from_session(self, session: Session, track_id: int, track_name: str, radius_m: float = 20.0) -> Optional[Dict]:
        """
        Process a session to extract track geometry, sectors, and metadata.
        Saves artifacts to disk and returns the Track Dict.
        
        Args:
            track_id: Numeric, immutable track identity
            track_name: Mutable, human-readable name (drives folder name)
            radius_m: Start line detection radius
        """
        # Sanitize track_name to get folder name
        folder_name = self.registry.sanitize_name(track_name)
        track_dir = os.path.join(self.output_dir, folder_name)
        
        # Check if Track Folder exists (Immutability Check)
        if os.path.exists(track_dir):
            print(f"[TrackGenerator] Track folder '{folder_name}' already exists. Skipping generation.")
            # We assume if it exists, it's valid. Return None to indicate we didn't generate new one?
            # Or try to load it?
            # Caller expects a dict if success.
            # Let's return None to force loading from TM or indicate "Not New".
            return None

        if not session.samples:
            print("[TrackGenerator] Error: Empty session.")
            return None

        # 1. Identify Start (Smart Detection)
        start_lat, start_lon = self._detect_start_line_candidate(session, radius_m)

        # 2. Detect Laps
        sl_obj = StartLine(start_lat, start_lon, radius_m)
        detector = LapDetector(sl_obj)
        laps = detector.detect(session)

        if not laps:
            print("[TrackGenerator] No laps detected to infer geometry.")
            return None

        # 3. Find Reference Lap (Fastest Valid Flying Lap)
        # Filter outliers based on distance (exclude short Out laps or long In laps)
        valid_laps = [l for l in laps if l.duration > 0]
        if not valid_laps:
             print("[TrackGenerator] No valid laps found.")
             return None
             
        # Calculate Median Distance
        # We need to compute distance for each lap first? Lap object might not store it pre-calc.
        # But we can iterate.
        lap_distances = []
        for l in valid_laps:
            dist = 0.0
            for i in range(1, len(l.samples)):
                dist += haversine_distance(l.samples[i-1].gps.lat, l.samples[i-1].gps.lon, 
                                         l.samples[i].gps.lat, l.samples[i].gps.lon)
            lap_distances.append(dist)
            
        median_dist = sorted(lap_distances)[len(lap_distances)//2]
        print(f"[TrackGenerator] Median Lap Distance: {median_dist:.3f} km")
        
        # Filter: Keep laps within 20% of median
        # This removes short Out laps (Start -> Line) and potentially weird In laps
        clean_laps = []
        for i, l in enumerate(valid_laps):
            if 0.8 * median_dist <= lap_distances[i] <= 1.2 * median_dist:
                clean_laps.append(l)
                
        if not clean_laps:
            print("[TrackGenerator] All laps filtered out by distance check. Using all valid laps.")
            clean_laps = valid_laps
            
        ref_lap = min(clean_laps, key=lambda l: l.duration)
        ref_lap_idx = valid_laps.index(ref_lap)
        print(f"[TrackGenerator] Selected Reference Lap {ref_lap.lap_number} (Time: {ref_lap.duration:.2f}s, Dist: {lap_distances[ref_lap_idx]:.3f}km)")

        # 4. Process Geometry (Smooth & Close Loop)
        # We extract samples from ref_lap
        raw_lats = [s.gps.lat for s in ref_lap.samples]
        raw_lons = [s.gps.lon for s in ref_lap.samples]
        
        # Smooth Geometry (Moving Average, window=5)
        # Use a simple helper or inline
        def smooth_coords(coords, window=5):
            if len(coords) < window: return coords
            smoothed = []
            for i in range(len(coords)):
                start = max(0, i - window // 2)
                end = min(len(coords), i + window // 2 + 1)
                chunk = coords[start:end]
                smoothed.append(sum(chunk) / len(chunk))
            return smoothed
            
        final_lats = smooth_coords(raw_lats)
        final_lons = smooth_coords(raw_lons)
        
        # Explicitly Close the Loop
        # Force the last point to match the first point exactly
        if final_lats:
             final_lats[-1] = final_lats[0]
             final_lons[-1] = final_lons[0]

        # 5. Overwrite Ref Lap Samples? 
        # Ideally we want to prevent recalculating sectors on raw data if we smoothed geometry.
        # But 'sectors' are calculated based on indices of ref_lap.
        # We should create a "Synthetic Lap" for geometry definition?
        # For simplicity, we keep sectors based on raw ref_lap (which is time-accurate)
        # BUT we update the 'Track Geometry' source to be this smoothed list?
        # The current system plots from 'ref_lap.samples'.
        # We need to save this smoothed geometry into track.json or pass it to visualizer.
        # Track JSON usually only stores sectors.
        # Wait, track.json doesn't performantly store 1000 points of geometry?
        # Usually it doesn't. But we need it for the map.
        
        # Let's update the Start Line to be exactly Point 0 of smoothed geometry
        if final_lats:
            start_lat = final_lats[0]
            start_lon = final_lons[0]

        # 6. Generate Sectors & Indices
        sectors, sector_indices = self._calculate_sectors_from_coords(final_lats, final_lons, start_lat, start_lon)

        # 7. Build Track Dict
        track_data = {
            "track_id": track_id,
            "track_name": track_name,
            "start_line": {
                "lat": start_lat,
                "lon": start_lon,
                "radius_m": radius_m,
            },
            "metadata": {
                "sector_strategy": "distance_equal_v1",
                "num_sectors": len(sectors),
                "source_session": session.description
            },
            "sectors": sectors,
            "location": "Unknown",
            "created_at": "now"
        }

        # 8. Create Folder & Save Artifacts
        try:
            os.makedirs(track_dir, exist_ok=True)
            
            # A. Save track.json (Frozen)
            track_json_path = os.path.join(track_dir, "track.json")
            with open(track_json_path, 'w') as f:
                json.dump(track_data, f, indent=4)
                
            # A2. Save geometry.json (New in Phase 7.2)
            geo_json_path = os.path.join(track_dir, "geometry.json")
            geometry_data = {
                "coordinates": list(zip(final_lats, final_lons)),
                "sector_indices": sector_indices
            }
            with open(geo_json_path, 'w') as f:
                json.dump(geometry_data, f)
                
            # B. Initialize tbl.json (Mutable)
            tbl_json_path = os.path.join(track_dir, "tbl.json")
            default_tbl = {
                "track_id": track_id,
                "sectors": [],
                "total_best_time": None,
                "best_real_lap": {"time": None, "session": None} 
            }
            with open(tbl_json_path, 'w') as f:
                json.dump(default_tbl, f, indent=4)
                
            # C. Generate Map using SMOOTHED data
            from src.analysis.core.track_visualizer import TrackVisualizer
            map_path = os.path.join(track_dir, "track_map.png")
            
            TrackVisualizer.generate_track_map(final_lats, final_lons, track_data, map_path)
            
            # D. Register track in registry.json for UI
            self.registry.register_track(track_id, track_name, folder_name)
            
            print(f"[TrackGenerator] Successfully generated track ID {track_id}: {folder_name}/")
            return track_data
            
        except Exception as e:
            print(f"[TrackGenerator] Failed to save track artifacts: {e}")
            return None

    def _detect_start_line_candidate(self, session: Session, radius_m: float) -> tuple[float, float]:
        """
        Scans for the 'First Valid Loop Closure' within the racing circuit.
        Criteria:
        1. Point A (early) and Point B (later) are spatially close (< radius).
        2. Heading at A matches Heading at B (within 45 deg).
        3. Skips initial samples to avoid pit exit/entry roads.
        """
        samples = session.samples
        if not samples:
            print("[TrackGenerator] Error: No samples.")
            return 0.0, 0.0
            
        step = 1 # High precision scan
        buffer_frames = 600 # ~60s - ensure we're finding full lap closures
        skip_initial = 300 # Skip first 30s to avoid pit exit/entry areas
        
        limit = min(len(samples), 5000) 

        print("[TrackGenerator] Scanning for First Loop Closure (Skipping pit areas)...")
        
        import math
        def get_heading(idx):
             # Simple heading using next point
             if idx >= len(samples) - 1: return 0.0
             s1 = samples[idx]
             s2 = samples[idx+1]
             # simple bearing calculation
             y = math.sin(math.radians(s2.gps.lon - s1.gps.lon)) * math.cos(math.radians(s2.gps.lat))
             x = math.cos(math.radians(s1.gps.lat)) * math.sin(math.radians(s2.gps.lat)) - \
                 math.sin(math.radians(s1.gps.lat)) * math.cos(math.radians(s2.gps.lat)) * math.cos(math.radians(s2.gps.lon - s1.gps.lon))
             return math.degrees(math.atan2(y, x)) % 360.0

        min_speed_kmh = 30.0 # Force start line to be on track (not in pits)
        min_speed_warning_printed = False

        for i in range(skip_initial, limit, step):
            candidate = samples[i]
            
            # Speed Filter: Ignore points where we are too slow (Pits)
            if candidate.gps.speed < min_speed_kmh:
                if not min_speed_warning_printed:
                    # Debug log once per session to avoid spam
                    # print(f"[TrackGenerator] Skipping candidate at index {i} (Speed {candidate.gps.speed:.1f} < {min_speed_kmh})")
                    min_speed_warning_printed = True
                continue

            c_lat, c_lon = candidate.gps.lat, candidate.gps.lon
            
            search_start = i + buffer_frames
            if search_start >= len(samples): break
            
            c_heading = get_heading(i)
            
            for j in range(search_start, len(samples), 5):
                s = samples[j]
                
                # Fast Euclidian
                if abs(s.gps.lat - c_lat) > 0.002: continue 
                
                d = haversine_distance(c_lat, c_lon, s.gps.lat, s.gps.lon) * 1000.0
                
                if d < radius_m:
                    # Spatially close. Check Heading.
                    s_heading = get_heading(j)
                    heading_diff = abs(c_heading - s_heading)
                    if heading_diff > 180: heading_diff = 360 - heading_diff
                    
                    if heading_diff < 60: # Allow some cornering variation, but must be roughly same direction
                        print(f"[TrackGenerator] Valid Loop Closure at Index {i} (Time {candidate.timestamp:.1f}).")
                        print(f"  > Speed: {candidate.gps.speed:.1f} km/h (Threshold: {min_speed_kmh})")
                        print(f"  > Heading Match: A={c_heading:.0f}, B={s_heading:.0f} (Diff={heading_diff:.0f})")
                        print(f"  > Snapping Start Line to Racing Line (2nd Pass, Index {j}).")
                        print(f"  > Start Line set to: {s.gps.lat:.6f}, {s.gps.lon:.6f}")
                        return s.gps.lat, s.gps.lon
                    
        print("[TrackGenerator] No valid closed loop found. Defaulting to Start.")
        return samples[0].gps.lat, samples[0].gps.lon

    def _calculate_sectors_from_coords(self, lats: List[float], lons: List[float], start_lat: float, start_lon: float) -> List[Dict]:
        """
        Calculates sectors based on equidistant splits of the coordinate geometry.
        """
        # Calculate cumulative distance
        dists = [0.0]
        total = 0.0
        for i in range(1, len(lats)):
            d = haversine_distance(lats[i-1], lons[i-1], lats[i], lons[i]) * 1000.0
            total += d
            dists.append(total)

        num_sectors = config.SECTOR_COUNT
        step = total / num_sectors
        # Dynamic Radius Calculation to prevent overlap on short tracks
        # Radius should be less than half the sector length (step / 2)
        # We target 40% of step, clamped between 5m and 30m.
        dynamic_radius = max(5.0, min(30.0, step * 0.4))
        
        sectors = []
        indices = []

        for i in range(1, num_sectors + 1):
            target_dist = step * i
            
            if i == num_sectors:
                # Force exact snap
                s_lat, s_lon = start_lat, start_lon
                # Find index for start (usually 0 or -1)
                closest_idx = 0 
            else:
                # Find point
                closest_idx = min(range(len(dists)), key=lambda k: abs(dists[k] - target_dist))
                s_lat, s_lon = lats[closest_idx], lons[closest_idx]

            sectors.append({
                "id": f"S{i}",
                "end_lat": s_lat,
                "end_lon": s_lon,
                "radius_m": round(dynamic_radius, 1)
            })
            indices.append(closest_idx)
            
        return sectors, indices

