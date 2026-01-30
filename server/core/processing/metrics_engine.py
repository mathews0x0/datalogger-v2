import math
from typing import List, Dict, Optional, Tuple
from src.analysis.core.models import Session, Lap

class SensorMetricsEngine:
    """
    Phase 7.3.2: Load & Stability Metrics.
    Computes derived relative metrics from gravity-aligned IMU data.
    """
    
    def compute(self, session: Session) -> Dict:
        """
        Compute relative metrics for the session.
        Returns a dict structure for 'sensor_metrics'.
        """
        # Validate Input
        if not hasattr(session, 'derived_signals') or not session.derived_signals:
            return {"confidence": "NONE", "message": "No aligned signals present"}
            
        confidence = "LOW"
        if hasattr(session, 'calibration') and session.calibration:
            confidence = session.calibration.get("confidence", "LOW")
            
        # Extract Signal Arrays
        # These correspond 1:1 with session.samples
        sigs = session.derived_signals
        ax_global = sigs.get('aligned_accel_x', []) # Longitudinal (approx)
        ay_global = sigs.get('aligned_accel_y', []) # Lateral (approx)
        # az_global = sigs.get('aligned_accel_z', []) # Vertical
        
        # 1. Compute Raw Derived Series (Frame-by-Frame)
        # 1.1 Lateral Load Magnitude
        lat_load_series = [abs(v) for v in ay_global]
        
        # 1.2 Jerk (Stability Proxy)
        # J = d(Accel)/dt. Magnitude of jerk vector.
        # We need timestamps.
        timestamps = [s.timestamp for s in session.samples]
        jerk_series = self._compute_jerk_magnitude(ax_global, ay_global, timestamps)
        
        # 2. Aggregation Per Lap
        lap_stats = []
        
        # To map laps to indices efficiently, we assume laps are ordered slices
        # We can scan through session samples? Or just finding start index.
        
        current_idx = 0
        total_samples = len(session.samples)
        
        for lap in session.laps:
            if not lap.samples:
                lap_stats.append(None)
                continue
                
            # Find start index (Optimization: assume laps are sequential forward)
            # Find first timestamp match with tolerance for float precision
            start_ts = lap.samples[0].timestamp
            TIMESTAMP_TOLERANCE = 0.01  # 10ms tolerance
            
            # Simple linear search from current_idx
            found_start = -1
            for i in range(current_idx, total_samples):
                if abs(session.samples[i].timestamp - start_ts) < TIMESTAMP_TOLERANCE:
                    found_start = i
                    break
            
            if found_start == -1: 
                # Fallback reset search
                for i in range(0, total_samples):
                    if session.samples[i].timestamp == start_ts:
                        found_start = i
                        break
            
            if found_start == -1:
                lap_stats.append(None)
                continue
                
            start_idx = found_start
            end_idx = start_idx + len(lap.samples) # Assuming contiguous
            
            # Slice Signals
            l_lat = lat_load_series[start_idx:end_idx]
            l_long = ax_global[start_idx:end_idx]
            l_jerk = jerk_series[start_idx:end_idx]
            
            if not l_lat:
                lap_stats.append(None)
                continue
                
            metrics = {
                "lap_number": lap.lap_number,
                "lateral": {
                    "avg_load": self._mean(l_lat),
                    "peak_load": max(l_lat) if l_lat else 0
                },
                "longitudinal": {
                    "braking_avg": self._mean([x for x in l_long if x < 0] or [0]),
                    "braking_peak": min(l_long) if l_long else 0, # Max braking is min value (negative)
                    "accel_avg": self._mean([x for x in l_long if x > 0] or [0]),
                    "accel_peak": max(l_long) if l_long else 0
                },
                "stability": {
                    "jerk_avg": self._mean(l_jerk),
                    "jerk_peak": max(l_jerk) if l_jerk else 0
                }
            }
            lap_stats.append(metrics)
            
            current_idx = end_idx # Advance hint
            
        # 3. Normalization (Session Relative)
        # We find session Max for each metric type to normalize 0-1 (using 95th-98th percentile to avoid impacts/noise)
        
        norm_map = self._normalize_lap_stats(lap_stats)
        
        return {
            "laps": norm_map,
            "confidence": confidence,
            "meta": {
                "metric_version": "7.3.2",
                "normalization_basis": "session_max"
            }
        }

    def _compute_jerk_magnitude(self, ax, ay, timestamps) -> List[float]:
        jerk = []
        n = len(timestamps)
        for i in range(1, n):
            dt = timestamps[i] - timestamps[i-1]
            if dt <= 0.001: 
                jerk.append(0)
                continue
                
            dax = ax[i] - ax[i-1]
            day = ay[i] - ay[i-1]
            # Jerk Magnitude = sqrt(dax^2 + day^2) / dt
            j = math.sqrt(dax**2 + day**2) / dt
            jerk.append(j)
            
        # Pad first element
        return [0.0] + jerk

    def _mean(self, data):
        if not data: return 0.0
        return sum(data) / len(data)

    def _normalize_lap_stats(self, stats: List[Dict]) -> List[Dict]:
        """
        Scales metrics 0-1 based on session maximums.
        Inverts Stability (Lower jerk -> Higher Score).
        """
        valid = [s for s in stats if s]
        if not valid: return stats
        
        # Find Maxima
        max_lat = max((s["lateral"]["avg_load"] for s in valid), default=1)
        max_jerk = max((s["stability"]["jerk_avg"] for s in valid), default=1)
        
        # Apply
        out = []
        for s in stats:
            if not s:
                out.append(None)
                continue
            
            # Copy structure
            # Normalized Scores (0-100 scale for UI)
            
            # Lateral Score: Higher load = High Score (Riding harder?)
            # Or is Score separate? Spec: "Mean lateral load... normalized relative"
            norm_lat = min(1.0, s["lateral"]["avg_load"] / (max_lat if max_lat > 0 else 1))
            
            # Stability Score: Low Jerk = High Stability
            # 1.0 - (jerk / max_jerk)
            j_ratio = s["stability"]["jerk_avg"] / (max_jerk if max_jerk > 0 else 1)
            stab_score = 1.0 - min(1.0, j_ratio)
            
            # Add Scores
            s["scores"] = {
                "lateral_load_score": round(norm_lat * 100, 1),
                "stability_score": round(stab_score * 100, 1)
            }
            out.append(s)
            
        return out
