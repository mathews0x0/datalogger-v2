"""
IMU Auto-Calibration: Detect Roll Axis from GPS Correlation

Strategy:
1. Calculate GPS-derived lean angles (ground truth)
2. For each gyro axis (X, Y, Z) and sign (+/-):
   - Integrate gyro rate to get lean estimate
   - Correlate with GPS lean
3. The axis/sign with highest correlation is the roll axis
4. Use that axis for enhanced lean calculation

This allows the IMU to be mounted in ANY orientation.
"""

import numpy as np
from scipy.signal import butter, filtfilt, correlate
from scipy.stats import pearsonr
import math


def safe_lowpass(data: np.ndarray, cutoff: float, fs: float, order: int = 2) -> np.ndarray:
    """Zero-phase lowpass filter with safety checks."""
    if len(data) < 13:
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


def integrate_gyro_to_lean(gyro_rate: np.ndarray, fs: float, decay: float = 0.98) -> np.ndarray:
    """
    Integrate gyro rate to lean angle with drift compensation.
    
    Args:
        gyro_rate: Roll rate in deg/s
        fs: Sample rate
        decay: Decay factor per sample (0.98 = slow drift correction)
    
    Returns:
        Estimated lean angles in degrees
    """
    dt = 1.0 / fs
    lean = 0.0
    leans = []
    
    for rate in gyro_rate:
        lean = lean * decay + rate * dt
        lean = max(-60, min(60, lean))
        leans.append(lean)
    
    return np.array(leans)


def detect_roll_axis(gx: np.ndarray, gy: np.ndarray, gz: np.ndarray,
                     gps_lean: np.ndarray, fs: float) -> dict:
    """
    Auto-detect which gyro axis corresponds to roll (lean) by correlating
    with GPS-derived lean angles.
    
    Args:
        gx, gy, gz: Raw gyro data (will be auto-scaled if needed)
        gps_lean: GPS-derived lean angles (ground truth)
        fs: Sample rate in Hz
    
    Returns:
        dict with:
            - 'axis': 'X', 'Y', or 'Z'
            - 'sign': +1 or -1
            - 'correlation': Pearson correlation coefficient
            - 'confidence': 'high', 'medium', or 'low'
    """
    # Auto-scale gyro if raw 16-bit values
    scale = 1.0
    max_val = max(np.max(np.abs(gx)), np.max(np.abs(gy)), np.max(np.abs(gz)))
    if max_val > 100:  # Likely raw 16-bit
        scale = 131.0  # 131 LSB/deg/s for ±250°/s range
    
    gx_scaled = gx / scale
    gy_scaled = gy / scale
    gz_scaled = gz / scale
    
    # Filter to remove vibration noise
    gx_f = safe_lowpass(gx_scaled, 2.0, fs)
    gy_f = safe_lowpass(gy_scaled, 2.0, fs)
    gz_f = safe_lowpass(gz_scaled, 2.0, fs)
    
    # Also filter GPS lean for fair comparison
    gps_lean_f = safe_lowpass(gps_lean, 2.0, fs)
    
    # Test all 6 axis/sign combinations
    candidates = [
        ('X', +1, gx_f),
        ('X', -1, -gx_f),
        ('Y', +1, gy_f),
        ('Y', -1, -gy_f),
        ('Z', +1, gz_f),
        ('Z', -1, -gz_f),
    ]
    
    results = []
    
    for axis, sign, gyro_rate in candidates:
        # Integrate to get lean estimate
        imu_lean = integrate_gyro_to_lean(gyro_rate, fs)
        imu_lean_f = safe_lowpass(imu_lean, 1.0, fs)
        
        # Calculate correlation with GPS lean
        # Use only samples where we're actually turning (|lean| > 5°)
        mask = np.abs(gps_lean_f) > 5
        
        if np.sum(mask) > 50:  # Need enough turning samples
            try:
                corr, pvalue = pearsonr(gps_lean_f[mask], imu_lean_f[mask])
                if np.isnan(corr):
                    corr = 0
            except:
                corr = 0
        else:
            corr = 0
        
        results.append({
            'axis': axis,
            'sign': sign,
            'correlation': corr,
            'imu_lean': imu_lean_f
        })
        
        print(f"  Gyro {'+' if sign > 0 else '-'}{axis}: correlation = {corr:.3f}")
    
    # Find best match
    best = max(results, key=lambda x: x['correlation'])
    
    # Determine confidence
    if best['correlation'] > 0.7:
        confidence = 'high'
    elif best['correlation'] > 0.4:
        confidence = 'medium'
    else:
        confidence = 'low'
    
    return {
        'axis': best['axis'],
        'sign': best['sign'],
        'correlation': best['correlation'],
        'confidence': confidence,
        'imu_lean': best['imu_lean'],
        'all_results': results
    }


def enhanced_lean_calculation(gps_lean: np.ndarray, imu_lean: np.ndarray, 
                               correlation: float) -> np.ndarray:
    """
    Blend GPS and IMU lean based on correlation quality.
    
    High correlation: Trust IMU more (captures actual lean)
    Low correlation: Trust GPS more (reliable but physics-only)
    """
    if correlation > 0.7:
        # High correlation: 70% IMU, 30% GPS
        alpha = 0.7
    elif correlation > 0.4:
        # Medium: 50/50 blend
        alpha = 0.5
    else:
        # Low: Mostly GPS
        alpha = 0.2
    
    blended = alpha * imu_lean + (1 - alpha) * gps_lean
    return np.clip(blended, -60, 60)


# Test function
def test_axis_detection(csv_path: str):
    """Test axis detection on a CSV file."""
    import pandas as pd
    
    print(f"\n{'='*60}")
    print("IMU Roll Axis Auto-Detection")
    print(f"{'='*60}")
    print(f"\nInput: {csv_path}")
    
    df = pd.read_csv(csv_path)
    n = len(df)
    
    # Get sample rate
    timestamps = df['timestamp'].values
    dt = np.median(np.diff(timestamps))
    fs = 1.0 / dt if dt > 0 else 10.0
    print(f"Sample rate: {fs:.1f} Hz, Samples: {n}")
    
    # Get GPS lean (calculate from speed and heading)
    speeds = df['speed'].values / 3.6  # m/s
    lats = np.radians(df['latitude'].values)
    lons = np.radians(df['longitude'].values)
    
    # Calculate heading
    y = np.sin(np.diff(lons, prepend=lons[0])) * np.cos(lats)
    x = np.cos(np.roll(lats, 1)) * np.sin(lats) - \
        np.sin(np.roll(lats, 1)) * np.cos(lats) * np.cos(np.diff(lons, prepend=lons[0]))
    x[0] = x[1]
    headings = np.degrees(np.arctan2(y, x))
    headings = np.unwrap(np.radians(headings))
    headings = np.degrees(headings)
    
    yaw_rate = np.gradient(headings) * fs  # deg/s
    yaw_rate = safe_lowpass(yaw_rate, 1.0, fs)
    yaw_rate_rad = np.radians(yaw_rate)
    
    # GPS physics lean
    G = 9.81
    gps_lean = []
    for i in range(n):
        v = speeds[i]
        omega = yaw_rate_rad[i]
        if v < 2.0:
            gps_lean.append(0.0)
        else:
            tan_lean = (v * omega) / G
            lean = math.degrees(math.atan(tan_lean))
            lean = max(-60, min(60, lean))
            gps_lean.append(lean)
    gps_lean = np.array(gps_lean)
    gps_lean = safe_lowpass(gps_lean, 1.0, fs)
    
    print(f"\nGPS Lean: min={gps_lean.min():.1f}°, max={gps_lean.max():.1f}°")
    
    # Get gyro data
    gx = df['gyro_x'].values
    gy = df['gyro_y'].values
    gz = df['gyro_z'].values
    
    print("\nTesting all axis orientations...")
    
    result = detect_roll_axis(gx, gy, gz, gps_lean, fs)
    
    print(f"\n{'='*60}")
    print(f"RESULT: Roll axis is {'+' if result['sign'] > 0 else '-'}Gyro_{result['axis']}")
    print(f"Correlation: {result['correlation']:.3f}")
    print(f"Confidence: {result['confidence'].upper()}")
    print(f"{'='*60}")
    
    # Show enhanced lean stats
    if result['confidence'] != 'low':
        enhanced = enhanced_lean_calculation(gps_lean, result['imu_lean'], result['correlation'])
        print(f"\nEnhanced Lean: min={enhanced.min():.1f}°, max={enhanced.max():.1f}°")
    
    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python imu_axis_detect.py <input.csv>")
        sys.exit(1)
    
    test_axis_detection(sys.argv[1])
