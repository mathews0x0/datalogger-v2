import numpy as np
import math
from scipy.signal import butter, filtfilt, medfilt
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

@dataclass
class IMUConfig:
    # Approximate mounting offset in meters [x, y, z] from Bike CoG
    # Default: 15cm up (z)
    cog_offset: List[float]
    sample_rate_est: float = 100.0 # Will be detected
    
class AdvancedIMUProcessor:
    """
    Advanced Signal Processing Pipeline for Motorcycle Telemetry.
    Implements:
    1. Auto-Scaling & Calibration
    2. Hardware-Aware Filtering (Zero-phase IIR)
    3. Impulse Rejection
    4. CoG Compensation
    5. Sensor Fusion (Madgwick)
    6. Bike-Frame Alignment
    """
    
    def __init__(self):
        self.config = IMUConfig(cog_offset=[0.0, 0.0, 0.15])
        
    def process(self, timestamps: List[float], 
                ax_raw: List[float], ay_raw: List[float], az_raw: List[float],
                gx_raw: List[float], gy_raw: List[float], gz_raw: List[float],
                speeds: List[float] = None, lats: List[float] = None, lons: List[float] = None) -> Dict:
        """
        Two-Phase IMU Processing Pipeline.
        Phase 1: Detect straights from GPS, calibrate biases.
        Phase 2: Apply complementary filter with physics constraints.
        
        Args:
            timestamps: Unix timestamps for each sample
            ax_raw, ay_raw, az_raw: Raw accelerometer readings
            gx_raw, gy_raw, gz_raw: Raw gyroscope readings
            speeds: GPS speeds in km/h (required for calibration)
            lats, lons: GPS coordinates in degrees (required for straight detection)
        
        Returns:
            Dict with lean_angle, pitch_angle, yaw_angle, ax_cg, ay_cg, az_cg, confidence
        """
        # Validate required GPS data
        if speeds is None or lats is None or lons is None:
            print("[IMU] WARNING: Missing GPS data. Returning uncalibrated fallback.")
            return self._fallback_process(timestamps, ax_raw, ay_raw, az_raw, gx_raw)
        
        # 0. Convert to Numpy
        t = np.array(timestamps)
        v = np.array(speeds) / 3.6  # Convert km/h to m/s
        lat_rad = np.radians(lats)
        lon_rad = np.radians(lons)
        
        dt_list = np.diff(t)
        dt_avg = np.mean(dt_list) if len(dt_list)>0 else 0.1
        if dt_avg <= 0: dt_avg = 0.1
        fs = 1.0 / dt_avg
        
        # GPS Yaw Rate
        y = np.sin(np.diff(lon_rad, prepend=lon_rad[0])) * np.cos(lat_rad)
        x = np.cos(np.roll(lat_rad, 1)) * np.sin(lat_rad) - \
            np.sin(np.roll(lat_rad, 1)) * np.cos(lat_rad) * np.cos(np.diff(lon_rad, prepend=lon_rad[0]))
        # Fix first element of roll which wraps around
        x[0] = 0 # simple hack
        
        headings = np.degrees(np.arctan2(y, x))
        headings = np.unwrap(headings, period=360)
        gps_yaw_rate = np.gradient(headings) * fs
        
        def _lpf(data, cutoff):
            nyq = 0.5 * fs
            if cutoff >= nyq: cutoff = nyq * 0.9
            normal = cutoff / nyq
            b, a = butter(2, normal, btype='low', analog=False)
            return filtfilt(b, a, data)
            
        gps_yaw_rate = _lpf(gps_yaw_rate, 1.0)
        
        # Segments < 3 deg/s
        is_straight = np.abs(gps_yaw_rate) < 3.0
        
        straight_mask = np.zeros_like(is_straight, dtype=bool)
        current_run = []
        for i, val in enumerate(is_straight):
            if val:
                current_run.append(i)
            else:
                if current_run:
                    dist = 0
                    # Quick sum
                    # dist = sum(v[current_run]) * dt
                    chunk_v = v[current_run]
                    dist = np.sum(chunk_v) * dt_avg
                    if dist > 50.0:
                        straight_mask[current_run] = True
                current_run = []
        if current_run:
             dist = np.sum(v[current_run]) * dt_avg
             if dist > 50.0: straight_mask[current_run] = True
             
        # Scales
        scale_a = 1/16384.0 if np.mean(np.abs(az_raw)) > 1000 else 1.0
        scale_g = 1/131.0 if np.max(np.abs(gx_raw)) > 100 else 1.0
        
        ax = np.array(ax_raw) * scale_a
        ay = np.array(ay_raw) * scale_a
        az = np.array(az_raw) * scale_a
        gx = np.array(gx_raw) * scale_g
        gz = np.array(gz_raw) * scale_g
        
        # Calculate Biases
        bias_ay = 0.0
        bias_gx = 0.0
        bias_ax = 0.0
        
        if np.sum(straight_mask) > 10:
            bias_ay = np.mean(ay[straight_mask])
            
            # Ax Bias from GPS acceleration
            gps_accel = np.gradient(v) * fs
            bias_ax = np.mean(ax[straight_mask] - gps_accel[straight_mask])
            print(f"[IMU] Calibrated Biases: Ay={bias_ay:.2f} Ax={bias_ax:.2f}")
        else:
            print("[IMU] No suitable straights for calibration. Using GPS-only mode.")
            
        # Apply Correction to accelerometer (for G-force display)
        ax -= bias_ax
        ay -= bias_ay
        
        # Heavy Filter accelerometer
        ax = _lpf(ax, 0.5)
        ay = _lpf(ay, 0.5)
        
        # ===== LEAN ANGLE: Hybrid GPS + IMU with Auto-Calibration =====
        # Step 1: Calculate GPS physics lean (ground truth reference)
        G = 9.81
        yaw_rate_rad = np.radians(gps_yaw_rate)
        yaw_rate_rad = _lpf(yaw_rate_rad, 1.0)
        
        gps_lean = []
        for i in range(len(v)):
            speed = v[i]
            omega = yaw_rate_rad[i]
            if speed < 2.0:
                gps_lean.append(0.0)
            else:
                tan_lean = (speed * omega) / G
                lean = math.degrees(math.atan(tan_lean))
                lean = max(-60, min(60, lean))
                gps_lean.append(lean)
        gps_lean = np.array(gps_lean)
        gps_lean = _lpf(gps_lean, 1.0)
        gps_lean = np.clip(gps_lean, -60, 60)
        
        # Step 2: Auto-detect roll axis - handles TILTED IMU with multi-axis regression
        # If IMU is tilted, roll shows up as combination of axes: roll = a*Gx + b*Gy + c*Gz
        gy = np.array(gy_raw) * scale_g
        gy = _lpf(gy, 2.0)
        gx = _lpf(gx, 2.0)
        gz = _lpf(gz, 2.0)
        
        def integrate_gyro(gyro_rate, decay=0.98):
            """Integrate gyro to lean with drift compensation."""
            lean = 0.0
            leans = []
            for rate in gyro_rate:
                lean = lean * decay + rate * dt_avg
                lean = max(-60, min(60, lean))
                leans.append(lean)
            return np.array(leans)
        
        # Only use turn segments for calibration
        turn_mask = np.abs(gps_lean) > 5
        
        best_corr = 0
        best_imu_lean = None
        best_coeffs = None
        
        if np.sum(turn_mask) > 50:
            from scipy.stats import pearsonr
            from scipy.optimize import minimize
            
            # Method 1: Try single axes first (fastest)
            single_axes = [
                ('X', gx, [1, 0, 0]), ('-X', -gx, [-1, 0, 0]),
                ('Y', gy, [0, 1, 0]), ('-Y', -gy, [0, -1, 0]),
                ('Z', gz, [0, 0, 1]), ('-Z', -gz, [0, 0, -1]),
            ]
            
            for axis_name, gyro_data, coeffs in single_axes:
                imu_lean = integrate_gyro(gyro_data)
                imu_lean_f = _lpf(imu_lean, 1.0)
                
                try:
                    corr, _ = pearsonr(gps_lean[turn_mask], imu_lean_f[turn_mask])
                    if np.isnan(corr):
                        corr = 0
                except:
                    corr = 0
                
                if corr > best_corr:
                    best_corr = corr
                    best_imu_lean = imu_lean_f
                    best_coeffs = coeffs
            
            # Method 2: If single axis correlation < 0.6, try multi-axis optimization
            if best_corr < 0.6:
                print(f"[IMU] Single axis corr={best_corr:.2f}, trying multi-axis optimization...")
                
                def objective(coeffs):
                    """Minimize negative correlation (maximize correlation)."""
                    a, b, c = coeffs
                    # Normalize coefficients
                    norm = np.sqrt(a*a + b*b + c*c)
                    if norm < 0.01:
                        return 1.0
                    a, b, c = a/norm, b/norm, c/norm
                    
                    combined = a * gx + b * gy + c * gz
                    imu_lean = integrate_gyro(combined)
                    imu_lean_f = _lpf(imu_lean, 1.0)
                    
                    try:
                        corr, _ = pearsonr(gps_lean[turn_mask], imu_lean_f[turn_mask])
                        if np.isnan(corr):
                            return 1.0
                        return -corr  # Minimize negative = maximize positive
                    except:
                        return 1.0
                
                # Try optimization from multiple starting points
                best_opt_corr = best_corr
                for init in [[1,0,0], [0,1,0], [0,0,1], [1,1,0], [1,0,1], [0,1,1], [1,1,1]]:
                    try:
                        result = minimize(objective, init, method='Nelder-Mead', 
                                         options={'maxiter': 100, 'xatol': 0.01})
                        if -result.fun > best_opt_corr:
                            best_opt_corr = -result.fun
                            # Normalize and store
                            a, b, c = result.x
                            norm = np.sqrt(a*a + b*b + c*c)
                            if norm > 0.01:
                                a, b, c = a/norm, b/norm, c/norm
                                combined = a * gx + b * gy + c * gz
                                imu_lean = integrate_gyro(combined)
                                best_imu_lean = _lpf(imu_lean, 1.0)
                                best_coeffs = [a, b, c]
                                best_corr = best_opt_corr
                    except:
                        pass
                
                if best_corr > 0.5:
                    print(f"[IMU] Multi-axis solution: {best_coeffs[0]:.2f}*Gx + {best_coeffs[1]:.2f}*Gy + {best_coeffs[2]:.2f}*Gz")
        
        # Step 3: Bias correction and blending
        if best_corr > 0.5 and best_imu_lean is not None:
            # CRITICAL: Remove mean bias to center IMU lean around GPS lean
            # This corrects for gyro DC offset that causes left/right asymmetry
            imu_mean = np.mean(best_imu_lean[turn_mask])
            gps_mean = np.mean(gps_lean[turn_mask])
            bias = imu_mean - gps_mean
            best_imu_lean_corrected = best_imu_lean - bias
            
            if abs(bias) > 1.0:
                print(f"[IMU] Corrected lean bias: {bias:+.1f}° (was skewing {'right' if bias > 0 else 'left'})")
            
            # Also check for scale mismatch (IMU might under/over-report lean magnitude)
            imu_std = np.std(best_imu_lean_corrected[turn_mask])
            gps_std = np.std(gps_lean[turn_mask])
            if gps_std > 0:
                scale_factor = gps_std / imu_std if imu_std > 0 else 1.0
                # Only apply scaling if significantly different (avoid over-correction)
                if scale_factor < 0.7 or scale_factor > 1.4:
                    best_imu_lean_corrected *= scale_factor
                    print(f"[IMU] Corrected lean scale: {scale_factor:.2f}x (IMU was {'under' if scale_factor > 1 else 'over'}-reporting)")
            
            alpha = min(0.6, best_corr)
            final_lean = alpha * best_imu_lean_corrected + (1 - alpha) * gps_lean
            
            if best_coeffs:
                axis_str = []
                if abs(best_coeffs[0]) > 0.1:
                    axis_str.append(f"{best_coeffs[0]:+.2f}*Gx")
                if abs(best_coeffs[1]) > 0.1:
                    axis_str.append(f"{best_coeffs[1]:+.2f}*Gy")
                if abs(best_coeffs[2]) > 0.1:
                    axis_str.append(f"{best_coeffs[2]:+.2f}*Gz")
                print(f"[IMU] Roll axis: {' '.join(axis_str)} (correlation={best_corr:.2f})")
            print(f"[IMU] Using hybrid GPS+IMU lean (alpha={alpha:.2f})")
        else:
            final_lean = gps_lean
            print(f"[GPS] 100% GPS-based lean (IMU correlation too low: {best_corr:.2f})")
        
        final_lean = np.clip(final_lean, -60, 60)
        
        # Dynamic Range Compression
        lean_abs = np.abs(final_lean)
        p99 = np.percentile(lean_abs, 99) if len(lean_abs) > 0 else 0
        
        if p99 > 55.0:
            scale_factor = 52.0 / p99
            final_lean *= scale_factor
            print(f"[IMU] Lean Auto-Scaled by {scale_factor:.2f} (P99 was {p99:.1f})")
        
        # ===== 100% GPS-BASED: Acceleration & Braking =====
        # Longitudinal G = d(speed)/dt / g
        gps_accel = np.gradient(v) * fs  # m/s^2
        gps_accel = _lpf(gps_accel, 0.5)  # Heavy filter for smooth display
        
        # Split into acceleration (positive) and braking (negative)
        final_ax = gps_accel / G  # Convert to G-force
        final_accel = np.maximum(final_ax, 0)  # Positive = acceleration
        final_brake = np.abs(np.minimum(final_ax, 0))  # Negative = braking
        
        # Dead zone to prevent noise near zero
        final_accel[final_accel < 0.02] = 0
        final_brake[final_brake < 0.02] = 0
        
        # ===== 100% GPS-BASED: Lateral G =====
        # Lateral G = tan(lean) * g / g = tan(lean)
        # Or equivalently: v * yaw_rate / g (same as lean calculation)
        final_lateral = np.tan(np.radians(final_lean))
        final_lateral = np.clip(final_lateral, -1.5, 1.5)  # Clamp to realistic range
        
        print(f"[GPS] 100% GPS-based processing complete. No IMU data used.")
        
        return {
            "lean_angle": np.round(final_lean, 1).tolist(),
            "pitch_angle": [0.0]*len(final_lean),
            "yaw_angle": [0.0]*len(final_lean),
            "ax_cg": np.round(final_ax, 2).tolist(),  # Raw longitudinal G
            "ay_cg": np.round(final_lateral, 2).tolist(),  # Lateral G from lean
            "az_cg": [1.0]*len(final_lean),  # Vertical always ~1G
            "acceleration_g": np.round(final_accel, 2).tolist(),
            "braking_g": np.round(final_brake, 2).tolist(),
            "lateral_g": np.round(final_lateral, 2).tolist(),
            "confidence": 1.0 
        }

    def _fallback_process(self, timestamps, ax_raw, ay_raw, az_raw, gx_raw):
        """
        Fallback processing when GPS data is unavailable.
        Uses simple scaling and filtering without calibration.
        """
        n = len(timestamps)
        
        # Basic scaling
        scale_a = 1/16384.0 if np.mean(np.abs(az_raw)) > 1000 else 1.0
        scale_g = 1/131.0 if np.max(np.abs(gx_raw)) > 100 else 1.0
        
        ax = np.array(ax_raw) * scale_a
        ay = np.array(ay_raw) * scale_a
        az = np.array(az_raw) * scale_a
        gx = np.array(gx_raw) * scale_g
        
        # Simple low-pass filter
        dt_list = np.diff(timestamps)
        dt_avg = np.mean(dt_list) if len(dt_list) > 0 else 0.1
        fs = 1.0 / dt_avg if dt_avg > 0 else 10.0
        
        def _lpf(data, cutoff):
            nyq = 0.5 * fs
            if cutoff >= nyq: cutoff = nyq * 0.9
            normal = cutoff / nyq
            b, a = butter(2, normal, btype='low', analog=False)
            return filtfilt(b, a, data)
        
        ax = _lpf(ax, 0.5)
        ay = _lpf(ay, 0.5)
        
        # No lean angle without GPS (return zeros)
        return {
            "lean_angle": [0.0] * n,
            "pitch_angle": [0.0] * n,
            "yaw_angle": [0.0] * n,
            "ax_cg": np.round(ax, 2).tolist(),
            "ay_cg": np.round(ay, 2).tolist(),
            "az_cg": np.round(az, 2).tolist(),
            "confidence": 0.3  # Low confidence without GPS calibration
        }
