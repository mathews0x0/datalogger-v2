import os
import csv
import json
from typing import TextIO, Union
from src.analysis.core.models import Session, Sample, GPSSample, IMUSample, EnvSample

class CSVLoader:
    """
    Decoupled CSV Ingestion for Motorcycle Telemetry.
    Reads the fixed telemetry CSV format and produces a Session object.

    Expected format:
      tick_ms,row_type,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,lat,lon,alt,speed,sats,vbat,...

    row_type:
      - I: 100Hz IMU sample without a raw GPS fix.
      - G: 100Hz IMU sample carrying a raw GPS fix.
      - M: marker/metadata row.
    """
    
    def load(self, file_source: Union[str, TextIO], source_name: str = "Unknown") -> Session:
        """
        Load a CSV file into a Session.
        file_source: File path (str) or file-like object (TextIO).
        """
        
        # Handle file paths vs file objects
        should_close = False
        if isinstance(file_source, str):
            f = open(file_source, 'r', newline='')
            should_close = True
            source_name = os.path.basename(file_source)
        else:
            f = file_source # Already open
            
        try:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []

            if 'row_type' not in fieldnames:
                raise ValueError("Unsupported CSV format: expected fixed telemetry CSV with row_type column")
            return self._load_fixed_100hz(reader, source_name)
                
        finally:
            if should_close:
                f.close()
    
    def _load_fixed_100hz(self, reader, source_name: str) -> Session:
        """
        Load fixed-format telemetry CSV emitted by the 100Hz logger.
        
        Strategy:
          1. Collect all 100Hz IMU samples from I/G rows.
          2. Preserve raw GPS values on G rows and mark them gps_is_fix=True.
          3. Interpolate GPS values only for non-fix I rows.
        """
        # (tick_ms, acc_x, acc_y, acc_z, gyr_x, gyr_y, gyr_z, is_gps_fix, raw_gps)
        imu_rows = []
        gps_rows = []  # (tick_ms, lat, lon, alt, speed, sats, vbat)
        markers = {}
        
        first_tick_ms = None
        gps_epoch_anchor = None
        gps_epoch_tick = None
        
        for row in reader:
            try:
                tick_ms = int(row.get("tick_ms", 0))
                row_type = row.get("row_type", "").strip()
                
                if first_tick_ms is None:
                    first_tick_ms = tick_ms
                
                # IMU fields (present in both I and G rows)
                acc_x = float(row.get("acc_x") or 0.0)
                acc_y = float(row.get("acc_y") or 0.0)
                acc_z = float(row.get("acc_z") or 0.0)
                gyr_x = float(row.get("gyro_x") or 0.0)
                gyr_y = float(row.get("gyro_y") or 0.0)
                gyr_z = float(row.get("gyro_z") or 0.0)
                
                if row_type == 'I':
                    imu_rows.append((tick_ms, acc_x, acc_y, acc_z, gyr_x, gyr_y, gyr_z, False, None))
                elif row_type == 'G':
                    lat = float(row.get("lat") or 0.0)
                    lon = float(row.get("lon") or 0.0)
                    alt = float(row.get("alt") or 0.0)
                    speed = float(row.get("speed") or 0.0)
                    sats = int(row.get("sats") or 0)
                    vbat = float(row.get("vbat") or 0.0)
                    
                    gps_epoch = float(row.get("gps_epoch") or 0.0)
                    if gps_epoch > 0 and gps_epoch_anchor is None:
                        gps_epoch_anchor = gps_epoch
                        gps_epoch_tick = tick_ms
                    
                    gps_rows.append((tick_ms, lat, lon, alt, speed, sats, vbat))
                    # Also add to IMU list (G rows contain IMU data too)
                    imu_rows.append((tick_ms, acc_x, acc_y, acc_z, gyr_x, gyr_y, gyr_z, True, (lat, lon, alt, speed, sats, vbat)))
                elif row_type == 'M':
                    marker_name = (row.get("lon") or "").strip()
                    marker_value = row.get("speed") or ""
                    if marker_name:
                        markers[marker_name] = marker_value

            except (ValueError, TypeError):
                continue
        
        if not imu_rows:
            return Session(description=source_name)
        
        # Build unified session by interpolating GPS onto IMU timeline
        session = Session(description=source_name)
        
        # Convert tick_ms to seconds (relative to first tick), then to Unix epoch estimate
        # We use relative time since tick_ms is a monotonic clock
        base_tick = first_tick_ms if first_tick_ms else 0
        
        gps_idx = 0  # Current lower GPS bound for interpolation
        
        for imu in imu_rows:
            tick_ms = imu[0]
            
            # Timestamp: convert tick_ms to absolute Unix epoch if we found an anchor
            if gps_epoch_anchor is not None:
                ts = gps_epoch_anchor + (tick_ms - gps_epoch_tick) / 1000.0
            else:
                ts = (tick_ms - base_tick) / 1000.0
            
            # IMU sample
            imu_sample = IMUSample(
                accel_x=imu[1], accel_y=imu[2], accel_z=imu[3],
                gyro_x=imu[4], gyro_y=imu[5], gyro_z=imu[6]
            )
            
            # Interpolate GPS for IMU rows. Real GPS rows keep their raw fix value.
            lat, lon, alt, speed, sats, vbat = 0.0, 0.0, 0.0, 0.0, 0, 0.0
            
            if imu[7] and imu[8] is not None:
                lat, lon, alt, speed, sats, vbat = imu[8]
            elif gps_rows:
                # Advance GPS index to bracket the current tick
                while gps_idx < len(gps_rows) - 1 and gps_rows[gps_idx + 1][0] <= tick_ms:
                    gps_idx += 1
                
                if gps_idx >= len(gps_rows) - 1:
                    # Beyond last GPS point — use last known
                    g = gps_rows[-1]
                    lat, lon, alt, speed, sats, vbat = g[1], g[2], g[3], g[4], g[5], g[6]
                elif tick_ms <= gps_rows[0][0]:
                    # Before first GPS point — use first known
                    g = gps_rows[0]
                    lat, lon, alt, speed, sats, vbat = g[1], g[2], g[3], g[4], g[5], g[6]
                else:
                    # Interpolate between gps_idx and gps_idx+1
                    g0 = gps_rows[gps_idx]
                    g1 = gps_rows[gps_idx + 1]
                    dt = g1[0] - g0[0]
                    if dt > 0:
                        ratio = (tick_ms - g0[0]) / dt
                    else:
                        ratio = 0.0
                    
                    lat = g0[1] + (g1[1] - g0[1]) * ratio
                    lon = g0[2] + (g1[2] - g0[2]) * ratio
                    alt = g0[3] + (g1[3] - g0[3]) * ratio
                    speed = g0[4] + (g1[4] - g0[4]) * ratio
                    sats = g0[5]  # No interpolation for integer count
                    vbat = g0[6]
            
            gps_sample = GPSSample(lat=lat, lon=lon, speed=speed, sats=sats)
            env_sample = EnvSample(temp=0.0, pressure=vbat)
            
            session.add_sample(Sample(ts, gps_sample, imu_sample, env_sample, gps_is_fix=bool(imu[7])))

        session.device_metadata = {
            "gps_fix_count": len(gps_rows),
        }
        if gps_rows:
            session.device_metadata["gps_fix_span_s"] = max(0.0, (gps_rows[-1][0] - gps_rows[0][0]) / 1000.0)
            session.device_metadata["gps_fix_rate_hz"] = (
                len(gps_rows) / session.device_metadata["gps_fix_span_s"]
                if session.device_metadata["gps_fix_span_s"] > 0
                else float(len(gps_rows))
            )
        if markers.get("IMU_PROFILE") and markers.get("IMU_PROFILE") != "none":
            try:
                session.device_metadata["imu_profile"] = json.loads(markers["IMU_PROFILE"])
            except Exception:
                session.device_metadata["imu_profile_error"] = markers.get("IMU_PROFILE")
        if markers.get("IMU_VALIDATION"):
            try:
                session.device_metadata["imu_validation"] = json.loads(markers["IMU_VALIDATION"])
            except Exception:
                session.device_metadata["imu_validation_error"] = markers.get("IMU_VALIDATION")
        if session.device_metadata.get("imu_profile"):
            session.mount_profile = session.device_metadata["imu_profile"]
        if session.device_metadata.get("imu_validation"):
            session.runtime_validation = session.device_metadata["imu_validation"]
        
        return session
