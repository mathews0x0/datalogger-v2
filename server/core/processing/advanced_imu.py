import math
import statistics
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any

@dataclass
class IMUConfig:
    # Approximate mounting offset in meters [x, y, z] from Bike CoG
    # Default: 15cm up (z)
    cog_offset: List[float]
    sample_rate_est: float = 100.0 # Will be detected
    
class AdvancedIMUProcessor:
    """
    Algorithm 1: 2-Pass Precision IMU Fusion
    Pass 1: Gyro bias calibration & GPS-IMU Orientation Alignment (Pitch/Direction)
    Pass 2: Centripetal Lean Angle & Corrected Longitudinal Force calculation
    """
    def __init__(self, imu_smoothing_window: int = 50):
        self.config = IMUConfig(cog_offset=[0.0, 0.0, 0.15])
        self.imu_smoothing_window = imu_smoothing_window
        self.gx_bias: float = 0.0
        self.gy_bias: float = 0.0
        self.gz_bias: float = 0.0
        self.x_gravity_bias: float = 0.0
        self.x_invert_multiplier: int = 1
        
    def calibrate(self, timestamps: List[float], 
                  gx_raw: List[float], gy_raw: List[float], gz_raw: List[float], 
                  ax_raw: List[float], speeds: List[float]):
        # 1. Gyro Bias
        best_var = float('inf')
        window_sz = min(100, len(timestamps))
        
        for i in range(0, max(1, len(timestamps) - window_sz), window_sz or 1):
            gx_slice = gx_raw[i:i+window_sz]
            gy_slice = gy_raw[i:i+window_sz]
            gz_slice = gz_raw[i:i+window_sz]
            
            if not gx_slice or not gy_slice or not gz_slice:
                continue
                
            var = statistics.variance(gx_slice) + statistics.variance(gy_slice) + statistics.variance(gz_slice) if len(gx_slice) > 1 else float('inf')
            
            if var < best_var:
                best_var = var
                self.gx_bias = sum(gx_slice)/len(gx_slice)
                self.gy_bias = sum(gy_slice)/len(gy_slice)
                self.gz_bias = sum(gz_slice)/len(gz_slice)

        # 2. Orientation Alignment
        gps_accels: List[Tuple[float, float]] = []
        for i in range(1, len(speeds)-1):
            dt = (timestamps[i+1] - timestamps[i-1]) / 1000.0
            if dt > 0:
                dv = (speeds[i+1] - speeds[i-1]) / 3.6
                gps_accels.append((timestamps[i], dv / dt / 9.81))

        matched: List[Tuple[float, float]] = []
        gps_idx = 0
        for i, t in enumerate(timestamps):
            while gps_idx < len(gps_accels) - 1 and gps_accels[gps_idx+1][0] <= t:
                gps_idx += 1
            if gps_idx < len(gps_accels) and abs(gps_accels[gps_idx][0] - t) < 1000:
                matched.append((gps_accels[gps_idx][1], ax_raw[i]))

        if len(matched) > 10:
            mean_gps = sum(x[0] for x in matched) / len(matched)
            mean_imu_x = sum(x[1] for x in matched) / len(matched)
            num = sum((x[0] - mean_gps) * (x[1] - mean_imu_x) for x in matched)
            self.x_invert_multiplier = 1 if num > 0 else -1
            
            steady_x = [x[1] for x in matched if abs(x[0]) < 0.05]
            self.x_gravity_bias = statistics.mean(steady_x) if steady_x else 0.0
            print(f"[IMU] Calibrated Algorithm 1: PitchBias={self.x_gravity_bias:.2f}g, Invert={self.x_invert_multiplier}")
        else:
             print("[IMU] Algorithm 1 Calibration Failed: Not enough GPS straight matches.")


    def process(self, timestamps: List[float], 
                ax_raw: List[float], ay_raw: List[float], az_raw: List[float],
                gx_raw: List[float], gy_raw: List[float], gz_raw: List[float],
                speeds: Optional[List[float]] = None, lats: Optional[List[float]] = None, lons: Optional[List[float]] = None) -> Dict[str, Any]:
        """
        Two-Phase IMU Processing Pipeline using Algorithm 1.
        """
        
        if speeds is None or lats is None or lons is None:
            print("[IMU] WARNING: Missing GPS data. Algorithm 1 requires GPS sync.")
            # Still process, just zero lean
            speeds = [0.0] * len(timestamps)
            lats = [0.0] * len(timestamps)
            lons = [0.0] * len(timestamps)

        self.calibrate(timestamps, gx_raw, gy_raw, gz_raw, ax_raw, speeds)
        
        # Smoothing queues
        ax_q = deque(maxlen=self.imu_smoothing_window)
        gz_q = deque(maxlen=self.imu_smoothing_window)
        
        lean_angle: List[float] = []
        ax_cg: List[float] = []
        ay_cg: List[float] = [] # We'll populate this with lateral G
        acceleration_g: List[float] = [] # Pos Ax
        braking_g: List[float] = [] # Neg Ax (absolute value)
        
        for i, t in enumerate(timestamps):
            gx = gx_raw[i] - self.gx_bias
            gz = gz_raw[i] - self.gz_bias
            ax_forward = (ax_raw[i] - self.x_gravity_bias) * self.x_invert_multiplier
            
            ax_q.append(ax_forward)
            gz_q.append(gz)
            
            ax_sm = float(sum(ax_q)/len(ax_q))
            gz_sm = sum(gz_q)/len(gz_q)
            
            v_ms = speeds[i] / 3.6
            
            # Centripetal Lateral G
            lat_g = (v_ms * (gz_sm * math.pi / 180.0)) / 9.81
            lean = math.degrees(math.atan(-lat_g))
            
            # Exponential Moving Average Smoothing
            alpha_lean = 0.15  # Smooth lean heavily
            alpha_g = 0.15     # Smooth G-forces moderately

            if i == 0:
                 smoothed_lean = lean
                 smoothed_lat_g = lat_g
                 smoothed_ax = ax_sm
            else:
                 smoothed_lean = (alpha_lean * lean) + ((1 - alpha_lean) * prev_lean)
                 smoothed_lat_g = (alpha_g * lat_g) + ((1 - alpha_g) * prev_lat_g)
                 smoothed_ax = (alpha_g * ax_sm) + ((1 - alpha_g) * prev_ax)

            prev_lean = smoothed_lean
            prev_lat_g = smoothed_lat_g
            prev_ax = smoothed_ax
            
            lean_angle.append(round(smoothed_lean, 1))
            ax_cg.append(round(smoothed_ax, 2))
            ay_cg.append(round(smoothed_lat_g, 2))
            
            # Acceleration / Braking separation
            if smoothed_ax > 0:
                 acceleration_g.append(round(smoothed_ax, 2))
                 braking_g.append(0.0)
            else:
                 acceleration_g.append(0.0)
                 braking_g.append(round(abs(smoothed_ax), 2))

        return {
            "lean_angle": lean_angle,
            "pitch_angle": [0.0]*len(timestamps),
            "yaw_angle": [0.0]*len(timestamps),
            "ax_cg": ax_cg,  # Raw longitudinal G
            "ay_cg": ay_cg,  # Lateral G 
            "az_cg": [1.0]*len(timestamps), 
            "acceleration_g": acceleration_g,
            "braking_g": braking_g,
            "lateral_g": ay_cg,
            "confidence": 1.0 
        }

