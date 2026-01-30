import os
import uuid
import datetime
from typing import Optional

from src.analysis.ingestion.csv_loader import CSVLoader
from src.analysis.core.track_manager import TrackManager
from src.analysis.core.track_generator import TrackGenerator
from src.analysis.core.tbl_manager import TBLManager
from src.analysis.core.session_exporter import SessionExporter
from src.analysis.processing.laps import LapDetector, StartLine
from src.analysis.processing.stats import StatsEngine
from src.analysis.core.registry_manager import RegistryManager
from src.analysis.core.imu_calibrator import IMUCalibrator
from src.analysis.processing.metrics_engine import SensorMetricsEngine
import src.config as config
from src.core.log_manager import get_logger

class SessionProcessor:
    """
    Orchestrator for the Post-Session Workflow.
    INPUT: Session/CSV
    OUTPUT: Updated Artifacts (Tracks, TBL, Session JSON)
    """

    def __init__(self, output_dir=None):
        self.log = get_logger("analysis")
        self.loader = CSVLoader()
        self.tm = TrackManager()
        self.gen = TrackGenerator()
        self.tbl_mgr = TBLManager()
        self.exporter = SessionExporter(output_dir=output_dir)

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
                # Auto-ID
                track_info = self.tm.identify_track(session)
            
            # 3. Handle Unknown Track (Auto-Gen)
            if not track_info:
                self.log.info("Track not identified. Initiating Auto-Generation...")
                # Generate sequential numeric track ID via registry
                registry = RegistryManager()
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
            start_line = StartLine(sl["lat"], sl["lon"], sl.get("radius_m", 20.0))
            
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
                    "pitch": imu_results["pitch_angle"]
                }
                
                # Inject Metrics
                # We can re-use SensorMetricsEngine or build new simple ones
                # For now just log success
                self.log.info(f"IMU Processing Complete. Confidence: {imu_results.get('confidence')}")
                
                # Update calibration status for JSON export compatibility
                session.calibration = {
                    "calibrated": True, 
                    "confidence": "HIGH",
                    "method": "AdvancedIMUProcessor"
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
