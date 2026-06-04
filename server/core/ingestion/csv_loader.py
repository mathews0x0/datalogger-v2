import os
import csv
import json
import math
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
            f = open(file_source, 'r', encoding='utf-8', errors='replace', newline='')
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

        # The logger can emit I and G rows in separate ordered substreams while the
        # combined CSV file order is not globally sorted by tick. Build all downstream
        # timelines from true chronological order so playback connects adjacent points
        # in time, regardless of whether they are raw GPS fixes or promoted samples.
        imu_rows.sort(key=lambda row: row[0])
        gps_rows.sort(key=lambda row: row[0])
        
        # Build unified session using Hermite GPS promotion at the maximum supported factor.
        session = Session(description=source_name)
        
        # Convert tick_ms to seconds (relative to first tick), then to Unix epoch estimate
        # We use relative time since tick_ms is a monotonic clock
        base_tick = imu_rows[0][0]
        
        max_factor, promoted_ticks = self._select_max_hermite_promotions(imu_rows, gps_rows)
        promoted_by_tick = self._hermite_interpolate_gps(gps_rows, promoted_ticks)
        
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
            
            lat, lon, alt, speed, sats, vbat = 0.0, 0.0, 0.0, 0.0, 0, 0.0
            gps_is_valid = False
            if imu[7] and imu[8] is not None:
                lat, lon, alt, speed, sats, vbat = imu[8]
                gps_is_valid = True
            else:
                promoted = promoted_by_tick.get(tick_ms)
                if promoted is not None:
                    lat, lon, alt, speed, sats, vbat = promoted
                    gps_is_valid = True
            
            gps_sample = GPSSample(lat=lat, lon=lon, speed=speed, sats=sats)
            env_sample = EnvSample(temp=0.0, pressure=vbat)
            
            session.add_sample(
                Sample(
                    ts,
                    gps_sample,
                    imu_sample,
                    env_sample,
                    gps_is_fix=bool(imu[7]),
                    gps_is_valid=gps_is_valid,
                )
            )

        session.device_metadata = {
            "gps_fix_count": len(gps_rows),
            "gps_hermite_max_factor": max_factor,
            "gps_hermite_promoted_count": len(promoted_ticks),
            "timestamp_source": "gps_epoch" if gps_epoch_anchor is not None else "relative_fallback",
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

    @staticmethod
    def _clamp(value, lo, hi):
        return max(lo, min(hi, value))

    def _select_max_hermite_promotions(self, imu_rows, gps_rows):
        if len(gps_rows) < 2:
            return 1, []

        imu_ticks = [row[0] for row in imu_rows if not row[7]]
        available_promotions = []
        imu_index = 0
        imu_count = len(imu_ticks)
        for index in range(len(gps_rows) - 1):
            start = gps_rows[index][0]
            end = gps_rows[index + 1][0]
            while imu_index < imu_count and imu_ticks[imu_index] <= start:
                imu_index += 1
            interval_ticks = []
            scan_index = imu_index
            while scan_index < imu_count and imu_ticks[scan_index] < end:
                interval_ticks.append(imu_ticks[scan_index])
                scan_index += 1
            available_promotions.append(interval_ticks)
            imu_index = scan_index

        original_gps_points = len(gps_rows)
        total_available_promotions = sum(len(ticks) for ticks in available_promotions)
        max_factor = max(1, (original_gps_points + total_available_promotions) // original_gps_points)
        extra_per_interval = max(0, max_factor - 1)
        promoted_ticks = []

        for index in range(len(gps_rows) - 1):
            start = gps_rows[index][0]
            end = gps_rows[index + 1][0]
            candidates = available_promotions[index]
            if not candidates or extra_per_interval == 0:
                continue
            picks = []
            for sample_index in range(1, extra_per_interval + 1):
                target_tick_ms = start + (((end - start) * sample_index) / max_factor)
                best_tick_ms = None
                best_distance = float("inf")
                for candidate_tick_ms in candidates:
                    if candidate_tick_ms in picks:
                        continue
                    distance = abs(candidate_tick_ms - target_tick_ms)
                    if distance < best_distance:
                        best_distance = distance
                        best_tick_ms = candidate_tick_ms
                if best_tick_ms is not None:
                    picks.append(best_tick_ms)
            picks.sort()
            promoted_ticks.extend(picks)

        return max_factor, promoted_ticks

    def _hermite_interpolate_gps(self, gps_rows, target_ticks):
        if len(gps_rows) < 2 or not target_ticks:
            return {}

        points = []
        origin_lat = gps_rows[0][1]
        origin_lon = gps_rows[0][2]
        lat_scale = 111320.0
        lon_scale = 111320.0 * math.cos(math.radians(origin_lat))
        for tick_ms, lat, lon, alt, speed, sats, vbat in gps_rows:
            points.append({
                "tick_ms": tick_ms,
                "x": (lon - origin_lon) * lon_scale,
                "y": (origin_lat - lat) * lat_scale,
                "alt": alt,
                "speed": speed,
                "sats": sats,
                "vbat": vbat,
            })

        tangents = []
        for index, point in enumerate(points):
            if index == 0:
                nxt = points[1]
                dt = max(1, nxt["tick_ms"] - point["tick_ms"])
                tangents.append({
                    "dx": (nxt["x"] - point["x"]) / dt,
                    "dy": (nxt["y"] - point["y"]) / dt,
                })
            elif index == len(points) - 1:
                prev = points[index - 1]
                dt = max(1, point["tick_ms"] - prev["tick_ms"])
                tangents.append({
                    "dx": (point["x"] - prev["x"]) / dt,
                    "dy": (point["y"] - prev["y"]) / dt,
                })
            else:
                prev = points[index - 1]
                nxt = points[index + 1]
                dt = max(1, nxt["tick_ms"] - prev["tick_ms"])
                tangents.append({
                    "dx": (nxt["x"] - prev["x"]) / dt,
                    "dy": (nxt["y"] - prev["y"]) / dt,
                })

        sorted_ticks = sorted(set(target_ticks))
        promoted = {}
        segment_index = 0
        last_segment = len(points) - 2
        for tick_ms in sorted_ticks:
            while segment_index < last_segment and tick_ms > points[segment_index + 1]["tick_ms"]:
                segment_index += 1
            a = points[segment_index]
            b = points[min(segment_index + 1, len(points) - 1)]
            tangent_a = tangents[segment_index]
            tangent_b = tangents[min(segment_index + 1, len(tangents) - 1)]
            dt = max(1, b["tick_ms"] - a["tick_ms"])
            u = self._clamp((tick_ms - a["tick_ms"]) / dt, 0.0, 1.0)
            h00 = (2 * u * u * u) - (3 * u * u) + 1
            h10 = (u * u * u) - (2 * u * u) + u
            h01 = (-2 * u * u * u) + (3 * u * u)
            h11 = (u * u * u) - (u * u)
            x = (h00 * a["x"]) + (h10 * dt * tangent_a["dx"]) + (h01 * b["x"]) + (h11 * dt * tangent_b["dx"])
            y = (h00 * a["y"]) + (h10 * dt * tangent_a["dy"]) + (h01 * b["y"]) + (h11 * dt * tangent_b["dy"])
            lat = origin_lat - (y / lat_scale)
            lon = origin_lon + (x / lon_scale)
            alt = gps_rows[segment_index][3] + ((gps_rows[min(segment_index + 1, len(gps_rows) - 1)][3] - gps_rows[segment_index][3]) * u)
            speed = gps_rows[segment_index][4] + ((gps_rows[min(segment_index + 1, len(gps_rows) - 1)][4] - gps_rows[segment_index][4]) * u)
            sats = int(round(gps_rows[segment_index][5] + ((gps_rows[min(segment_index + 1, len(gps_rows) - 1)][5] - gps_rows[segment_index][5]) * u)))
            vbat = gps_rows[segment_index][6] + ((gps_rows[min(segment_index + 1, len(gps_rows) - 1)][6] - gps_rows[segment_index][6]) * u)
            promoted[tick_ms] = (
                lat,
                lon,
                alt,
                speed,
                sats,
                vbat,
            )

        return promoted
