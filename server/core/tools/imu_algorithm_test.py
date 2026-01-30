"""
IMU Data Cleaning Algorithm Test Suite
======================================

Purpose: Find the best algorithm for cleaning noisy motorcycle IMU data.

Input: Raw CSV with noisy IMU data (vibration-contaminated)
Output: Cleaned CSV files with processed values + validation scores

Validation Criteria:
1. Lean angle: -60° to +60°
2. Lean rate: Max 20°/0.1s (200 deg/s) 
3. Accel/Brake switching: Max 2-3 times per 10 seconds
4. GPS-IMU correlation: Braking should match speed decrease
5. Straights: Near-zero lean on detected straights

Author: Datalogger Project
Date: 2026-01-18
"""

import pandas as pd
import numpy as np
import math
import os
from scipy.signal import butter, filtfilt, medfilt
from dataclasses import dataclass
from typing import List, Dict, Tuple

# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class ValidationConfig:
    """Validation thresholds for IMU data quality."""
    max_lean_angle: float = 60.0        # Degrees
    max_lean_rate: float = 200.0        # Deg/s (20° per 0.1s)
    max_accel_brake_switches: int = 3   # Per 10 seconds
    straight_min_length_m: float = 50.0 # Minimum straight length
    straight_max_yaw_rate: float = 3.0  # Deg/s threshold for "straight"
    gps_accel_threshold: float = 0.5    # m/s^2 for clear accel/brake


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def safe_lowpass(data: np.ndarray, cutoff: float, fs: float, order: int = 2) -> np.ndarray:
    """Zero-phase lowpass filter with safety checks."""
    if len(data) < 13:  # Need at least 13 samples for filtfilt
        return data
    
    nyq = 0.5 * fs
    if cutoff >= nyq:
        cutoff = nyq * 0.9
    if cutoff <= 0:
        return data
    
    normal_cutoff = cutoff / nyq
    try:
        b, a = butter(order, normal_cutoff, btype='low', analog=False)
        return filtfilt(b, a, data)
    except Exception:
        return data


def calculate_gps_heading(lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    """Calculate heading from GPS coordinates."""
    headings = np.zeros(len(lats))
    
    for i in range(1, len(lats)):
        lat1, lon1 = math.radians(lats[i-1]), math.radians(lons[i-1])
        lat2, lon2 = math.radians(lats[i]), math.radians(lons[i])
        
        dlon = lon2 - lon1
        x = math.sin(dlon) * math.cos(lat2)
        y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        
        heading = math.degrees(math.atan2(x, y))
        headings[i] = (heading + 360) % 360
    
    headings[0] = headings[1] if len(headings) > 1 else 0
    return headings


def detect_straights(speeds: np.ndarray, lats: np.ndarray, lons: np.ndarray, 
                     fs: float, min_length_m: float = 50.0, max_yaw_rate: float = 3.0) -> np.ndarray:
    """
    Detect straight-line segments using GPS data.
    Returns a boolean mask where True = on a straight.
    """
    n = len(speeds)
    if n < 10:
        return np.zeros(n, dtype=bool)
    
    # Calculate yaw rate from GPS heading
    headings = calculate_gps_heading(lats, lons)
    
    # Unwrap headings to handle 360->0 transitions
    headings_unwrapped = np.unwrap(np.radians(headings))
    headings_deg = np.degrees(headings_unwrapped)
    
    # Calculate yaw rate (deg/s)
    yaw_rate = np.gradient(headings_deg) * fs
    yaw_rate = safe_lowpass(yaw_rate, 1.0, fs)  # Smooth it
    
    # Low yaw rate = straight
    is_low_yaw = np.abs(yaw_rate) < max_yaw_rate
    
    # Find contiguous straight segments > min_length_m
    straight_mask = np.zeros(n, dtype=bool)
    
    # Run-length encoding to find segments
    segment_start = None
    for i in range(n):
        if is_low_yaw[i]:
            if segment_start is None:
                segment_start = i
        else:
            if segment_start is not None:
                # Calculate segment distance
                segment_len = i - segment_start
                if segment_len >= 3:  # At least 3 samples
                    # Estimate distance from speed
                    dt = 1.0 / fs
                    segment_speeds = speeds[segment_start:i] / 3.6  # m/s
                    distance = np.sum(segment_speeds) * dt
                    
                    if distance >= min_length_m:
                        straight_mask[segment_start:i] = True
                
                segment_start = None
    
    # Handle last segment
    if segment_start is not None:
        segment_len = n - segment_start
        if segment_len >= 3:
            dt = 1.0 / fs
            segment_speeds = speeds[segment_start:n] / 3.6
            distance = np.sum(segment_speeds) * dt
            if distance >= min_length_m:
                straight_mask[segment_start:n] = True
    
    return straight_mask


# ============================================================================
# ALGORITHM: Physics-Based (GPS-Derived)
# ============================================================================

class Algorithm_PhysicsBased:
    """
    Uses GPS data primarily. Lean angle from centripetal physics.
    Acceleration from GPS speed derivative.
    """
    name = "PhysicsBased_GPS"
    
    def process(self, df: pd.DataFrame, fs: float) -> pd.DataFrame:
        speeds = df['speed'].values  # km/h
        lats = df['latitude'].values
        lons = df['longitude'].values
        
        speeds_ms = speeds / 3.6
        n = len(speeds)
        
        # GPS-derived acceleration
        gps_accel = np.gradient(speeds_ms) * fs  # m/s^2
        gps_accel = safe_lowpass(gps_accel, 0.5, fs)
        
        # GPS-derived yaw rate
        headings = calculate_gps_heading(lats, lons)
        headings_unwrapped = np.unwrap(np.radians(headings))
        yaw_rate = np.gradient(np.degrees(headings_unwrapped)) * fs  # deg/s
        yaw_rate = safe_lowpass(yaw_rate, 1.0, fs)
        yaw_rate_rad = np.radians(yaw_rate)  # rad/s
        
        # Physics: Lean angle from centripetal force
        # tan(lean) = v * omega / g
        G = 9.81
        lean_angles = []
        for i in range(n):
            v = speeds_ms[i]
            omega = yaw_rate_rad[i]
            
            if v < 2.0:  # < 7 km/h, stationary
                lean_angles.append(0.0)
            else:
                tan_lean = (v * omega) / G
                lean = math.degrees(math.atan(tan_lean))
                lean = max(-60, min(60, lean))
                lean_angles.append(lean)
        
        lean_angles = np.array(lean_angles)
        lean_angles = safe_lowpass(lean_angles, 1.0, fs)
        
        # Acceleration/Braking (longitudinal)
        accel = np.maximum(gps_accel / G, 0)  # G-force (positive only)
        brake = np.abs(np.minimum(gps_accel / G, 0))  # G-force (positive)
        
        # Lateral G from lean (approx: lateral = g * tan(lean))
        lateral_g = np.tan(np.radians(lean_angles))
        lateral_g = np.clip(lateral_g, -1.5, 1.5)
        
        return self._build_output(df, lean_angles, accel, brake, lateral_g)
    
    def _build_output(self, df, lean, accel, brake, lateral):
        result = df.copy()
        result['lean_angle'] = np.round(lean, 1)
        result['acceleration_g'] = np.round(accel, 2)
        result['braking_g'] = np.round(brake, 2)
        result['lateral_g'] = np.round(lateral, 2)
        return result


# ============================================================================
# ALGORITHM: Two-Phase Calibration (User's Request)
# ============================================================================

class Algorithm_TwoPhase:
    """
    Phase 1: Detect straights -> Calibrate biases
    Phase 2: Apply calibration -> Generate clean data
    """
    name = "TwoPhase_Calibration"
    
    def process(self, df: pd.DataFrame, fs: float) -> pd.DataFrame:
        speeds = df['speed'].values
        lats = df['latitude'].values
        lons = df['longitude'].values
        
        # Raw IMU (scaled from 16-bit)
        scale_a = 1.0 / 16384.0 if df['imu_z'].abs().mean() > 1000 else 1.0
        scale_g = 1.0 / 131.0 if df['gyro_x'].abs().max() > 100 else 1.0
        
        ax = df['imu_x'].values * scale_a
        ay = df['imu_y'].values * scale_a
        az = df['imu_z'].values * scale_a
        gx = df['gyro_x'].values * scale_g
        gy = df['gyro_y'].values * scale_g
        gz = df['gyro_z'].values * scale_g
        
        n = len(speeds)
        speeds_ms = speeds / 3.6
        
        # ===== PHASE 1: Straight Detection & Calibration =====
        straight_mask = detect_straights(speeds, lats, lons, fs)
        
        if np.sum(straight_mask) > 20:
            # Bias estimation from straights
            # On straights: Roll rate ≈ 0, Lateral G ≈ 0
            bias_gx = np.mean(gx[straight_mask])
            bias_ay = np.mean(ay[straight_mask])
            
            # Longitudinal bias: Compare with GPS acceleration
            gps_accel = np.gradient(speeds_ms) * fs
            bias_ax = np.mean(ax[straight_mask] - gps_accel[straight_mask])
            
            print(f"[TwoPhase] Straights found: {np.sum(straight_mask)} samples")
            print(f"[TwoPhase] Biases: Gx={bias_gx:.3f}, Ax={bias_ax:.3f}, Ay={bias_ay:.3f}")
        else:
            # Fallback: Use session mean
            print("[TwoPhase] Warning: No straights found, using session mean")
            bias_gx = np.mean(gx)
            bias_ay = np.mean(ay)
            bias_ax = 0
        
        # Apply bias correction
        gx_cal = gx - bias_gx
        ay_cal = ay - bias_ay
        ax_cal = ax - bias_ax
        
        # ===== PHASE 2: Signal Processing =====
        
        # Heavy filtering (0.5-1.0 Hz for vibration rejection)
        gx_f = safe_lowpass(gx_cal, 1.0, fs)
        ay_f = safe_lowpass(ay_cal, 0.5, fs)
        ax_f = safe_lowpass(ax_cal, 0.5, fs)
        
        # Lean angle from gyro integration with decay
        lean_angles = []
        lean = 0.0
        dt = 1.0 / fs
        
        for i in range(n):
            if straight_mask[i]:
                # On straights: Force decay to 0
                lean *= 0.7  # Fast decay
            else:
                # Normal integration with slow drift correction
                lean = lean * 0.99 + gx_f[i] * dt
            
            lean = max(-60, min(60, lean))
            lean_angles.append(lean)
        
        lean_angles = np.array(lean_angles)
        lean_angles = safe_lowpass(lean_angles, 1.0, fs)
        lean_angles = np.clip(lean_angles, -60, 60)  # Final clamp after filter
        
        # GPS-constrained acceleration/braking
        gps_accel = np.gradient(speeds_ms) * fs
        gps_accel = safe_lowpass(gps_accel, 0.5, fs)
        
        accel = np.zeros(n)
        brake = np.zeros(n)
        
        for i in range(n):
            if gps_accel[i] > 0.3:  # Clearly accelerating
                # Use max of GPS and IMU (IMU might under-report due to pitch)
                accel[i] = max(gps_accel[i] / 9.81, max(0, ax_f[i]))
            elif gps_accel[i] < -0.3:  # Clearly braking
                brake[i] = abs(min(gps_accel[i] / 9.81, min(0, ax_f[i])))
        
        # Smooth to reduce switching
        accel = safe_lowpass(accel, 0.3, fs)
        brake = safe_lowpass(brake, 0.3, fs)
        
        # Lateral G = ay (calibrated)
        lateral_g = np.clip(ay_f, -1.5, 1.5)
        
        return self._build_output(df, lean_angles, accel, brake, lateral_g)
    
    def _build_output(self, df, lean, accel, brake, lateral):
        result = df.copy()
        result['lean_angle'] = np.round(lean, 1)
        result['acceleration_g'] = np.round(np.clip(accel, 0, 1.5), 2)
        result['braking_g'] = np.round(np.clip(brake, 0, 2.0), 2)
        result['lateral_g'] = np.round(lateral, 2)
        return result


# ============================================================================
# ALGORITHM: Aggressive Filtering (Simple but Robust)
# ============================================================================

class Algorithm_AggressiveFilter:
    """
    Very heavy filtering to kill all vibration noise.
    Uses GPS as primary source, IMU as secondary.
    """
    name = "AggressiveFilter"
    
    def process(self, df: pd.DataFrame, fs: float) -> pd.DataFrame:
        speeds = df['speed'].values
        lats = df['latitude'].values
        lons = df['longitude'].values
        
        n = len(speeds)
        speeds_ms = speeds / 3.6
        
        # Pure GPS acceleration
        gps_accel = np.gradient(speeds_ms) * fs
        gps_accel = safe_lowpass(gps_accel, 0.3, fs)  # Very heavy filter
        
        # GPS yaw rate for lean
        headings = calculate_gps_heading(lats, lons)
        headings_unwrapped = np.unwrap(np.radians(headings))
        yaw_rate = np.gradient(np.degrees(headings_unwrapped)) * fs
        yaw_rate = safe_lowpass(yaw_rate, 0.5, fs)  # Very heavy filter
        yaw_rate_rad = np.radians(yaw_rate)
        
        # Physics lean
        G = 9.81
        lean_angles = []
        for i in range(n):
            v = speeds_ms[i]
            omega = yaw_rate_rad[i]
            
            if v < 2.0:
                lean_angles.append(0.0)
            else:
                tan_lean = (v * omega) / G
                lean = math.degrees(math.atan(tan_lean))
                lean = max(-60, min(60, lean))
                lean_angles.append(lean)
        
        lean_angles = np.array(lean_angles)
        lean_angles = safe_lowpass(lean_angles, 0.5, fs)
        
        # Acceleration/Braking (clean separation)
        accel = np.maximum(gps_accel / G, 0)
        brake = np.abs(np.minimum(gps_accel / G, 0))
        
        # Dead zone to prevent switching noise
        accel[accel < 0.05] = 0
        brake[brake < 0.05] = 0
        
        lateral_g = np.tan(np.radians(lean_angles))
        lateral_g = np.clip(lateral_g, -1.5, 1.5)
        
        return self._build_output(df, lean_angles, accel, brake, lateral_g)
    
    def _build_output(self, df, lean, accel, brake, lateral):
        result = df.copy()
        result['lean_angle'] = np.round(lean, 1)
        result['acceleration_g'] = np.round(accel, 2)
        result['braking_g'] = np.round(brake, 2)
        result['lateral_g'] = np.round(lateral, 2)
        return result


# ============================================================================
# ALGORITHM: Hybrid Fusion (IMU + GPS)
# ============================================================================

class Algorithm_HybridFusion:
    """
    Fuses IMU gyro for lean angle with GPS for validation.
    Uses GPS acceleration as reference, blends with IMU.
    """
    name = "HybridFusion"
    
    def process(self, df: pd.DataFrame, fs: float) -> pd.DataFrame:
        speeds = df['speed'].values
        lats = df['latitude'].values
        lons = df['longitude'].values
        
        # Scale IMU
        scale_a = 1.0 / 16384.0 if df['imu_z'].abs().mean() > 1000 else 1.0
        scale_g = 1.0 / 131.0 if df['gyro_x'].abs().max() > 100 else 1.0
        
        ax = df['imu_x'].values * scale_a
        ay = df['imu_y'].values * scale_a
        gx = df['gyro_x'].values * scale_g
        
        n = len(speeds)
        speeds_ms = speeds / 3.6
        
        # Detect straights for calibration
        straight_mask = detect_straights(speeds, lats, lons, fs)
        
        # Calibrate gyro bias
        if np.sum(straight_mask) > 10:
            bias_gx = np.median(gx[straight_mask])
        else:
            bias_gx = np.median(gx)
        
        gx_cal = gx - bias_gx
        gx_f = safe_lowpass(gx_cal, 2.0, fs)  # Moderate filter
        
        # GPS physics lean (reference)
        headings = calculate_gps_heading(lats, lons)
        headings_unwrapped = np.unwrap(np.radians(headings))
        yaw_rate = np.gradient(np.degrees(headings_unwrapped)) * fs
        yaw_rate = safe_lowpass(yaw_rate, 1.0, fs)
        yaw_rate_rad = np.radians(yaw_rate)
        
        G = 9.81
        gps_lean = []
        for i in range(n):
            v = speeds_ms[i]
            omega = yaw_rate_rad[i]
            if v < 2.0:
                gps_lean.append(0.0)
            else:
                gps_lean.append(math.degrees(math.atan((v * omega) / G)))
        gps_lean = np.array(gps_lean)
        
        # IMU lean from integration
        imu_lean = []
        lean = 0.0
        dt = 1.0 / fs
        for i in range(n):
            if speeds[i] < 5:  # Stationary
                lean *= 0.5
            else:
                lean = lean * 0.98 + gx_f[i] * dt
            lean = max(-60, min(60, lean))
            imu_lean.append(lean)
        imu_lean = np.array(imu_lean)
        
        # Blend: Trust GPS more when speed is high, IMU when turning
        alpha = np.clip(np.abs(yaw_rate) / 10.0, 0, 1)  # 0-1 based on yaw rate
        lean_angles = (1 - alpha) * gps_lean + alpha * imu_lean
        lean_angles = safe_lowpass(lean_angles, 1.0, fs)
        lean_angles = np.clip(lean_angles, -60, 60)
        
        # Acceleration (GPS primary, IMU secondary)
        gps_accel = np.gradient(speeds_ms) * fs
        gps_accel = safe_lowpass(gps_accel, 0.5, fs)
        
        ax_f = safe_lowpass(ax, 0.5, fs)
        
        # Blend
        fused_accel = 0.7 * (gps_accel / G) + 0.3 * ax_f
        
        accel = np.maximum(fused_accel, 0)
        brake = np.abs(np.minimum(fused_accel, 0))
        
        lateral_g = np.clip(safe_lowpass(ay, 0.5, fs), -1.5, 1.5)
        
        return self._build_output(df, lean_angles, accel, brake, lateral_g)
    
    def _build_output(self, df, lean, accel, brake, lateral):
        result = df.copy()
        result['lean_angle'] = np.round(lean, 1)
        result['acceleration_g'] = np.round(np.clip(accel, 0, 1.5), 2)
        result['braking_g'] = np.round(np.clip(brake, 0, 2.0), 2)
        result['lateral_g'] = np.round(lateral, 2)
        return result


# ============================================================================
# VALIDATION ENGINE
# ============================================================================

class ValidationEngine:
    """Validates processed IMU data against constraints."""
    
    def __init__(self, config: ValidationConfig = None):
        self.config = config or ValidationConfig()
    
    def validate(self, df: pd.DataFrame, fs: float) -> Tuple[int, List[str]]:
        """
        Returns (score 0-100, list of issues).
        """
        score = 100
        issues = []
        
        lean = df['lean_angle'].values
        accel = df['acceleration_g'].values
        brake = df['braking_g'].values
        speeds = df['speed'].values
        
        n = len(lean)
        
        # 1. Lean angle range
        if np.any(np.abs(lean) > self.config.max_lean_angle):
            exceed_count = np.sum(np.abs(lean) > self.config.max_lean_angle)
            issues.append(f"FAIL: Lean exceeded ±{self.config.max_lean_angle}° ({exceed_count} samples)")
            score -= 25
        
        # 2. Lean rate (abrupt changes)
        lean_rate = np.abs(np.gradient(lean) * fs)
        max_rate = np.max(lean_rate)
        if max_rate > self.config.max_lean_rate:
            issues.append(f"FAIL: Lean rate too fast ({max_rate:.0f} deg/s, max {self.config.max_lean_rate})")
            score -= 25
        
        # 3. Accel/Brake switching frequency
        # Count sign changes in net force
        net_force = accel - brake
        sign_changes = np.sum(np.diff(np.sign(net_force)) != 0)
        duration_s = n / fs
        switches_per_10s = (sign_changes / duration_s) * 10
        
        if switches_per_10s > self.config.max_accel_brake_switches:
            issues.append(f"FAIL: Too many accel/brake switches ({switches_per_10s:.1f}/10s)")
            score -= 20
        
        # 4. GPS correlation
        speeds_ms = speeds / 3.6
        gps_accel = np.gradient(speeds_ms) * fs
        
        # Check for braking when GPS says accelerating (and vice versa)
        mismatches = 0
        for i in range(n):
            if gps_accel[i] > self.config.gps_accel_threshold and brake[i] > 0.1:
                mismatches += 1
            elif gps_accel[i] < -self.config.gps_accel_threshold and accel[i] > 0.1:
                mismatches += 1
        
        mismatch_pct = (mismatches / n) * 100
        if mismatch_pct > 10:
            issues.append(f"FAIL: GPS-IMU mismatch ({mismatch_pct:.1f}%)")
            score -= 15
        elif mismatch_pct > 5:
            issues.append(f"WARN: GPS-IMU mismatch ({mismatch_pct:.1f}%)")
            score -= 5
        
        # 5. Straight detection (lean should be near 0)
        straight_mask = detect_straights(speeds, df['latitude'].values, df['longitude'].values, fs)
        if np.sum(straight_mask) > 10:
            straight_lean = np.abs(lean[straight_mask])
            mean_straight_lean = np.mean(straight_lean)
            if mean_straight_lean > 10:
                issues.append(f"FAIL: Lean on straights too high ({mean_straight_lean:.1f}°)")
                score -= 10
            elif mean_straight_lean > 5:
                issues.append(f"WARN: Lean on straights ({mean_straight_lean:.1f}°)")
                score -= 5
        
        # Clamp score
        score = max(0, min(100, score))
        
        if not issues:
            issues.append("PASS: All constraints satisfied")
        
        return score, issues


# ============================================================================
# TEST RUNNER
# ============================================================================

def run_test_suite(input_csv: str, output_dir: str = None):
    """
    Run all algorithms on the input CSV and validate results.
    """
    print(f"=" * 60)
    print(f"IMU Algorithm Test Suite")
    print(f"=" * 60)
    print(f"\nInput: {input_csv}")
    
    # Load data
    df = pd.read_csv(input_csv)
    print(f"Loaded {len(df)} samples")
    
    # Determine sample rate
    timestamps = df['timestamp'].values
    dt = np.median(np.diff(timestamps))
    fs = 1.0 / dt if dt > 0 else 10.0
    print(f"Sample rate: {fs:.1f} Hz")
    
    # Determine output directory
    if output_dir is None:
        output_dir = os.path.dirname(input_csv)
    
    # Define algorithms
    algorithms = [
        Algorithm_PhysicsBased(),
        Algorithm_TwoPhase(),
        Algorithm_AggressiveFilter(),
        Algorithm_HybridFusion(),
    ]
    
    validator = ValidationEngine()
    results = []
    
    print(f"\n{'Algorithm':<25} {'Score':>8} {'Status':<40}")
    print("-" * 75)
    
    for algo in algorithms:
        try:
            # Process
            processed_df = algo.process(df, fs)
            
            # Validate
            score, issues = validator.validate(processed_df, fs)
            
            # Save output
            base_name = os.path.basename(input_csv).replace('.csv', '')
            output_file = os.path.join(output_dir, f"imu_cleaned_{algo.name}_{base_name}.csv")
            
            # Select columns to save
            output_cols = ['timestamp', 'latitude', 'longitude', 'speed', 'satellites',
                          'imu_x', 'imu_y', 'imu_z', 'gyro_x', 'gyro_y', 'gyro_z',
                          'lean_angle', 'acceleration_g', 'braking_g', 'lateral_g']
            output_cols = [c for c in output_cols if c in processed_df.columns]
            processed_df[output_cols].to_csv(output_file, index=False)
            
            # Print result
            status = issues[0] if issues else "OK"
            print(f"{algo.name:<25} {score:>8}/100 {status:<40}")
            
            results.append({
                'algorithm': algo.name,
                'score': score,
                'issues': issues,
                'output_file': output_file
            })
            
        except Exception as e:
            print(f"{algo.name:<25} {'ERROR':>8} {str(e)[:40]}")
            results.append({
                'algorithm': algo.name,
                'score': 0,
                'issues': [f"ERROR: {str(e)}"],
                'output_file': None
            })
    
    # Summary
    print(f"\n{'=' * 60}")
    print("DETAILED RESULTS")
    print(f"{'=' * 60}")
    
    for r in results:
        print(f"\n[{r['algorithm']}] Score: {r['score']}/100")
        for issue in r['issues']:
            print(f"  - {issue}")
        if r['output_file']:
            print(f"  -> Saved: {os.path.basename(r['output_file'])}")
    
    # Winner
    best = max(results, key=lambda x: x['score'])
    print(f"\n{'=' * 60}")
    print(f"WINNER: {best['algorithm']} ({best['score']}/100)")
    print(f"{'=' * 60}")
    
    return results


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python imu_algorithm_test.py <input.csv>")
        sys.exit(1)
    
    input_file = sys.argv[1]
    run_test_suite(input_file)
