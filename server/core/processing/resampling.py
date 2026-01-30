from typing import List
from src.analysis.core.models import Session, Sample, GPSSample, IMUSample, EnvSample
from src.analysis.processing.geo import haversine_distance

class Resampler:
    """
    Resamples a Session to fixed distance intervals (e.g. every 10 meters).
    Enables comparisons between laps of different time durations.
    """
    def __init__(self, step_meters: float = 10.0):
        self.step = step_meters

    def _lerp(self, v1: float, v2: float, ratio: float) -> float:
        return v1 + (v2 - v1) * ratio

    def resample_session(self, session: Session) -> List[Sample]:
        if not session.samples or len(session.samples) < 2:
            return []

        new_samples = []
        
        # Start at distance 0 (first sample)
        current_cumulative_dist = 0.0
        target_dist = 0.0
        
        # Add the first sample exactly
        new_samples.append(session.samples[0])
        target_dist += self.step

        for i in range(len(session.samples) - 1):
            s1 = session.samples[i]
            s2 = session.samples[i+1]
            
            # Calculate segment length
            seg_dist_km = haversine_distance(s1.gps.lat, s1.gps.lon, s2.gps.lat, s2.gps.lon)
            seg_dist_m = seg_dist_km * 1000.0
            
            # If we are stuck at the same point (stopped), skip
            if seg_dist_m <= 0.001:
                continue

            # Check if we crossed one or more target distances in this segment
            while target_dist <= (current_cumulative_dist + seg_dist_m):
                # How far into the segment is the target?
                remaining = target_dist - current_cumulative_dist
                ratio = remaining / seg_dist_m
                
                # Interpolate
                # Time
                ts = self._lerp(s1.timestamp, s2.timestamp, ratio)
                
                # GPS (Lat/Lon linear interpolation is approximation, valid for small steps)
                lat = self._lerp(s1.gps.lat, s2.gps.lat, ratio)
                lon = self._lerp(s1.gps.lon, s2.gps.lon, ratio)
                speed = self._lerp(s1.gps.speed, s2.gps.speed, ratio)
                
                # IMU
                ax = self._lerp(s1.imu.accel_x, s2.imu.accel_x, ratio)
                ay = self._lerp(s1.imu.accel_y, s2.imu.accel_y, ratio)
                az = self._lerp(s1.imu.accel_z, s2.imu.accel_z, ratio)
                
                # Create Sample
                sample = Sample(
                    timestamp=ts,
                    gps=GPSSample(lat, lon, speed, s1.gps.sats),
                    imu=IMUSample(ax, ay, az),
                    env=s1.env # Negligible change
                )
                new_samples.append(sample)
                
                target_dist += self.step
                
            current_cumulative_dist += seg_dist_m
            
        return new_samples
