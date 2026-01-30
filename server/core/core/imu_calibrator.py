import math
from typing import List, Dict, Optional, Tuple
from src.analysis.core.models import Sample

class IMUCalibrator:
    """
    Phase 7.3.1: Sensor Calibration & Trust Layer.
    Detects static windows to estimate Gravity Vector and Gyro Bias.
    Zero-dependency (Pure Python).
    """
    
    def calibrate(self, samples: List[Sample], window_sec: float = 2.0, threshold_std_dev: float = 2000.0) -> Dict:
        """
        Scans for a static period to calibrate IMU.
        
        Args:
            samples: Session samples
            window_sec: Window duration
            threshold_std_dev: Max allowed standard deviation (raw units) to consider 'static'.
                               Default 2000 covers engine vibration/noise while parked.
        """
        if not samples:
            return {"calibrated": False, "reason": "No samples"}
            
        freq = self._estimate_frequency(samples)
        window_size = int(freq * window_sec)
        
        if len(samples) < window_size:
             # Just use what we have if barely enough? No, stricter.
             return {"calibrated": False, "reason": "Session too short"}
             
        # Scan for best window (lowest variance)
        best_variance = float('inf')
        best_window = None
        
        # Step size optimization
        step = max(1, window_size // 2)
        
        # Only scan the first 60 seconds? Or whole session?
        # Usually parked at start or end.
        # Let's scan START (first 2 mins) and END.
        # For simplicity, scan all but with large steps.
        
        limit_idx = min(len(samples), int(freq * 120)) # First 2 mins
        
        for i in range(0, limit_idx - window_size, step):
            window = samples[i : i+window_size]
            var = self._compute_accel_variance(window)
            if var < best_variance:
                best_variance = var
                best_window = window
                
        # Check Quality
        std_dev = math.sqrt(best_variance)
        
        if std_dev > threshold_std_dev:
             return {
                 "calibrated": False, 
                 "reason": f"No static window found (Best StdDev: {std_dev:.1f})",
                 "confidence": "NONE"
             }
             
        # Compute Calibration Vectors
        gravity = self._mean_accel(best_window)
        
        gyro_bias = None
        if best_window[0].imu.gyro_x is not None:
             gyro_bias = self._mean_gyro(best_window)
             
        return {
            "calibrated": True,
            "confidence": "HIGH" if std_dev < 500 else "MEDIUM",
            "gravity_vector": gravity,
            "gyro_bias": gyro_bias,
            "calibration_epoch": best_window[0].timestamp,
            "message": f"Calibrated using window at T+{best_window[0].timestamp - samples[0].timestamp:.1f}s"
        }

    def compute_rotation_matrix(self, gravity_vector: Tuple[float, float, float]) -> List[List[float]]:
        """
        Computes 3x3 rotation matrix to align the Measured Gravity Vector to Global Z (0,0,1).
        Uses Rodrigues' rotation formula.
        """
        # Source: Gravity Vector (Normalized)
        gx, gy, gz = gravity_vector
        mag = math.sqrt(gx*gx + gy*gy + gz*gz)
        if mag == 0: return [[1,0,0],[0,1,0],[0,0,1]]
        
        src = (gx/mag, gy/mag, gz/mag)
        dest = (0.0, 0.0, 1.0)
        
        # If already aligned
        if abs(src[0]) < 1e-6 and abs(src[1]) < 1e-6 and src[2] > 0:
            return [[1,0,0],[0,1,0],[0,0,1]]
            
        # Axis of Rotation = src x dest
        # (sy*dz - sz*dy, ...) -> (sy*1 - 0, -sx*1 + 0, 0) -> (sy, -sx, 0)
        v = (src[1], -src[0], 0.0) 
        
        # Sine of angle = magnitude of cross product
        s = math.sqrt(v[0]**2 + v[1]**2)
        
        # Cosine of angle = src . dest = sz
        c = src[2]
        
        if s == 0: # 180 degree flip (upside down)
             # Arbitrary axis
             return [[1,0,0],[0,-1,0],[0,0,-1]] 
             
        # Rodrigues Matrix
        # I + [v]x + [v]x^2 * (1-c)/s^2
        # Actually simpler form: 
        # R = I + [v]x + [v]x^2 * (1 / (1+c)) 
        
        vx, vy, vz = v
        
        # Skew symmetric matrix [v]x
        # 0  -vz  vy
        # vz  0  -vx
        # -vy vx  0
        # Here vz=0
        
        c1 = 1.0 / (1.0 + c)
        
        r00 = 1 + (-vy * -vy * c1) + (-vz*-vz*c1) # wait formula check
        # R = I + K + K^2 * (1/(1+c))
        # K = [[0, 0, vy], [0, 0, -vx], [-vy, vx, 0]]
        # K^2 = [[-vy^2, vy*vx, 0], [vx*vy, -vx^2, 0], [0, 0, -vy^2-vx^2]]
        
        # R00 = 1 + 0 + (-vy^2)*k
        # R01 = 0 + 0 + (vy*vx)*k
        # R02 = vy + 0
        
        k = 1.0 / (1.0 + c)
        
        R = [
            [1 - (vy**2)*k,     (vx*vy)*k,      vy],
            [(vx*vy)*k,         1 - (vx**2)*k,  -vx],
            [-vy,               vx,             1 - (vx**2 + vy**2)*k] 
        ]
        
        # Term 3,3 check: 1 - s^2/(1+sz) = 1 - (1-c^2)/(1+c) = 1 - (1-c) = c = sz. Correct.
        
        return R

    def apply_rotation(self, vec: Tuple[float, float, float], R: List[List[float]]) -> Tuple[float, float, float]:
        """Matrix multiplication R * vec"""
        vx, vy, vz = vec
        return (
            R[0][0]*vx + R[0][1]*vy + R[0][2]*vz,
            R[1][0]*vx + R[1][1]*vy + R[1][2]*vz,
            R[2][0]*vx + R[2][1]*vy + R[2][2]*vz
        )

    # --- Helpers ---
    def _estimate_frequency(self, samples):
        if len(samples) < 2: return 10.0
        dur = samples[-1].timestamp - samples[0].timestamp
        if dur <= 0: return 10.0
        return len(samples) / dur

    def _compute_accel_variance(self, window: List[Sample]) -> float:
        vals_x = [s.imu.accel_x for s in window]
        vals_y = [s.imu.accel_y for s in window]
        vals_z = [s.imu.accel_z for s in window]
        return self._var(vals_x) + self._var(vals_y) + self._var(vals_z)

    def _var(self, data):
        if not data: return 0.0
        mean = sum(data) / len(data)
        return sum((x - mean) ** 2 for x in data) / len(data)

    def _mean_accel(self, window):
        n = len(window)
        return (
            sum(s.imu.accel_x for s in window)/n,
            sum(s.imu.accel_y for s in window)/n,
            sum(s.imu.accel_z for s in window)/n
        )

    def _mean_gyro(self, window):
        n = len(window)
        return (
            sum(s.imu.gyro_x for s in window)/n,
            sum(s.imu.gyro_y for s in window)/n,
            sum(s.imu.gyro_z for s in window)/n
        )
