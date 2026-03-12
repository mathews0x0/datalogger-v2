from dataclasses import dataclass
from typing import List
import math
from src.analysis.core.models import Session, Lap
from src.analysis.processing.geo import haversine_distance

@dataclass
class StartLine:
    lat: float
    lon: float
    radius_m: float = 10.0
    expected_heading: float = None  # Optional: expected heading in degrees (0-360)

class LapDetector:
    def __init__(self, start_line: StartLine):
        self.start_line = start_line
        self.min_lap_time = 10.0  # Ignore crossings if faster than this (debounce)
        self.heading_tolerance = 90.0  # Degrees tolerance for heading validation
        self._reference_heading = None  # Learned from first valid crossing

    def _calculate_heading(self, lat1, lon1, lat2, lon2):
        """Calculate heading from point 1 to point 2 in degrees (0-360)."""
        if lat1 == lat2 and lon1 == lon2:
            return 0
        
        lat1_r = math.radians(lat1)
        lat2_r = math.radians(lat2)
        dlon = math.radians(lon2 - lon1)
        
        x = math.sin(dlon) * math.cos(lat2_r)
        y = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlon)
        
        heading = math.degrees(math.atan2(x, y))
        return (heading + 360) % 360

    def _heading_is_valid(self, heading):
        """Check if heading matches expected direction."""
        if self._reference_heading is None:
            return True  # First crossing - accept any direction
        
        diff = abs(heading - self._reference_heading)
        if diff > 180:
            diff = 360 - diff
        
        return diff < self.heading_tolerance

    def detect(self, session: Session) -> List[Lap]:
        """
        Scan the session for start/finish line crossings.
        Includes heading validation to prevent wrong-way triggers.
        """
        laps = []
        crossing_indices = []
        
        in_zone = False
        
        # Dynamically calculate sample rate (Hz)
        sample_rate = 10.0
        if session.samples and len(session.samples) > 10:
            duration = session.samples[10].timestamp - session.samples[0].timestamp
            if duration > 0.05:
                sample_rate = 10.0 / duration
        hz = max(10, min(200, int(sample_rate)))
        lookback_limit = max(20, int(2.0 * hz)) # Look back up to 2 seconds

        for i, sample in enumerate(session.samples):
            dist_km = haversine_distance(
                sample.gps.lat, sample.gps.lon,
                self.start_line.lat, self.start_line.lon
            )
            dist_m = dist_km * 1000.0
            
            if dist_m < self.start_line.radius_m:
                if not in_zone:
                    in_zone = True
                    
                    # Calculate heading using look-back to handle "stair-step" GPS
                    heading = None
                    # Look back up to 2s to find 5m of movement
                    for lookback in range(1, min(i, lookback_limit) + 1):
                        prev = session.samples[i - lookback]
                        d_km = haversine_distance(
                            prev.gps.lat, prev.gps.lon,
                            sample.gps.lat, sample.gps.lon
                        )
                        if d_km * 1000.0 > 5.0:  # Found 5m of movement
                            heading = self._calculate_heading(
                                prev.gps.lat, prev.gps.lon,
                                sample.gps.lat, sample.gps.lon
                            )
                            break
                    
                    if heading is None and i > 0:
                        # Fallback: if we haven't moved 5m in 2s, just use the immediate previous point if it exists
                        prev = session.samples[i - 1]
                        if prev.gps.lat != sample.gps.lat or prev.gps.lon != sample.gps.lon:
                             heading = self._calculate_heading(
                                prev.gps.lat, prev.gps.lon,
                                sample.gps.lat, sample.gps.lon
                            )

                    # Validate heading
                    if heading is not None:
                        if not self._heading_is_valid(heading):
                            continue  # Skip wrong-way crossing
                        
                        # Learn reference heading from first valid crossing
                        if self._reference_heading is None:
                            self._reference_heading = heading
                            if self.start_line.expected_heading is not None:
                                self._reference_heading = self.start_line.expected_heading
                        
                        # Check debounce
                        if not crossing_indices or (sample.timestamp - session.samples[crossing_indices[-1]].timestamp > self.min_lap_time):
                            crossing_indices.append(i)
                    elif self._reference_heading is not None:
                        # If we can't determine heading but have a reference, we might be too slow.
                        # For safety, skip if we can't confirm direction.
                        continue
            else:
                in_zone = False
                
        # Convert crossings into Laps
        if len(crossing_indices) < 2:
            return []
            
        for i in range(len(crossing_indices) - 1):
            start_idx = crossing_indices[i]
            end_idx = crossing_indices[i+1]
            
            lap = Lap(session, start_idx, end_idx, number=i+1)
            laps.append(lap)
            
        return laps
