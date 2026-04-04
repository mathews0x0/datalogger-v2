import os
import json
import math

from src.analysis.ingestion.csv_loader import CSVLoader
from src.analysis.core.track_manager import TrackManager
from src.analysis.core.track_generator import TrackGenerator
from src.analysis.core.tbl_manager import TBLManager
from src.analysis.core.session_exporter import SessionExporter
from src.analysis.processing.laps import LapDetector, StartLine
from src.analysis.processing.stats import StatsEngine
from src.analysis.core.registry_manager import RegistryManager
from src.analysis.processing.metrics_engine import SensorMetricsEngine
import src.config as config
from src.core.log_manager import get_logger
from src.analysis.processing.geo import haversine_distance

class SessionProcessor:
    """
    Orchestrator for the Post-Session Workflow.
    INPUT: Session/CSV
    OUTPUT: Updated Artifacts (Tracks, TBL, Session JSON)
    """

    def __init__(self, output_dir=None, tracks_dir=None):
        self.log = get_logger("analysis")
        self.loader = CSVLoader()
        self.tm = TrackManager(tracks_dir=tracks_dir)
        self.global_tracks_dir = str(config.get_global_tracks_dir())
        self.global_tm = TrackManager(tracks_dir=self.global_tracks_dir)
        self.gen = TrackGenerator(tracks_dir=tracks_dir)
        self.tbl_mgr = TBLManager(tracks_dir=tracks_dir)
        self.exporter = SessionExporter(output_dir=output_dir, tracks_dir=tracks_dir)
        self.user_tracks_dir = tracks_dir if tracks_dir else config.TRACKS_DIR

    def _load_layout_metadata(self, track_info):
        folder_name = track_info.get("folder_name")
        if not folder_name:
            return None
        meta_path = os.path.join(self.global_tracks_dir, folder_name, "layout_metadata.json")
        if not os.path.exists(meta_path):
            return None
        try:
            with open(meta_path, "r") as handle:
                return json.load(handle)
        except Exception:
            return None

    @staticmethod
    def _start_line_target(sl):
        if not sl:
            return None, None, 20.0
        if "lat" in sl and "lon" in sl:
            return sl["lat"], sl["lon"], sl.get("radius_m", 20.0)
        center = sl.get("center") or {}
        if "lat" in center and "lon" in center:
            return center["lat"], center["lon"], sl.get("radius_m", 20.0)
        return None, None, sl.get("radius_m", 20.0) if isinstance(sl, dict) else 20.0

    def _global_track_matches_package(self, session, track_info):
        layout_meta = self._load_layout_metadata(track_info)
        if not layout_meta:
            return True

        bounds = layout_meta.get("telemetry_bounds") or {}
        geo_reference = layout_meta.get("geo_reference") or {}
        auto_align = layout_meta.get("auto_align") or {}
        if not bounds or not geo_reference or not auto_align:
            return True

        min_x = float(bounds.get("minX", 0.0))
        max_x = float(bounds.get("maxX", 0.0))
        min_y = float(bounds.get("minY", 0.0))
        max_y = float(bounds.get("maxY", 0.0))
        width = max(max_x - min_x, 1.0)
        height = max(max_y - min_y, 1.0)
        pad_x = width * 0.15
        pad_y = height * 0.15

        theta = math.radians(float(auto_align["rotationDeg"]))
        scale = float(auto_align["scale"])
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)

        projected = []
        step = max(1, len(session.samples) // 250)
        for sample in session.samples[::step]:
            local_x = (float(sample.gps.lon) - float(geo_reference["lon0"])) * float(geo_reference["metersPerDegLon"])
            local_y = (float(geo_reference["lat0"]) - float(sample.gps.lat)) * float(geo_reference["metersPerDegLat"])
            x_rot = local_x * cos_t - local_y * sin_t
            y_rot = local_x * sin_t + local_y * cos_t
            projected.append({
                "x": x_rot * scale + float(auto_align["translateX"]),
                "y": y_rot * scale + float(auto_align["translateY"]),
            })

        if not projected:
            return False

        inside = 0
        xs = []
        ys = []
        for point in projected:
            xs.append(point["x"])
            ys.append(point["y"])
            if (min_x - pad_x) <= point["x"] <= (max_x + pad_x) and (min_y - pad_y) <= point["y"] <= (max_y + pad_y):
                inside += 1

        inside_ratio = inside / len(projected)
        centroid_x = sum(xs) / len(xs)
        centroid_y = sum(ys) / len(ys)
        target_x = min_x + width / 2.0
        target_y = min_y + height / 2.0
        centroid_distance = math.hypot(centroid_x - target_x, centroid_y - target_y)

        return inside_ratio >= 0.45 and centroid_distance <= max(width, height) * 0.45

    @staticmethod
    def _is_global_track(track):
        if not isinstance(track, dict):
            return False
        track_id = track.get("track_id", track.get("id"))
        if isinstance(track_id, str) and track_id.isdigit():
            track_id = int(track_id)
        return isinstance(track_id, int) and track_id >= config.GLOBAL_TRACK_ID_MIN

    def _identify_global_track(self, session):
        best_candidate = None
        best_distance = None
        for track in self.global_tm.tracks:
            if not self._is_global_track(track):
                continue
            sl = track.get("start_line")
            target_lat, target_lon, radius_m = self._start_line_target(sl)
            if target_lat is None or target_lon is None:
                continue
            radius_km = max(float(radius_m), 60.0) / 1000.0
            for sample in session.samples:
                dist = haversine_distance(sample.gps.lat, sample.gps.lon, target_lat, target_lon)
                if dist < radius_km and (best_distance is None or dist < best_distance):
                    best_candidate = track
                    best_distance = dist
                    break
        return best_candidate

    def _prepare_user_track_storage(self, track_info):
        track_id = track_info.get("track_id")
        if track_id is None:
            return
        folder_name = track_info.get("folder_name") or f"track_{track_id}"
        from src.analysis.core.registry_manager import RegistryManager
        registry = RegistryManager(registry_path=self.user_tracks_dir)
        registry.register_track(track_id, track_info.get("track_name", f"Track {track_id}"), folder_name=folder_name)
        os.makedirs(os.path.join(self.user_tracks_dir, folder_name), exist_ok=True)

    def process_session(self, file_path: str, force_track_id: str = None) -> bool:
        """
        Full pipeline execution.
        """
        filename = os.path.basename(file_path)
        self.log.info(f"Starting processing for: {filename}", data={"file": file_path})
        
        try:
            # 1. Load Session
            try:
                session = self.loader.load(file_path)
                if not session.samples:
                    self.log.warning("Session empty. Skipping.", data={"file": filename})
                    return False
            except Exception as e:
                self.log.error(f"Load failed: {e}", exc_info=True)
                return False

            # 2. Identify or Generate Track
            track_info = None
            
            if force_track_id:
                # Manual override or Known ID
                track_info = next((t for t in self.tm.tracks if t["id"] == force_track_id), None)
                if not track_info:
                    self.log.warning(f"Forced track '{force_track_id}' not found.")
            else:
                global_candidate = self._identify_global_track(session)
                if global_candidate and self._is_global_track(global_candidate):
                    if self._global_track_matches_package(session, global_candidate):
                        track_info = global_candidate
                        track_info["id"] = track_info.get("track_id")
                        track_info["name"] = track_info.get("track_name")
                        track_info["track_scope"] = "global"
                        track_info["track_source"] = "global_package"
                        track_info["has_canonical_layout"] = True
                        track_info["package_version"] = track_info.get("package_version")
                        track_info["folder_name"] = f"global_track_{track_info['track_id']}"
                        self._prepare_user_track_storage(track_info)
                if not track_info:
                    track_info = self.tm.identify_track(session)
            
            # 3. Handle Unknown Track (Auto-Gen)
            if not track_info:
                self.log.info("Track not identified. Initiating Auto-Generation...")
                # Generate sequential numeric track ID via registry
                registry_path = os.path.join(self.tm.tracks_dir, "registry.json")
                registry = RegistryManager(registry_path=registry_path)
                new_id = registry.get_next_track_id()  # Returns numeric ID
                
                new_name = f"track_{new_id}"  # Human name, will be sanitized to folder
                
                track_info = self.gen.generate_from_session(session, new_id, new_name)
                if not track_info:
                    self.log.error("Auto-Generation failed. Aborting.")
                    return False
                    
                # Reload TM to include new track? Or just use dict.
                # Ideally add to TM's cache if persistent.
                self.tm.tracks.append(track_info) # update local cache
                
            else:
                self.log.info(f"Identified Track: {track_info['track_name']}", data={"track_id": track_info['id']})

            # 4. Lap Detection & Stats
            # Use DB Start Line
            sl = track_info["start_line"]
            sl_lat, sl_lon, sl_radius = self._start_line_target(sl)
            if sl_lat is None or sl_lon is None:
                self.log.error("Track start line missing usable coordinates", data={"track_id": track_info.get("track_id")})
                return False
            start_line = StartLine(sl_lat, sl_lon, sl_radius)
            
            detector = LapDetector(start_line)
            laps = detector.detect(session)
            session.laps = laps # Attach to session for exporters
            
            self.log.info(f"Laps Detected: {len(laps)}")
            
            # 4.5. IMU Processing (Advanced Pipeline)
            from src.analysis.processing.advanced_imu import AdvancedIMUProcessor
            
            # Extract Raw Signals
            # Note: Values might be missing/None, mapped to 0.0 in CSVLoader but ensure lists are standard
            timestamps = [s.timestamp for s in session.samples]
            ax_raw = [s.imu.accel_x for s in session.samples]
            ay_raw = [s.imu.accel_y for s in session.samples]
            az_raw = [s.imu.accel_z for s in session.samples]
            
            gx_raw = [(s.imu.gyro_x if s.imu.gyro_x else 0.0) for s in session.samples]
            gy_raw = [(s.imu.gyro_y if s.imu.gyro_y else 0.0) for s in session.samples]
            gz_raw = [(s.imu.gyro_z if s.imu.gyro_z else 0.0) for s in session.samples]
            
            lats = [s.gps.lat for s in session.samples]
            lons = [s.gps.lon for s in session.samples]
            speeds = [s.gps.speed for s in session.samples]

            self.log.info("Running Advanced IMU Processing Pipeline...")
            
            try:
                imu_proc = AdvancedIMUProcessor()
                imu_results = imu_proc.process(timestamps, ax_raw, ay_raw, az_raw, gx_raw, gy_raw, gz_raw, 
                                             speeds=speeds, lats=lats, lons=lons)
                
                # Map results to session signals
                # Results: lean_angle, pitch_angle, ax_cg, ay_cg, etc.
                session.derived_signals = {
                    "aligned_accel_x": imu_results["ax_cg"], # Longitudinal
                    "aligned_accel_y": imu_results["ay_cg"], # Lateral
                    "aligned_accel_z": imu_results["az_cg"],
                    "lean_angle": imu_results["lean_angle"],
                    "pitch": imu_results["pitch_angle"],
                    "yaw_rate": imu_results.get("yaw_angle", []),
                    "lateral_g": imu_results.get("lateral_g", []),
                    "acceleration_g": imu_results.get("acceleration_g", []),
                    "braking_g": imu_results.get("braking_g", []),
                }
                
                # Inject Metrics
                # We can re-use SensorMetricsEngine or build new simple ones
                # For now just log success
                self.log.info(f"IMU Processing Complete. Confidence: {imu_results.get('confidence')}")
                
                # Update calibration status for JSON export compatibility
                session.calibration = {
                    "calibrated": True, 
                    "confidence": imu_results.get("mount_confidence", "LOW"),
                    "method": imu_results.get("mount_method", "AdvancedIMUProcessor"),
                    "selected_algorithm": imu_results.get("diagnostics", {}).get("selected_algorithm"),
                    "rotation_matrix": imu_results.get("rotation_matrix"),
                    "gyro_bias": imu_results.get("gyro_bias"),
                    "gravity_vector": imu_results.get("gravity_vector"),
                    "evidence_summary": imu_results.get("evidence_summary"),
                    "validation": imu_results.get("validation"),
                    "diagnostics": imu_results.get("diagnostics"),
                }
                
                # 4.6 Sensor Metrics (Recalculate on clean signals)
                # Ensure metrics engine handles new clean signals
                met_engine = SensorMetricsEngine()
                metrics = met_engine.compute(session)
                session.sensor_metrics = metrics
                
            except Exception as e:
                self.log.error(f"Advanced IMU Processing Failed: {e}", exc_info=True)
                session.derived_signals = {}
                session.calibration = {"calibrated": False, "reason": str(e)}

            # 5. Sector Calculation
            StatsEngine.calculate_sectors(laps, track_info)
            
            # 6. Update Persistent Records (Track JSON & TBL)
            self.log.debug("Track JSON is frozen. Skipping record update.")

            # B. TBL Update
            if self.tbl_mgr.update_from_session(session, track_info):
                self.log.info("Theoretical Best Lap Updated.")

            # 7. Export Session JSON (Actionable Artifact)
            # Load latest TBL for reference
            tbl_data = self.tbl_mgr.load_tbl(track_info["track_id"])
            
            # Get Reference BRL
            brl_ref = track_info.get("records", {}).get("best_real_lap", {}).get("time")
            
            json_path = self.exporter.export(session, track_info, tbl_data, best_real_lap_ref=brl_ref, source_file=filename)
            if json_path:
                self.log.info(f"Session Export Complete: {json_path}")
                
            return True

        except Exception as e:
            self.log.error(f"Critical Processing Failure: {e}", exc_info=True, data={"file": filename})
            return False
