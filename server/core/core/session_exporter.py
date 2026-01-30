import json
import os
import uuid
from typing import Dict, List, Optional
import datetime
from src.analysis.core.models import Session, Lap
import src.config as config
from src.analysis.processing.diagnostics import DiagnosticsEngine

class SessionExporter:
    """
    Generates and persists a self-contained JSON representation of a Session.
    This JSON is consumed by UI/Apps (Phase 5).
    """

    def __init__(self, output_dir: str = None):
        self.output_dir = output_dir if output_dir else config.SESSIONS_DIR
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
        
        # Convert timestamps to ISO8601
        st_iso = datetime.datetime.fromtimestamp(st_ts).isoformat() + "Z" if st_ts else None
        et_iso = datetime.datetime.fromtimestamp(et_ts).isoformat() + "Z" if et_ts else None
        
        data = {
            "meta": {
                "session_id": sess_id,
                "session_name": session.description,
                "source_file": source_file,  # Track which CSV produced this session
                "start_time": st_iso,
                "end_time": et_iso,
                "duration_sec": round(dur, 2),
                "logger_version": "v3.6",
                "schema_version": "1.0"
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
        registry = RegistryManager()
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
            
            return out_path
        except Exception as e:
            print(f"[SessionExporter] Failed to write JSON: {e}")
            return ""

    def _export_telemetry(self, session: Session, main_path: str):
        """
        Saves 10Hz telemetry to <session>_telemetry.json
        Structure of Arrays (Columnar) for compactness.
        """
        if not session.samples: return

        t_path = main_path.replace(".json", "_telemetry.json")
        
        # Base Timestamp
        t0 = session.samples[0].timestamp
        
        # Build Columns
        # Rounding for file size optimization
        times = [round(s.timestamp - t0, 3) for s in session.samples]
        lats = [round(s.gps.lat, 6) for s in session.samples]
        lons = [round(s.gps.lon, 6) for s in session.samples]
        speeds = [round(s.gps.speed, 1) for s in session.samples]
        
        # Base keys
        payload = {
            "time": times,
            "lat": lats,
            "lon": lons,
            "speed": speeds
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
    
    def _generate_session_filename(self, session_timestamp: float, folder_name: str) -> str:
        """
        Generate date-based session filename: jan21Session1.json
        Uses session timestamp to derive date, then finds next available number for that day.
        """
        # Parse timestamp to get date components
        if session_timestamp:
            session_dt = datetime.datetime.fromtimestamp(session_timestamp)
        else:
            session_dt = datetime.datetime.now()
        
        # Format: jan21, feb05, etc.
        month_abbrev = session_dt.strftime("%b").lower()  # 'jan', 'feb', etc.
        day = session_dt.strftime("%d")                    # '01', '21', etc.
        date_prefix = f"{month_abbrev}{day}"               # 'jan21'
        
        # Find existing sessions with this date prefix
        existing = []
        
        if os.path.exists(self.output_dir):
            for file in os.listdir(self.output_dir):
                # Match pattern: jan21Session1.json (case insensitive)
                if file.lower().startswith(date_prefix.lower()) and file.endswith(".json") and not file.endswith("_telemetry.json"):
                    # Extract session number from jan21Session5.json
                    try:
                        # Remove date prefix and .json to get 'Session5'
                        session_part = file[len(date_prefix):].replace(".json", "")
                        # Extract number after 'Session'
                        if session_part.lower().startswith("session"):
                            num_part = session_part[7:]  # Skip 'Session' (7 chars)
                            session_num = int(num_part)
                            existing.append(session_num)
                    except (ValueError, IndexError):
                        continue
        
        # Next number is max + 1, or 1 if none exist
        next_num = max(existing) + 1 if existing else 1
        return f"{date_prefix}Session{next_num}.json"

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

    def _build_laps_list(self, session: Session, track_info: Dict = None) -> List[Dict]:
        laps_out = []
        best_time = self._find_best_lap_time(session)
        
        t0 = session.start_time
        
        for lap in session.laps:
            # Calculate relative start time for syncing with telemetry
            start_rel = 0.0
            if lap.samples:
                start_rel = round(lap.samples[0].timestamp - t0, 3)

            l_data = {
                "lap_index": lap.lap_number - 1, # 0-indexed schema
                "lap_number": lap.lap_number,    # Human readable
                "start_time": start_rel,         # Relative to session start (seconds)
                "lap_time": round(lap.duration, 3) if lap.duration else None,
                "valid": getattr(lap, 'valid', True),
                "reason_invalid": None, # Logic not yet present
                "sector_times": [],
                "delta_to_reference": round(lap.duration - best_time, 3) if (lap.duration and best_time) else 0.0,
                "is_session_best": (lap.duration == best_time and lap.duration > 0)
            }
            
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
            sec_id = sec["id"]
            # Gather all times for this sector
            times = []
            for lap in session.laps:
                val = lap.sector_times.get(sec_id)
                if val: times.append(val)
            
            if not times:
                continue
                
            stats.append({
                "sector_index": sec.get("id"), # Or index
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

    def _calc_gap_to_tbl(self, session, tbl_data) -> Optional[float]:
        best = self._find_best_lap_time(session)
        if best and tbl_data and tbl_data.get("total_best_time"):
            return round(best - tbl_data["total_best_time"], 3)
        return None
