import os
import json
from typing import Dict, Optional, List
import src.config as config
from src.analysis.core.models import Session, Lap, Sample, GPSSample, IMUSample, EnvSample
from src.analysis.processing.geo import haversine_distance
from src.analysis.processing.laps import LapDetector, StartLine
from src.analysis.core.registry_manager import RegistryManager

try:
    import matplotlib.pyplot as plt  # noqa: F401
except Exception:
    plt = None

class TrackGenerator:
    """
    Modular logic to generate Track JSON (and geometry) from a Session.
    Used for both 'Learning Mode' and 'Auto-Track' generation.
    """

    def __init__(self, tracks_dir: str = None):
        self.output_dir = tracks_dir if tracks_dir else config.TRACKS_DIR
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Initialize Registry Manager for sequential track IDs
        registry_path = os.path.join(self.output_dir, "registry.json")
        self.registry = RegistryManager(registry_path=registry_path)

    @staticmethod
    def _gps_fix_count(session: Session) -> int:
        meta = getattr(session, "device_metadata", {}) or {}
        count = meta.get("gps_fix_count")
        if isinstance(count, int):
            return count
        return sum(1 for sample in session.samples if getattr(sample, "gps_is_fix", True))

    @staticmethod
    def _has_sufficient_gps_coverage(session: Session) -> bool:
        if not session.samples or session.duration <= 0:
            return False

        meta = getattr(session, "device_metadata", {}) or {}
        gps_fix_count = TrackGenerator._gps_fix_count(session)
        gps_fix_span_s = float(meta.get("gps_fix_span_s") or 0.0)
        coverage_ratio = gps_fix_span_s / session.duration if session.duration > 0 else 0.0
        return gps_fix_count >= 50 and coverage_ratio >= 0.5

    @staticmethod
    def _lap_path_samples(lap: Lap) -> List:
        gps_fix_samples = [sample for sample in lap.samples if getattr(sample, "gps_is_fix", True)]
        source_samples = gps_fix_samples if len(gps_fix_samples) >= 16 else list(lap.samples)

        filtered = []
        last_lat = None
        last_lon = None
        for sample in source_samples:
            lat = sample.gps.lat
            lon = sample.gps.lon
            if lat == 0.0 or lon == 0.0:
                continue
            if last_lat is not None and lat == last_lat and lon == last_lon:
                continue
            filtered.append(sample)
            last_lat = lat
            last_lon = lon

        return filtered

    @staticmethod
    def _gps_only_session(session: Session) -> Session:
        gps_samples = []
        for sample in session.samples:
            if not getattr(sample, "gps_is_fix", True):
                continue
            lat = sample.gps.lat
            lon = sample.gps.lon
            if lat == 0.0 or lon == 0.0:
                continue
            gps_samples.append(
                Sample(
                    timestamp=sample.timestamp,
                    gps=GPSSample(sample.gps.lat, sample.gps.lon, sample.gps.speed, sample.gps.sats),
                    imu=IMUSample(
                        sample.imu.accel_x,
                        sample.imu.accel_y,
                        sample.imu.accel_z,
                        sample.imu.gyro_x,
                        sample.imu.gyro_y,
                        sample.imu.gyro_z,
                    ),
                    env=EnvSample(sample.env.temp, sample.env.pressure),
                    gps_is_fix=True,
                )
            )

        gps_session = Session(description=f"{session.description} (gps only)", samples=gps_samples)
        gps_session.device_metadata = dict(getattr(session, "device_metadata", {}) or {})
        gps_session.device_metadata["gps_fix_count"] = len(gps_samples)
        if gps_samples:
            gps_session.device_metadata["gps_fix_span_s"] = max(0.0, gps_samples[-1].timestamp - gps_samples[0].timestamp)
        return gps_session

    @staticmethod
    def _path_distance_m(samples: List) -> float:
        total = 0.0
        for idx in range(1, len(samples)):
            total += haversine_distance(
                samples[idx - 1].gps.lat,
                samples[idx - 1].gps.lon,
                samples[idx].gps.lat,
                samples[idx].gps.lon,
            ) * 1000.0
        return total

    @staticmethod
    def _build_centerline(lap: Lap) -> List[Dict]:
        path_samples = TrackGenerator._lap_path_samples(lap)
        if len(path_samples) < 3:
            return []
        centerline = [{"lat": sample.gps.lat, "lon": sample.gps.lon} for sample in path_samples]

        if centerline:
            loop_gap_m = haversine_distance(
                centerline[0]["lat"], centerline[0]["lon"],
                centerline[-1]["lat"], centerline[-1]["lon"],
            ) * 1000.0
            if loop_gap_m > 5.0:
                centerline.append(dict(centerline[0]))
            else:
                centerline[-1] = dict(centerline[0])

        return centerline

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

        if not self._has_sufficient_gps_coverage(session):
            gps_fix_count = self._gps_fix_count(session)
            gps_fix_span_s = float((getattr(session, "device_metadata", {}) or {}).get("gps_fix_span_s") or 0.0)
            coverage_ratio = gps_fix_span_s / session.duration if session.duration > 0 else 0.0
            print(
                f"[TrackGenerator] Insufficient GPS coverage for fallback generation "
                f"(fixes={gps_fix_count}, span={gps_fix_span_s:.1f}s, coverage={coverage_ratio:.2%})."
            )
            return None

        gps_session = self._gps_only_session(session)
        if len(gps_session.samples) < 16:
            print("[TrackGenerator] Not enough real GPS fixes for fallback generation.")
            return None

        # 1. Identify Start (Smart Detection)
        start_lat, start_lon = self._detect_start_line_candidate(gps_session, radius_m)

        # 2. Detect Laps
        sl_obj = StartLine(start_lat, start_lon, radius_m)
        detector = LapDetector(sl_obj)
        laps = detector.detect(gps_session)

        if not laps:
            print("[TrackGenerator] No laps detected to infer geometry.")
            return None

        # 3. Find Reference Lap (Fastest Valid Flying Lap)
        # Filter outliers based on distance (exclude short Out laps or long In laps)
        valid_laps = [l for l in laps if l.duration > 0]
        if not valid_laps:
             print("[TrackGenerator] No valid laps found.")
             return None
             
        lap_distances = []
        for l in valid_laps:
            lap_distances.append(self._path_distance_m(self._lap_path_samples(l)))
            
        median_dist = sorted(lap_distances)[len(lap_distances)//2]
        print(f"[TrackGenerator] Median Lap Distance: {median_dist:.1f} m")
        
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
        print(f"[TrackGenerator] Selected Reference Lap {ref_lap.lap_number} (Time: {ref_lap.duration:.2f}s, Dist: {lap_distances[ref_lap_idx]:.1f}m)")

        # 4. Build a centerline from real GPS fixes rather than the full interpolated IMU timeline.
        centerline = self._build_centerline(ref_lap)
        if len(centerline) < 3:
            print("[TrackGenerator] Reference lap does not contain enough GPS geometry.")
            return None

        final_lats = [point["lat"] for point in centerline]
        final_lons = [point["lon"] for point in centerline]
        start_lat = final_lats[0]
        start_lon = final_lons[0]

        # 5. Generate sectors & indices
        sectors, sector_indices = self._calculate_sectors_from_coords(final_lats, final_lons, start_lat, start_lon)

        # 6. Build Track Dict
        track_data = {
            "id": track_id,
            "track_id": track_id,
            "name": track_name,
            "track_name": track_name,
            "track_scope": "user_fallback",
            "track_source": "session_generated",
            "has_canonical_layout": False,
            "folder_name": folder_name,
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
            "centerline": centerline,
            "sectors": sectors,
            "location": "Unknown",
            "created_at": "now"
        }

        # 7. Create Folder & Save Artifacts
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
                
            # C. Generate map using the selected raw GPS lap path
            if plt is not None:
                from src.analysis.core.track_visualizer import TrackVisualizer
                map_path = os.path.join(track_dir, "track_map.png")
                TrackVisualizer.generate_track_map(final_lats, final_lons, track_data, map_path)
            else:
                print("[TrackGenerator] Matplotlib unavailable. Skipping track_map.png generation.")
            
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
            
        # Estimate the effective scan rate from the current sample stream.
        # Track generation may operate on GPS-only samples, not the 100Hz IMU timeline.
        sample_rate = 10.0
        if len(samples) > 10:
            duration = samples[10].timestamp - samples[0].timestamp
            if duration > 0.05:
                sample_rate = 10.0 / duration
        hz = max(10, min(200, int(sample_rate)))

        step = max(1, hz // 10)
        buffer_frames = 60 * hz # ~60s - ensure we're finding full lap closures
        
        session_duration_s = (samples[-1].timestamp - samples[0].timestamp) if samples else 0
        skip_s = 30 if session_duration_s >= 180 else 10
        skip_initial = int(skip_s * hz) # Skip initial area carefully
        
        limit = min(len(samples), 500 * hz) # Limit to first 500s

        print(f"[TrackGenerator] Scanning for First Loop Closure at {hz}Hz (Skipping pit areas)...")
        
        import math
        def get_heading(idx):
             # Improved heading using look-back to handle "stair-step" GPS
             # Look back up to 2 seconds to find 5m of movement
             target_s = samples[idx]
             lookback_limit = min(idx, max(20, int(2.0 * hz)))
             for lookback in range(1, lookback_limit + 1):
                 s_prev = samples[idx - lookback]
                 d_km = haversine_distance(
                     s_prev.gps.lat, s_prev.gps.lon,
                     target_s.gps.lat, target_s.gps.lon
                 )
                 if d_km * 1000.0 > 5.0:  # Found 5m of movement
                     # Calc bearing from s_prev to target_s
                     y = math.sin(math.radians(target_s.gps.lon - s_prev.gps.lon)) * math.cos(math.radians(target_s.gps.lat))
                     x = math.cos(math.radians(s_prev.gps.lat)) * math.sin(math.radians(target_s.gps.lat)) - \
                         math.sin(math.radians(s_prev.gps.lat)) * math.cos(math.radians(target_s.gps.lat)) * math.cos(math.radians(target_s.gps.lon - s_prev.gps.lon))
                     return math.degrees(math.atan2(y, x)) % 360.0
             
             # Fallback to immediate next point if no lookback found movement
             if idx >= len(samples) - 1: return 0.0
             s1 = samples[idx]
             s2 = samples[idx+1]
             if s1.gps.lat == s2.gps.lat and s1.gps.lon == s2.gps.lon: return 0.0
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

        num_sectors = config.get_default_sector_count()
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
                "sector_index": i,
                "end_lat": s_lat,
                "end_lon": s_lon,
                "radius_m": round(dynamic_radius, 1),
                "progress_m": round(target_dist, 3),
            })
            indices.append(closest_idx)
            
        return sectors, indices
