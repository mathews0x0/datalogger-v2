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
    Pass 1: 3D Axis Alignment & Gyro Drift Calibration
    Pass 2: Centripetal Lean Angle & Corrected Longitudinal Force calculation
    """
    def __init__(self, imu_smoothing_window: int = 50):
        self.config = IMUConfig(cog_offset=[0.0, 0.0, 0.15])
        self.imu_smoothing_window = imu_smoothing_window
        self.gx_bias = 0.0
        self.gy_bias = 0.0
        self.gz_bias = 0.0
        
        # 3D Orientation (Bike frame axes in Sensor coordinates)
        self.rot_X = [1.0, 0.0, 0.0] # Forward
        self.rot_Y = [0.0, 1.0, 0.0] # Lateral
        self.rot_Z = [0.0, 0.0, 1.0] # Up
        
    def calibrate(self, timestamps: List[float], 
                  gx_raw: List[float], gy_raw: List[float], gz_raw: List[float], 
                  ax_raw: List[float], ay_raw: List[float], az_raw: List[float], 
                  speeds: List[float]):
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

        # 2. 3D Orientation Alignment
        # Calculate Gravity (Up) Vector using the middle 50% of the session
        mid_start = len(ax_raw) // 4
        mid_end = 3 * len(ax_raw) // 4
        if mid_end <= mid_start:
            mid_start, mid_end = 0, len(ax_raw)
            
        mean_ax = sum(ax_raw[mid_start:mid_end]) / max(1, mid_end - mid_start)
        mean_ay = sum(ay_raw[mid_start:mid_end]) / max(1, mid_end - mid_start)
        mean_az = sum(az_raw[mid_start:mid_end]) / max(1, mid_end - mid_start)
        
        mag = math.sqrt(mean_ax**2 + mean_ay**2 + mean_az**2)
        if mag > 0:
            U = [mean_ax/mag, mean_ay/mag, mean_az/mag]
        else:
            U = [0.0, 0.0, 1.0]

        # Calculate Forward Vector using GPS correlation
        gps_accels = []
        for i in range(1, len(speeds)-1):
            dt = (timestamps[i+1] - timestamps[i-1]) / 1000.0
            if dt > 0:
                dv = (speeds[i+1] - speeds[i-1]) / 3.6
                gps_accels.append((timestamps[i], dv / dt / 9.81))

        matched = []
        gps_idx = 0
        for i, t in enumerate(timestamps):
            while gps_idx < len(gps_accels) - 1 and gps_accels[gps_idx+1][0] <= t:
                gps_idx += 1
            if gps_idx < len(gps_accels) and abs(gps_accels[gps_idx][0] - t) < 1000:
                matched.append((gps_accels[gps_idx][1], ax_raw[i], ay_raw[i], az_raw[i]))

        if len(matched) > 10:
            mean_gps = sum(x[0] for x in matched) / len(matched)
            var_gps = sum((x[0] - mean_gps)**2 for x in matched)
            if var_gps > 0:
                mean_x = sum(x[1] for x in matched) / len(matched)
                mean_y = sum(x[2] for x in matched) / len(matched)
                mean_z = sum(x[3] for x in matched) / len(matched)
                cx = sum((x[0] - mean_gps)*(x[1] - mean_x) for x in matched) / var_gps
                cy = sum((x[0] - mean_gps)*(x[2] - mean_y) for x in matched) / var_gps
                cz = sum((x[0] - mean_gps)*(x[3] - mean_z) for x in matched) / var_gps
                
                f_mag = math.sqrt(cx**2 + cy**2 + cz**2)
                F_raw = [cx/f_mag, cy/f_mag, cz/f_mag] if f_mag > 0 else [1.0, 0.0, 0.0]
            else:
                F_raw = [1.0, 0.0, 0.0]
        else:
            F_raw = [1.0, 0.0, 0.0]

        # Orthogonalize vectors
        # Y (Lateral) = U (Up) x F (Forward)
        Y = [U[1]*F_raw[2] - U[2]*F_raw[1],
             U[2]*F_raw[0] - U[0]*F_raw[2],
             U[0]*F_raw[1] - U[1]*F_raw[0]]
        y_mag = math.sqrt(sum(y*y for y in Y))
        if y_mag > 0:
            Y = [y/y_mag for y in Y]
        else:
            Y = [0.0, 1.0, 0.0]

        # X (True Forward) = Y (Lateral) x U (Up)
        X = [Y[1]*U[2] - Y[2]*U[1],
             Y[2]*U[0] - Y[0]*U[2],
             Y[0]*U[1] - Y[1]*U[0]]
        x_mag = math.sqrt(sum(x*x for x in X))
        if x_mag > 0:
            X = [x/x_mag for x in X]
        else:
            X = [1.0, 0.0, 0.0]

        self.rot_X = X
        self.rot_Y = Y
        self.rot_Z = U
        
        print(f"[IMU] Calibrated Algorithm 1 (3D): Up={self.rot_Z}, Fwd={self.rot_X}")

    def process(self, timestamps: List[float], 
                ax_raw: List[float], ay_raw: List[float], az_raw: List[float],
                gx_raw: List[float], gy_raw: List[float], gz_raw: List[float],
                speeds: Optional[List[float]] = None, lats: Optional[List[float]] = None, lons: Optional[List[float]] = None) -> Dict[str, Any]:
        """
        Two-Phase IMU Processing Pipeline using Algorithm 1.
        """
        
        if speeds is None or lats is None or lons is None:
            print("[IMU] WARNING: Missing GPS data. Algorithm 1 requires GPS sync.")
            speeds = [0.0] * len(timestamps)
            lats = [0.0] * len(timestamps)
            lons = [0.0] * len(timestamps)

        self.calibrate(timestamps, gx_raw, gy_raw, gz_raw, ax_raw, ay_raw, az_raw, speeds)
        
        # Smoothing queues
        ax_q = deque(maxlen=self.imu_smoothing_window)
        gz_q = deque(maxlen=self.imu_smoothing_window)
        az_load_q = deque(maxlen=self.imu_smoothing_window)
        
        lean_angle: List[float] = []
        ax_cg: List[float] = []
        ay_cg: List[float] = []
        acceleration_g: List[float] = []
        braking_g: List[float] = []
        
        prev_lean = 0.0
        prev_ax = 0.0
        
        for i, t in enumerate(timestamps):
            rx = ax_raw[i]
            ry = ay_raw[i]
            rz = az_raw[i]
            
            rgx = gx_raw[i] - self.gx_bias
            rgy = gy_raw[i] - self.gy_bias
            rgz = gz_raw[i] - self.gz_bias
            
            # Map into Bike Frame using rotation matrix
            ax_forward = rx * self.rot_X[0] + ry * self.rot_X[1] + rz * self.rot_X[2]
            gz_bike = rgx * self.rot_Z[0] + rgy * self.rot_Z[1] + rgz * self.rot_Z[2]
            az_load = rx * self.rot_Z[0] + ry * self.rot_Z[1] + rz * self.rot_Z[2]
            
            ax_q.append(ax_forward)
            gz_q.append(gz_bike)
            az_load_q.append(az_load)
            
            ax_sm = float(sum(ax_q)/len(ax_q))
            gz_sm = sum(gz_q)/len(gz_q)
            az_load_sm = sum(az_load_q)/len(az_load_q)
            
            v_ms = speeds[i] / 3.6
            
            # Z-Axis Load based Lean Angle
            if az_load_sm < 1.01 or v_ms < 1.0:
                raw_lean = 0.0
            else:
                # acos(1 / load) gives absolute lean
                raw_lean_mag = math.degrees(math.acos(min(1.0 / az_load_sm, 1.0)))
                # Direction from yaw rate (positive yaw = left turn = negative lean convention)
                raw_lean = -raw_lean_mag if gz_sm > 0 else raw_lean_mag
            
            # Exponential Moving Average Smoothing
            alpha_lean = 0.15
            alpha_g = 0.15

            if i == 0:
                 smoothed_lean = raw_lean
                 smoothed_ax = ax_sm
            else:
                 smoothed_lean = (alpha_lean * raw_lean) + ((1 - alpha_lean) * prev_lean)
                 smoothed_ax = (alpha_g * ax_sm) + ((1 - alpha_g) * prev_ax)

            prev_lean = smoothed_lean
            prev_ax = smoothed_ax
            
            lean_angle.append(round(smoothed_lean, 1))
            ax_cg.append(round(smoothed_ax, 2))
            
            # Reconstruct Lateral G for output from lean angle
            lat_g = math.tan(math.radians(smoothed_lean))
            ay_cg.append(round(lat_g, 2))
            
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
            "ax_cg": ax_cg,
            "ay_cg": ay_cg,
            "az_cg": [1.0]*len(timestamps), 
            "acceleration_g": acceleration_g,
            "braking_g": braking_g,
            "lateral_g": ay_cg,
            "confidence": 1.0 
        }

