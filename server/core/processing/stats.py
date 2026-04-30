import math
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
    def sector_time_key(sector: Dict, fallback_index: int = None) -> str:
        if isinstance(sector, dict):
            sector_index = sector.get("sector_index")
            try:
                sector_index = int(sector_index)
            except Exception:
                sector_index = None
            if sector_index is not None and sector_index > 0:
                return f"S{sector_index}"

            sector_id = sector.get("id")
            if isinstance(sector_id, str) and sector_id:
                return sector_id

        if fallback_index is not None:
            return f"S{fallback_index}"
        return ""

    @staticmethod
    def _normalize_start_line(start_line: Dict) -> Dict:
        if not isinstance(start_line, dict):
            return start_line
        center = start_line.get("center") if isinstance(start_line.get("center"), dict) else None
        if center and "lat" in center and "lon" in center:
            normalized = dict(start_line)
            normalized["lat"] = center["lat"]
            normalized["lon"] = center["lon"]
            return normalized
        if "lat" in start_line and "lon" in start_line:
            normalized = dict(start_line)
            normalized["center"] = {"lat": start_line["lat"], "lon": start_line["lon"]}
            return normalized
        return start_line

    @staticmethod
    def _ordered_centerline(track_info: Dict) -> List[Dict]:
        centerline = list(track_info.get("centerline") or [])
        if len(centerline) < 2:
            return centerline

        start_line = StatsEngine._normalize_start_line(track_info.get("start_line"))
        if not start_line:
            return centerline

        def distance_to_start(point):
            center = start_line.get("center") or start_line
            return math.hypot(float(point["lat"]) - float(center["lat"]), float(point["lon"]) - float(center["lon"]))

        closest_idx = min(range(len(centerline)), key=lambda idx: distance_to_start(centerline[idx]))
        return centerline[closest_idx:] + centerline[:closest_idx]

    @staticmethod
    def _cumulative_distances(points: List[Dict]) -> List[float]:
        if not points:
            return []
        distances = [0.0]
        total = 0.0
        for idx in range(1, len(points)):
            prev = points[idx - 1]
            curr = points[idx]
            total += haversine_distance(prev["lat"], prev["lon"], curr["lat"], curr["lon"]) * 1000.0
            distances.append(total)
        return distances

    @staticmethod
    def _centerline_progress_targets(sectors: List[Dict]):
        targets = []
        for sector_idx, sector in enumerate(sectors, start=1):
            progress_m = sector.get("progress_m")
            try:
                progress_m = float(progress_m)
            except Exception:
                return None
            targets.append((StatsEngine.sector_time_key(sector, fallback_index=sector_idx), progress_m))
        return targets

    @staticmethod
    def _nearest_centerline_index(lat: float, lon: float, ordered_centerline: List[Dict], start_index: int = 0):
        if len(ordered_centerline) < 2:
            return None, None
        best_index = None
        best_distance = None

        window_back = 2
        window_forward = min(max(32, len(ordered_centerline) // 8), len(ordered_centerline) - 1)

        def scan_range(idx_start, idx_end):
            nonlocal best_index, best_distance
            for idx in range(idx_start, idx_end + 1):
                distance = haversine_distance(lat, lon, ordered_centerline[idx]["lat"], ordered_centerline[idx]["lon"]) * 1000.0
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_index = idx

        local_start = max(0, start_index - window_back)
        local_end = min(len(ordered_centerline) - 1, start_index + window_forward)
        scan_range(local_start, local_end)

        if best_distance is None or best_distance > 60.0:
            best_index = None
            best_distance = None
            scan_range(0, len(ordered_centerline) - 1)

        return best_index, best_distance

    @staticmethod
    def _sample_progress_series(lap: Lap, ordered_centerline: List[Dict], cumulative: List[float]):
        sample_progress = []
        current_index = 0
        current_progress = 0.0

        for sample in lap.samples:
            idx, distance_m = StatsEngine._nearest_centerline_index(
                sample.gps.lat,
                sample.gps.lon,
                ordered_centerline,
                start_index=current_index,
            )
            if idx is None:
                continue

            progress = cumulative[idx]
            if progress < current_progress:
                progress = current_progress
            else:
                current_index = idx
                current_progress = progress

            sample_progress.append((sample.timestamp, progress, distance_m))

        return sample_progress

    @staticmethod
    def _progress_times_are_plausible(sector_times: Dict, lap_duration: float, sector_count: int) -> bool:
        if not sector_times or lap_duration <= 0:
            return False

        ordered = [sector_times.get(f"S{i}") for i in range(1, sector_count + 1)]
        if any(value is None for value in ordered):
            return False

        non_final = ordered[:-1]
        if not non_final:
            return False

        tiny_count = sum(1 for value in non_final if value < 1.0)
        if tiny_count > max(1, len(non_final) // 2):
            return False

        non_final_total = sum(non_final)
        if non_final_total <= 0 or non_final_total >= lap_duration:
            return False

        return True

    @staticmethod
    def _calculate_progress_based_sectors(lap: Lap, sectors: List[Dict], track_info: Dict) -> bool:
        ordered_centerline = StatsEngine._ordered_centerline(track_info)
        if len(ordered_centerline) < 2:
            return False

        cumulative = StatsEngine._cumulative_distances(ordered_centerline)
        targets = StatsEngine._centerline_progress_targets(sectors)
        if not targets or len(targets) < 2:
            return False

        sample_progress = StatsEngine._sample_progress_series(lap, ordered_centerline, cumulative)
        if not sample_progress:
            return False

        candidate_times = {}
        previous_split_time = lap.samples[0].timestamp
        previous_target = 0.0

        for sec_idx, (sec_id, target_progress) in enumerate(targets, start=1):
            if sec_idx == len(targets):
                total_so_far = sum(value for value in candidate_times.values() if value is not None)
                remainder = lap.duration - total_so_far
                candidate_times[sec_id] = remainder if remainder > 0 else 0.0
                continue

            if target_progress <= previous_target:
                return False

            crossed_ts = None
            for timestamp, progress, distance_m in sample_progress:
                if timestamp <= previous_split_time:
                    continue
                if progress >= target_progress and distance_m <= 60.0:
                    crossed_ts = timestamp
                    break

            if crossed_ts is None:
                return False

            candidate_times[sec_id] = crossed_ts - previous_split_time
            previous_split_time = crossed_ts
            previous_target = target_progress

        if not StatsEngine._progress_times_are_plausible(candidate_times, lap.duration, len(targets)):
            return False

        lap.sector_times.update(candidate_times)
        return True

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
            lap.sector_times = {}
            if StatsEngine._calculate_progress_based_sectors(lap, sectors, track_info):
                continue

            # For each sector, find when we crossed the end line
            # Default: Sector 1 starts at Lap Start.
            # Sector 2 starts at Sector 1 End.
            
            previous_split_time = lap.samples[0].timestamp
            last_split_valid = True
            
            for sector_idx, sector in enumerate(sectors, start=1):
                sec_id = StatsEngine.sector_time_key(sector, fallback_index=sector_idx)
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
