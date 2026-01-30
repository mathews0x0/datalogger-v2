from typing import List, Dict, Optional
from src.analysis.core.models import Lap, Sample
from src.analysis.processing.resampling import Resampler

class Comparator:
    """
    Compares two laps by normalizing them to a common distance axis.
    Calculates Delta Time and Delta Speed at each interval.
    """
    def __init__(self, step_meters: float = 10.0):
        self.resampler = Resampler(step_meters)

    def compare(self, ref_lap: Lap, target_lap: Lap) -> Dict:
        """
        Compare target_lap against ref_lap (Best Lap).
        Returns a dictionary containing aligned arrays:
        {
            "distance": [0, 10, 20...],
            "ref_speed": [...],
            "target_speed": [...],
            "delta_speed": [target - ref, ...],
            "delta_time": [target_cumulative - ref_cumulative, ...]
        }
        """
        # 1. Resample both laps to fixed distance steps
        # Note: We must restrict comparison to the SHORTER total distance
        # to avoid index errors if one lap is vastly longer (e.g. runoff).
        
        ref_samples = self.resampler.resample_session(ref_lap)
        target_samples = self.resampler.resample_session(target_lap)
        
        # 2. Determine truncation length
        length = min(len(ref_samples), len(target_samples))
        
        result = {
            "distance": [],
            "lat": [],
            "lon": [],
            "ref_time": [],
            "target_time": [],
            "ref_speed": [],
            "target_speed": [],
            "delta_speed": [],
            "delta_time": []
        }
        
        # 3. Calculate Deltas
        for i in range(length):
            r = ref_samples[i]
            t = target_samples[i]
            
            dist = i * self.resampler.step
            
            # Speed Delta: Positive means Target is Fast (Good? Usually Speed Delta is shown as is)
            # If Ref is 50, Target is 60, Delta is +10.
            d_speed = t.gps.speed - r.gps.speed
            
            # Time Delta: Positive means Target is Behind (Bad)
            # Ref arrives at 10s. Target arrives at 11s. Delta = +1s.
            # Convert timestamp to relative time from lap start
            r_rel = r.timestamp - ref_samples[0].timestamp
            t_rel = t.timestamp - target_samples[0].timestamp
            d_time = t_rel - r_rel
            
            result["distance"].append(dist)
            
            # Geo Coords (from Reference path - they are spatially aligned)
            result["lat"].append(r.gps.lat)
            result["lon"].append(r.gps.lon)
            
            # Times
            result["ref_time"].append(r_rel)
            result["target_time"].append(t_rel)
            
            result["ref_speed"].append(r.gps.speed)
            result["target_speed"].append(t.gps.speed)
            result["delta_speed"].append(d_speed)
            result["delta_time"].append(d_time)
            
        return result
