import json
import math
import os
import uuid
from typing import Any, Dict, List, Optional
import datetime
from datetime import timezone, timedelta

# IST timezone (GMT+5:30) for all user-facing dates
IST = timezone(timedelta(hours=5, minutes=30))
from src.analysis.core.models import Session, Lap
import src.config as config
from src.analysis.processing.diagnostics import DiagnosticsEngine
from src.analysis.processing.stats import StatsEngine

class SessionExporter:
    """
    Generates and persists a self-contained JSON representation of a Session.
    This JSON is consumed by UI/Apps (Phase 5).
    """

    def __init__(self, output_dir: str = None, tracks_dir: str = None):
        self.output_dir = output_dir if output_dir else config.SESSIONS_DIR
        self.tracks_dir = tracks_dir if tracks_dir else config.TRACKS_DIR
        if not os.path.exists(self.output_dir):
            try:
                os.makedirs(self.output_dir)
            except OSError:
                pass # Might not have permissions if running locally vs Pi

    def export(self, session: Session, track_info: Dict, tbl_data: Optional[Dict], 
               best_real_lap_ref: Optional[float] = None, source_file: Optional[str] = None) -> str:
        """
        Builds the JSON and saves it. Returns the file path.
        """
        
        # 1. Meta
        # Generate a stable UUID based on session start time + Description? 
        # For now, just a random UUID or derived from filename if available.
        sess_id = str(uuid.uuid4())
        
        st_ts = session.start_time
        et_ts = session.end_time
        dur = session.duration
        
        # Convert timestamps to ISO8601 in IST (derived from GPS timestamp)
        st_iso = datetime.datetime.fromtimestamp(st_ts, tz=IST).isoformat() if st_ts else None
        et_iso = datetime.datetime.fromtimestamp(et_ts, tz=IST).isoformat() if et_ts else None
        
        data = {
            "meta": {
                "session_id": sess_id,
                "session_name": session.description,
                "source_file": source_file,  # Track which CSV produced this session
                "start_time": st_iso,
                "end_time": et_iso,
                "duration_sec": round(dur, 2),
                "logger_version": "v3.6",
                "schema_version": "1.2",
                "source_mode": ((getattr(session, 'calibration', {}) or {}).get("source_mode")),
            },
            "environment": {
                 # Placeholder: In future, get from EnvSample stats
                "track_temperature": None,
                "ambient_temperature": None,
                "gps_quality_summary": self._extract_gps_stats(session)
            },
            "mode": {
                "mode_type": "active", # Default assumed, ideally passed in
                "learning_active": False,
                "notes": ""
            },
            "calibration": getattr(session, 'calibration', None),
            "analysis": {
                "signals": getattr(session, 'derived_signals', {}),
                "metrics": getattr(session, 'sensor_metrics', None),
                "diagnostics": {} # Will populate below
            },
            "track": {
                "track_id": track_info.get("track_id", 0),
                "track_name": track_info.get("track_name", "Unknown Track"),
                "track_scope": track_info.get("track_scope", "user_fallback"),
                "track_source": track_info.get("track_source", "session_generated"),
                "has_canonical_layout": bool(track_info.get("has_canonical_layout")),
                "package_version": track_info.get("package_version"),
                "folder_name": track_info.get("folder_name"),
                "sector_count": len(track_info.get("sectors", [])),
                "sector_definition_source": {
                     "fastest_lap_session_id": track_info.get("start_line", {}).get("source_session", None),
                     "fastest_lap_time": None # Not strictly tracked in current TrackJSON
                }
            },
            "references": self._build_references(track_info, tbl_data, best_real_lap_ref),
            "laps": self._build_laps_list(session, track_info),
            "sectors": self._build_sector_stats(session, track_info),
            "deltas": {
                # Placeholder for complex gain/loss analysis
                "distance_aligned_delta_summary": [],
                "max_gain": 0.0,
                "max_loss": 0.0,
                "mean_delta": 0.0,
                "sector_delta_summary": [] 
            },
            "aggregates": {
                "best_lap_time": self._find_best_lap_time(session),
                "gap_to_theoretical_best": self._calc_gap_to_tbl(session, tbl_data),
                "consistency_score": None
            },
            "integrity": {
                "clean_shutdown": True, # Presumed if we are here exporting
                "data_loss_detected": False,
                "gps_reliability_score": 1.0, 
                "warnings": []
            }
        }
        
        # 8.1 Diagnostics Integration
        try:
            diag_engine = DiagnosticsEngine()
            diag_report = diag_engine.analyze_session(session, track_info)
            data["analysis"]["diagnostics"] = diag_report
            data["aggregates"]["consistency_score"] = diag_report.get("consistency_score")
        except Exception as e:
            print(f"[Exporter] Diagnostics failed: {e}")
            data["analysis"]["diagnostics"] = {"error": str(e)}

        # Save with date-based naming: jan21Session1.json
        track_id = track_info.get("track_id", 0)
        
        # Get folder name from registry
        from src.analysis.core.registry_manager import RegistryManager
        # Use provided tracks_dir to find individual user's registry
        registry = RegistryManager(registry_path=self.tracks_dir)
        folder_name = registry.get_folder_name(track_id) or f"track_{track_id}"
        
        filename = self._generate_session_filename(st_ts, folder_name)
        
        # Update session_id and session_name to match filename (without .json)
        session_name = filename.replace(".json", "")
        data["meta"]["session_id"] = session_name
        data["meta"]["session_name"] = session_name  # Use date-based name instead of CSV filename
              
        out_path = os.path.join(self.output_dir, filename)
        
        try:
            with open(out_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            # 7.4.1 Separate Telemetry export
            self._export_telemetry(session, out_path)
            self._export_playback(session, track_info, out_path)
            
            return out_path
        except Exception as e:
            print(f"[SessionExporter] Failed to write JSON: {e}")
            return ""

    def _export_telemetry(self, session: Session, main_path: str):
        """
        Saves session telemetry to <session>_telemetry.json.
        Structure of Arrays (Columnar) for compactness.
        """
        if not session.samples: return

        t_path = main_path.replace(".json", "_telemetry.json")
        
        # Base Timestamp
        t0 = session.samples[0].timestamp
        
        # Build Columns
        # Rounding for file size optimization
        times = [round(s.timestamp - t0, 3) for s in session.samples]
        lats = [round(s.gps.lat, 6) if getattr(s, "gps_is_valid", True) else None for s in session.samples]
        lons = [round(s.gps.lon, 6) if getattr(s, "gps_is_valid", True) else None for s in session.samples]
        speeds = [round(s.gps.speed, 1) if getattr(s, "gps_is_valid", True) else None for s in session.samples]
        
        # Base keys
        payload = {
            "time": times,
            "lat": lats,
            "lon": lons,
            "speed": speeds,
            "gps_is_fix": [bool(getattr(s, "gps_is_fix", True)) for s in session.samples],
            "gps_is_valid": [bool(getattr(s, "gps_is_valid", True)) for s in session.samples],
            "source_mode": ((getattr(session, 'calibration', {}) or {}).get("source_mode")),
        }
        
        # 7.3 Raw IMU Data (Always export for client-side viz)
        # Assuming IMU is present in samples
        if session.samples and session.samples[0].imu:
            def safe_round(val, p): return round(val, p) if val is not None else 0
            
            payload["raw_ax"] = [safe_round(s.imu.accel_x, 3) for s in session.samples]
            payload["raw_ay"] = [safe_round(s.imu.accel_y, 3) for s in session.samples]
            payload["raw_az"] = [safe_round(s.imu.accel_z, 3) for s in session.samples]
            
            # Gyro if available
            if session.samples[0].imu.gyro_x is not None:
                payload["raw_gx"] = [safe_round(s.imu.gyro_x, 2) for s in session.samples]
                payload["raw_gy"] = [safe_round(s.imu.gyro_y, 2) for s in session.samples]
                payload["raw_gz"] = [safe_round(s.imu.gyro_z, 2) for s in session.samples]

        # 7.4 Aligned Signal Overrides
        if hasattr(session, 'derived_signals') and session.derived_signals:
            ds = session.derived_signals
            if 'aligned_accel_x' in ds:
                payload['ax'] = [round(x, 2) for x in ds['aligned_accel_x']]
                payload['ay'] = [round(x, 2) for x in ds['aligned_accel_y']]
                # payload['az'] = ... 
            
            # Export Kalman-Fused Lean Angle if available
            if 'lean_angle' in ds:
                payload['lean_angle'] = [round(x, 1) for x in ds['lean_angle']] 
                
        try:
            with open(t_path, 'w') as f:
                json.dump(payload, f) # Minified (no indent)
        except Exception as e:
            print(f"  [!] Failed to save telemetry: {e}")

    def _export_playback(self, session: Session, track_info: Dict, main_path: str):
        if not session.samples:
            return

        playback_path = main_path.replace(".json", "_playback.json")
        t0 = session.samples[0].timestamp
        playback_dataset = getattr(session, "playback_dataset", {}) or {}
        playback_signals = playback_dataset.get("signals", {}) or {}
        gps_references = playback_dataset.get("gps_references", {}) or {}
        playback_config = playback_dataset.get("config", {}) or {}
        playback_laps = self._build_laps_list(session, track_info, laps_override=getattr(session, "playback_laps", None), reference_laps=getattr(session, "laps", None))
        rows = self._build_playback_rows(session, playback_laps, t0, playback_signals, gps_references, playback_config)
        payload = {
            "meta": {
                "source_mode": ((getattr(session, 'calibration', {}) or {}).get("source_mode")),
                "gps_lag_ms_applied": playback_config.get("gpsLagMs", 0),
                "row_count": len(rows),
            },
            "config": playback_config,
            "laps": playback_laps,
            "rows": rows,
        }
        try:
            with open(playback_path, "w") as f:
                json.dump(payload, f)
        except Exception as e:
            print(f"  [!] Failed to save playback: {e}")

    def _build_playback_rows(
        self,
        session: Session,
        laps: List[Dict[str, Any]],
        t0: float,
        playback_signals: Dict[str, List[float]],
        gps_references: Dict[str, List[float]],
        playback_config: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        times = [round(sample.timestamp - t0, 3) for sample in session.samples]
        headings = self._build_heading_series(session)
        gps_lag_ms = int(playback_config.get("gpsLagMs", 0) or 0)
        gps_lean_ref = self._shift_series_by_lag(times, gps_references.get("gps_lean_deg", []), gps_lag_ms)
        gps_long_ref = self._shift_series_by_lag(times, gps_references.get("gps_long_g", []), gps_lag_ms)
        lap_start_indices = self._nearest_time_indices(times, [lap.get("start_time") for lap in laps])
        lap_end_indices = self._nearest_time_indices(times, [lap.get("end_time") for lap in laps])
        sector_boundary_times = []
        for lap in laps:
            sector_elapsed = 0.0
            for sector_duration in lap.get("sector_times", []):
                if sector_duration is None:
                    break
                sector_elapsed += float(sector_duration)
                sector_boundary_times.append(lap["start_time"] + sector_elapsed)
        sector_end_indices = self._nearest_time_indices(times, sector_boundary_times)
        sector_start_indices = set()
        sector_start_indices.update(lap_start_indices)
        for index in sector_end_indices:
            next_index = min(index + 1, max(0, len(times) - 1))
            sector_start_indices.add(next_index)

        rows = []
        for index, sample in enumerate(session.samples):
            time_rel = times[index]
            active_lap = self._lap_for_time(laps, time_rel)
            active_sector = self._sector_for_time(active_lap, time_rel) if active_lap else None
            lat = round(sample.gps.lat, 6) if getattr(sample, "gps_is_valid", True) else None
            lon = round(sample.gps.lon, 6) if getattr(sample, "gps_is_valid", True) else None
            speed = round(sample.gps.speed, 1) if getattr(sample, "gps_is_valid", True) else None
            row = {
                "time": time_rel,
                "lat": lat,
                "lon": lon,
                "speed_kmh": speed,
                "heading_deg": headings[index],
                "lean_deg": self._signal_value(playback_signals.get("lean_deg"), index, 1),
                "long_g": self._signal_value(playback_signals.get("long_g"), index, 3),
                "lat_g": self._signal_value(playback_signals.get("lat_g"), index, 3),
                "accel_g": self._signal_value(playback_signals.get("accel_g"), index, 3),
                "brake_g": self._signal_value(playback_signals.get("brake_g"), index, 3),
                "lap_number": active_lap.get("lap_number") if active_lap else None,
                "lap_start": index in lap_start_indices,
                "lap_end": index in lap_end_indices,
                "sector_index": active_sector.get("sector_index") if active_sector else None,
                "sector_start": index in sector_start_indices,
                "sector_end": index in sector_end_indices,
                "gps_is_fix": bool(getattr(sample, "gps_is_fix", True)),
                "gps_is_valid": bool(getattr(sample, "gps_is_valid", True)),
                "gps_lean_ref_deg": self._signal_value(gps_lean_ref, index, 1),
                "gps_long_ref_g": self._signal_value(gps_long_ref, index, 3),
                "gps_lag_ms_applied": gps_lag_ms,
            }
            rows.append(row)
        return rows

    def _lap_for_time(self, laps: List[Dict[str, Any]], time_rel: float) -> Optional[Dict[str, Any]]:
        for lap in laps:
            if time_rel < lap.get("start_time", 0.0):
                continue
            if time_rel <= lap.get("end_time", lap.get("start_time", 0.0)):
                return lap
        return None

    def _sector_for_time(self, lap: Dict[str, Any], time_rel: float) -> Optional[Dict[str, Any]]:
        sector_times = lap.get("sector_times", [])
        elapsed = lap.get("start_time", 0.0)
        for offset, duration in enumerate(sector_times, start=1):
            if duration is None:
                continue
            elapsed += float(duration)
            if time_rel <= elapsed:
                return {"sector_index": offset}
        if sector_times:
            return {"sector_index": len(sector_times)}
        return None

    def _nearest_time_indices(self, times: List[float], boundaries: List[Optional[float]]) -> set:
        indices = set()
        if not times:
            return indices
        for boundary in boundaries:
            if boundary is None:
                continue
            closest = min(range(len(times)), key=lambda idx: abs(times[idx] - boundary))
            indices.add(closest)
        return indices

    def _shift_series_by_lag(self, times: List[float], values: List[float], lag_ms: int) -> List[Optional[float]]:
        if not values or len(values) != len(times):
            return []
        lag_sec = float(lag_ms) / 1000.0
        shifted = []
        source_index = 0
        for current_time in times:
            target = current_time - lag_sec
            while source_index + 1 < len(times) and times[source_index + 1] <= target:
                source_index += 1
            if source_index + 1 < len(times):
                left_distance = abs(times[source_index] - target)
                right_distance = abs(times[source_index + 1] - target)
                closest = source_index if left_distance <= right_distance else source_index + 1
            else:
                closest = source_index
            shifted.append(values[closest])
        return shifted

    def _signal_value(self, values: Optional[List[Any]], index: int, precision: int):
        if not values or index >= len(values):
            return None
        value = values[index]
        if value is None:
            return None
        try:
            return round(float(value), precision)
        except Exception:
            return None

    def _build_heading_series(self, session: Session) -> List[Optional[float]]:
        valid_points = []
        for index, sample in enumerate(session.samples):
            if not getattr(sample, "gps_is_valid", True):
                continue
            valid_points.append((index, sample.gps.lat, sample.gps.lon))
        headings: List[Optional[float]] = [None] * len(session.samples)
        if len(valid_points) < 2:
            return headings

        for point_index, (sample_index, lat, lon) in enumerate(valid_points):
            if point_index < len(valid_points) - 1:
                _, next_lat, next_lon = valid_points[point_index + 1]
                heading = self._bearing_deg(lat, lon, next_lat, next_lon)
            else:
                _, prev_lat, prev_lon = valid_points[point_index - 1]
                heading = self._bearing_deg(prev_lat, prev_lon, lat, lon)
            headings[sample_index] = heading

        last_heading = None
        for index in range(len(headings)):
            if headings[index] is not None:
                last_heading = headings[index]
            elif last_heading is not None:
                headings[index] = last_heading
        next_heading = None
        for index in range(len(headings) - 1, -1, -1):
            if headings[index] is not None:
                next_heading = headings[index]
            elif next_heading is not None:
                headings[index] = next_heading
        return [round(value, 1) if value is not None else None for value in headings]

    def _bearing_deg(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        lat1_r = math.radians(lat1)
        lat2_r = math.radians(lat2)
        dlon = math.radians(lon2 - lon1)
        x = math.sin(dlon) * math.cos(lat2_r)
        y = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlon)
        return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0
    
    def _generate_session_filename(self, session_timestamp: float, folder_name: str) -> str:
        """
        Generate date-based session filename: 23-Mar-Sess-01.json
        Uses GPS timestamp in IST to derive date, then finds next available number for that day.
        """
        # Parse GPS timestamp to IST date components
        if session_timestamp:
            session_dt = datetime.datetime.fromtimestamp(session_timestamp, tz=IST)
        else:
            session_dt = datetime.datetime.now(tz=IST)
        
        # Format: 23-Mar, 05-Feb, etc.
        day = session_dt.strftime("%d")           # '23', '05', etc.
        month_abbrev = session_dt.strftime("%b")  # 'Mar', 'Feb', etc.
        date_prefix = f"{day}-{month_abbrev}"     # '23-Mar'
        
        # Find existing sessions with this date prefix
        existing = []
        
        if os.path.exists(self.output_dir):
            for file in os.listdir(self.output_dir):
                # Match pattern: 23-Mar-Sess-01.json (case insensitive)
                if file.lower().startswith(date_prefix.lower()) and file.endswith(".json") and not file.endswith("_telemetry.json"):
                    try:
                        # Remove date prefix and .json to get '-Sess-01'
                        session_part = file[len(date_prefix):].replace(".json", "")
                        # Extract number after '-Sess-'
                        if session_part.lower().startswith("-sess-"):
                            num_part = session_part[6:]  # Skip '-Sess-' (6 chars)
                            session_num = int(num_part)
                            existing.append(session_num)
                    except (ValueError, IndexError):
                        continue
        
        # Next number is max + 1, or 1 if none exist
        next_num = max(existing) + 1 if existing else 1
        return f"{date_prefix}-Sess-{next_num:02d}.json"

    def _extract_gps_stats(self, session: Session) -> Dict:
        if not session.samples:
            return {"total_fixes": 0, "fix_dropouts": 0}
        
        fixes = len(session.samples)
        # Naive dropout check: timestamps > 0.2s apart?
        # For now return basics
        return {
            "total_fixes": fixes,
            "fix_dropouts": 0 # Placeholder logic
        }

    def _build_references(self, track_info, tbl_data, best_real_ref):
        refs = {
            "best_real_lap_reference": {
                "lap_time": best_real_ref,
                "session_id": None # We'd need to fetch from TrackJSON records
            },
            "theoretical_best_reference": None,
            "sector_times": [],
            "reference_type_used_for_deltas": "theoretical"
        }
        
        if tbl_data:
            refs["theoretical_best_reference"] = tbl_data.get("total_best_time")
            # Extract sector times ordered
            sectors = sorted(tbl_data.get("sectors", []), key=lambda x: x["sector_index"])
            refs["sector_times"] = [s["best_time"] for s in sectors]
            
        return refs

    def _build_laps_list(self, session: Session, track_info: Dict = None, laps_override: Optional[List[Lap]] = None, reference_laps: Optional[List[Lap]] = None) -> List[Dict]:
        laps_out = []
        lap_source = laps_override if laps_override is not None else getattr(session, "laps", [])
        best_time = self._find_best_lap_time_from_laps(lap_source)
        reference_by_number = {lap.lap_number: lap for lap in (reference_laps or getattr(session, "laps", []) or [])}
        
        t0 = session.start_time
        
        for lap in lap_source:
            # Calculate relative start time for syncing with telemetry
            start_rel = 0.0
            end_rel = 0.0
            if lap.samples:
                start_rel = round(lap.start_time - t0, 3)
                end_rel = round(lap.end_time - t0, 3)

            l_data = {
                "lap_index": lap.lap_number - 1, # 0-indexed schema
                "lap_number": lap.lap_number,    # Human readable
                "start_time": start_rel,         # Relative to session start (seconds)
                "end_time": end_rel,             # Relative to session start (seconds)
                "lap_time": round(lap.duration, 3) if lap.duration else None,
                "valid": getattr(lap, 'valid', True),
                "reason_invalid": None, # Logic not yet present
                "sector_times": [],
                "delta_to_reference": round(lap.duration - best_time, 3) if (lap.duration and best_time) else 0.0,
                "is_session_best": (lap.duration == best_time and lap.duration > 0),
                "delta_to_gps_only": None,
            }

            reference_lap = reference_by_number.get(lap.lap_number)
            if reference_lap and lap.duration and reference_lap.duration:
                l_data["delta_to_gps_only"] = round(lap.duration - reference_lap.duration, 3)
            
            # Sectors
            # Dict to List based on keys S1, S2...
            # Ensure dense array matching Sector Count
            num_sectors = 0
            if track_info and "sectors" in track_info:
                num_sectors = len(track_info["sectors"])
            else:
                 # Fallback: Infer from keys if track_info missing (should not happen in flow)
                 s_keys_chk = sorted(lap.sector_times.keys(), key=lambda x: int(x[1:]) if x[1:].isdigit() else 0)
                 if s_keys_chk:
                     last_key = s_keys_chk[-1]
                     if last_key[1:].isdigit():
                         num_sectors = int(last_key[1:])

            dense_sectors = []
            for i in range(1, num_sectors + 1):
                key = f"S{i}"
                dense_sectors.append(lap.sector_times.get(key)) # None if missing
                
            l_data["sector_times"] = dense_sectors
            
            laps_out.append(l_data)
            
        return laps_out

    def _build_sector_stats(self, session: Session, track_info: Dict) -> List[Dict]:
        stats = []
        sectors_def = track_info.get("sectors", [])
        
        for sec in sectors_def:
            sec_id = StatsEngine.sector_time_key(sec)
            # Gather all times for this sector
            times = []
            for lap in session.laps:
                val = lap.sector_times.get(sec_id)
                if val: times.append(val)
            
            if not times:
                continue
                
            stats.append({
                "sector_index": sec.get("sector_index", sec.get("id")),
                "best_time_this_session": min(times),
                "median_time": sorted(times)[len(times)//2],
                "worst_time": max(times),
                "laps_count": len(times)
            })
            
        return stats

    def _find_best_lap_time(self, session: Session) -> Optional[float]:
        # valid = [l.duration for l in session.laps if l.valid and l.duration > 0]
        # Assuming all present laps are valid for now
        valid = [l.duration for l in session.laps if l.duration > 0]
        return min(valid) if valid else None

    def _find_best_lap_time_from_laps(self, laps: List[Lap]) -> Optional[float]:
        valid = [lap.duration for lap in laps if lap.duration > 0]
        return min(valid) if valid else None

    def _calc_gap_to_tbl(self, session, tbl_data) -> Optional[float]:
        best = self._find_best_lap_time(session)
        if best and tbl_data and tbl_data.get("total_best_time"):
            return round(best - tbl_data["total_best_time"], 3)
        return None
