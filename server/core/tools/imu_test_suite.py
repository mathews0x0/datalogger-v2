
import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt, detrend
from dataclasses import dataclass
from typing import List, Tuple, Dict
import math

# --- Utilities ---

def load_data(filepath):
    df = pd.read_csv(filepath)
    # Ensure float conversion
    cols = ['imu_x', 'imu_y', 'imu_z', 'gyro_x', 'gyro_y', 'gyro_z', 'speed', 'timestamp', 'latitude', 'longitude']
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
    return df

def save_result(original_df, results, algo_name):
    out = original_df.copy()
    # Replace IMU columns with cleaned ones
    out['accel_x_clean'] = results['ax']
    out['accel_y_clean'] = results['ay'] # Note: Bike Frame Y
    out['accel_z_clean'] = results['az']
    out['lean_angle'] = results['lean']
    
    # User requested: acceleration (forward G), braking (negative forward G)
    # This is essentially ax_longitudinal.
    # Breaking/Accel G map directly to ax_clean (assuming aligned)
    out['long_g'] = results['ax']
    out['lat_g'] = results['ay']
    
    fname = f"output/learning/imu_cleaned_{algo_name}.csv"
    out.to_csv(fname, index=False)
    return fname

def lowpass(data, cutoff, fs, order=2):
    nyq = 0.5 * fs
    if cutoff >= nyq:
        cutoff = nyq * 0.9 # Clamp to 90% of Nyquist to avoid error
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    return filtfilt(b, a, data)

# --- Algorithms ---

class BaseAlgorithm:
    def process(self, df, fs) -> Dict[str, np.ndarray]:
        pass

class Algo_PhysModel_GPS(BaseAlgorithm):
    """
    Algorithm 1: Physics Model + GPS Dominance.
    Ignores Gyro/Accel for orientation. Uses GPS path for lean.
    Uses heavily filtered Accel for G-forces.
    """
    def process(self, df, fs):
        # 1. Lean from GPS
        speeds = df['speed'] / 3.6 # m/s
        
        # Calculate Heading from Lat/Lon
        lats = np.radians(df['latitude'])
        lons = np.radians(df['longitude'])
        
        # Heading calculation
        y = np.sin(np.diff(lons, prepend=lons[0])) * np.cos(lats)
        x = np.cos(lats.shift(1).fillna(lats[0])) * np.sin(lats) - \
            np.sin(lats.shift(1).fillna(lats[0])) * np.cos(lats) * np.cos(np.diff(lons, prepend=lons[0]))
        headings = np.degrees(np.arctan2(y, x))
        
        # Heading Rate (Yaw Rate)
        # Unwrap
        headings = np.unwrap(headings, period=360)
        yaw_rate = np.gradient(headings) * fs # deg/s
        
        # Smooth Yaw Rate (GPS noise)
        yaw_rate = lowpass(yaw_rate, 2.0, fs) # Very low pass 2Hz
        
        # Lean = atan(v * w / g)
        leans = []
        for v, w in zip(speeds, yaw_rate):
            if v < 5.0: 
                leans.append(0.0)
                continue
            rad_w = math.radians(w)
            val = (v * rad_w) / 9.81
            leans.append(math.degrees(math.atan(val)))
            
        leans = np.array(leans)
        leans = np.clip(leans, -60, 60)
        
        # 2. G-Forces from Accel (Heavily Filtered)
        # Scale raw to G (Auto-detect scale)
        # Assume 16-bit 2g: 16384 LSB/g
        scale = 1/16384.0 
        if df['imu_z'].abs().max() > 20000:
             # Likely 4g or 8g? Or just noise.
             # Static Z mean check
             static_z = df['imu_z'].mean()
             if static_z > 8000: scale = 1.0/static_z # Normalize to 1g
        
        ax = df['imu_x'].values * scale
        ay = df['imu_y'].values * scale
        az = df['imu_z'].values * scale
        
        # Remove gravity from X?
        # User says "tilted forward". 
        # Bias subtract long term mean of X?
        ax -= np.mean(ax) # Zero out constant tilt
        
        # Heavy filter
        ax_clean = lowpass(ax, 2.0, fs) # 2Hz for dynamics
        ay_clean = lowpass(ay, 2.0, fs)
        az_clean = lowpass(az, 2.0, fs)
        
        return {"lean": leans, "ax": ax_clean, "ay": ay_clean, "az": az_clean}

class Algo_Complementary(BaseAlgorithm):
    """
    Algorithm 2: Complementary Filter (Aggressive for Noisy 10Hz Data)
    """
    def process(self, df, fs):
        # 1. Scale & Bias Removal
        # Bias estimation from stationary parts? 
        # Assume entire session mean of X/Y is bias if track is closed loop? No.
        # Just use heavy filtering.
        
        # Scale to G
        # If max > 20000 -> 16384 LSB/g. 
        scale = 1/16384.0
        # Check ranges
        if df['imu_z'].abs().mean() < 100: scale = 1.0 # Already G?
        
        ax = df['imu_x'].values * scale
        ay = df['imu_y'].values * scale
        az = df['imu_z'].values * scale
        
        # Gyro
        scale_g = 1.0/131.0
        gx = df['gyro_x'].values * scale_g
        
        # 2. Heavy Pre-Filter (0.5 Hz - 1.0 Hz)
        # Because User complains about "Spikes" and "Spinning".
        # 10Hz data, Nyquist=5Hz. 
        # Cutoff 1Hz.
        
        gx = lowpass(gx, 1.0, fs)
        ay_f = lowpass(ay, 1.0, fs)
        az_f = lowpass(az, 1.0, fs)
        
        # 3. Complementary Filter
        dt = 1.0/fs
        alpha = 0.90 # Trust Gyro 90%, Accel 10% (Slow correction)
        
        angles = []
        angle = 0.0
        
        speeds = df['speed'].values
        
        for i in range(len(ax)):
            # Stationary Check
            if speeds[i] < 5.0: # < 5km/h
                angle = 0.0
                angles.append(0.0)
                continue
                
            # Accel Angle (Roll approx)
            # ay measures gravity component sin(roll) * g ?
            # actually ay = g * sin(roll) + Centripetal
            # While cornering, Ay is NOT essentially gravity. Ideally Ay~0.
            # So standard Complementary filter FAILS for cornering bikes unless we compensate centripetal.
            
            # Alternative: Use "Pseudo-Roll" from Physics for the "Correction" term
            # Lean ~ atan(v*w/g)
            # We don't have good W (Yaw Rate).
            
            # Let's simple clamp raw Roll from Accel
            # If we assume Ay is mostly Gravity (Static) -> ERROR in corners.
            # 
            # Revised approach: 
            # Integration of Gyro X is primary.
            # Decay to 0 (Bleed off drift) instead of correcting to Accelerometer?
            # Or correct to Physics Model?
            
            angle = angle + gx[i] * dt
            
            # Decay (Centering) - prevents inf drift
            angle *= 0.99
            
            # Clamp
            angle = max(-60, min(60, angle))
            angles.append(angle)
            
        # 4. Filter Output G-Forces (Clean ax/accel)
        # 0.5Hz filter for display (Gauge needle smoothness)
        ax_clean = lowpass(ax, 0.5, fs)
        
        # Normalize Ax (Remove bias so median is 0?)
        # Only if track loop. Let's just Clamp.
        ax_clean = np.clip(ax_clean, -1.5, 1.0) # Braking > Accel
        
        # Lat G
        ay_clean = lowpass(ay, 0.5, fs)
        ay_clean = np.clip(ay_clean, -1.5, 1.5)
        
        # Smooth Lean Angle Final (Fix Rate of Change > 300 dps)
        final_lean = lowpass(np.array(angles), 1.0, fs)
        
        return {"lean": final_lean, "ax": ax_clean, "ay": ay_clean, "az": az_f}

class Algo_Madgwick_Robust(BaseAlgorithm):
    """
    Algorithm 3: Madgwick + Outlier Rejection + CoG
    Similar to previous attempt but with specific tuning for the test constraints.
    """
    def process(self, df, fs):
        # Re-use the scaling logic from Algo 2
        acc_mag = np.sqrt(df['imu_x']**2 + df['imu_y']**2 + df['imu_z']**2)
        scale_a = 9.81 / np.mean(acc_mag)
        ax = df['imu_x'] * scale_a
        ay = df['imu_y'] * scale_a
        az = df['imu_z'] * scale_a
        
        # Gyro Scaling? If raw is HUGE, it might be noise.
        # Despike: Median Filter 5
        from scipy.signal import medfilt
        gx = medfilt(df['gyro_x'], 5) * (1/131.0)
        gy = medfilt(df['gyro_y'], 5) * (1/131.0)
        gz = medfilt(df['gyro_z'], 5) * (1/131.0)

        # Madgwick is hard to implement one-shot here cleanly without external lib dep issues observed before.
        # Let's use a simplified "Centripetal Fusion" (Physics + Gyro Bias Est)
        
        # State: Lean Angle
        # Measurement: Phsyics Loan (v*w/g)
        # Input: Gyro X
        
        # Calculate Physics Lean (Meas)
        # Yaw Rate from Gyro Z (Cleaned)
        yaw_rate = lowpass(gz, 5.0, fs)
        speeds = df['speed'] / 3.6
        
        meas_leans = []
        for i in range(len(speeds)):
             val = (speeds[i] * math.radians(yaw_rate[i])) / 9.81
             meas_leans.append(math.degrees(math.atan(val)))
        
        # Fuse with Gyro X (Roll Rate)
        roll_rate = lowpass(gx, 5.0, fs)
        
        # Simple KF
        est_angle = 0.0
        output = []
        dt = 1/fs
        
        # Bias
        bias = 0.0
        
        for i in range(len(speeds)):
            # Predict
            rate = roll_rate[i] - bias
            est_angle += rate * dt
            
            # Update (Weakly pull towards physics)
            meas = meas_leans[i]
            
            # Trust weighting:
            # If speed > 10, trust physics more
            # If speed < 10, trust 0
            
            trust = 0.05
            if speeds[i] < 3.0: 
                meas = 0.0
                trust = 0.2
                
            err = meas - est_angle
            est_angle += trust * err
            
            # Bias update (Integrator)
            bias += -0.001 * err
            
            output.append(est_angle)
            
        return {"lean": np.array(output), "ax": lowpass(ax/9.81, 2, fs), "ay": lowpass(ay/9.81, 2, fs), "az": lowpass(az/9.81, 2, fs)}


# --- Validation Engine ---

def validate(results, speeds_kmh, fs):
    """
    Score the algorithm based on user constraints.
    """
    lean = results['lean']
    ax = results['ax']
    
    score = 100
    report = []
    
    # constraint 1: Range -60 to 60
    if np.max(lean) > 70 or np.min(lean) < -70:
        score -= 20
        report.append("FAIL: Lean angle exceeded +/- 70 deg")
        
    # constraint 2: Continuity (Rate of Change)
    # Check max delta per 100ms (10Hz is user ref, but data is higher?)
    # dt = 1/fs. 20 deg per 0.1s -> 200 deg/s
    diff = np.diff(lean) * fs
    max_rate = np.max(np.abs(diff))
    if max_rate > 300: # 300 deg/s is extremely fast flick
        score -= 30
        report.append(f"FAIL: Lean Changed too fast ({max_rate:.0f} deg/s)")
        
    # constraint 3: Braking/Accel Freq
    # Count transitions zero-crossings of jerk?
    # Simple check: Sign flips in ax (longitudinal)
    # Filter ax heavily before this check to ignore vibration
    signs = np.sign(ax)
    flips = np.sum(np.abs(np.diff(signs))) / 2
    # flips per second
    duration = len(lean) / fs
    flips_per_sec = flips / duration
    
    if flips_per_sec > 1.0: # More than 1 accel/brake transition per second?
        score -= 20
        report.append(f"WARN: Frequent Accel/Brake switching ({flips_per_sec:.1f}/s)")

    # Correlation Check: Drag vs Decel
    # If speed is increasing, ax should be positive (or neg depending on axis).
    # Check correlation coeff
    dv = np.gradient(speeds_kmh)
    # If ax and dv have same sign, good.
    corr = np.corrcoef(dv, ax)[0,1]
    if corr < 0.3:
        # Maybe axis is flipped?
        if corr < -0.3:
            report.append(f"INFO: Ax appears inverted (Corr {corr:.2f})")
        else:
            score -= 20
            report.append(f"FAIL: Poor Accel-Speed Correlation ({corr:.2f})")
    
    return score, report

class Algo_TwoPhase_Calibration(BaseAlgorithm):
    """
    Algorithm 3: Two-Phase Straight-Line Calibration.
    Phase 1: Detect Straights (>50m, Low Yaw) -> Estimate Biases.
    Phase 2: Apply Biases and correct Accel X using GPS trends.
    """
    def process(self, df, fs):
        # --- PHASE 1: Straight Detection ---
        speeds = df['speed'].values / 3.6 # m/s
        lats = np.radians(df['latitude'])
        lons = np.radians(df['longitude'])
        
        # GPS Yaw Rate
        y = np.sin(np.diff(lons, prepend=lons[0])) * np.cos(lats)
        x = np.cos(lats.shift(1).fillna(lats[0])) * np.sin(lats) - \
            np.sin(lats.shift(1).fillna(lats[0])) * np.cos(lats) * np.cos(np.diff(lons, prepend=lons[0]))
        headings = np.degrees(np.arctan2(y, x))
        headings = np.unwrap(headings, period=360)
        gps_yaw_rate = np.gradient(headings) * fs
        gps_yaw_rate = lowpass(gps_yaw_rate, 1.0, fs) # Smooth it
        
        # Find Segments where abs(yaw) < threshold
        is_straight = np.abs(gps_yaw_rate) < 3.0 # deg/s threshold
        
        # Filter for distance > 50m
        # We need contiguous blocks
        straight_mask = np.zeros_like(is_straight, dtype=bool)
        
        # Simple RLE approx
        current_run = []
        for i, val in enumerate(is_straight):
            if val:
                current_run.append(i)
            else:
                # Check distance of run
                if current_run:
                    dist = 0
                    for k in range(len(current_run)-1):
                        s_idx = current_run[k]
                        dist += speeds[s_idx] * (1.0/fs)
                    
                    if dist > 50.0:
                        straight_mask[current_run] = True
                current_run = []
        # Check last run
        if current_run:
             dist = sum([speeds[i]*(1.0/fs) for i in current_run])
             if dist > 50.0: straight_mask[current_run] = True
             
        # --- PHASE 2: Calibration from Straights ---
        # Collect Imus in Straights
        # Heuristic scaling first
        scale_a = 1/16384.0 if df['imu_z'].abs().mean() > 1000 else 1.0
        scale_g = 1/131.0 if df['gyro_x'].abs().max() > 100 else 1.0
        
        raw_ax = df['imu_x'].values * scale_a
        raw_ay = df['imu_y'].values * scale_a
        raw_az = df['imu_z'].values * scale_a
        raw_gx = df['gyro_x'].values * scale_g
        raw_gz = df['gyro_z'].values * scale_g # Yaw rate
        
        # Calculate Biases (Offsets)
        if np.sum(straight_mask) > 10:
            # Lateral Accel should be 0 on straights
            bias_ay = np.mean(raw_ay[straight_mask])
            
            # Gyro Rates should be 0 on straights
            bias_gx = np.mean(raw_gx[straight_mask])
            bias_gz = np.mean(raw_gz[straight_mask])
            
            # Longitudinal Accel Correlation
            # On straights: Ax_meas = GPS_Accel + Gravity_Pitch + Bias
            # Assume constant pitch bias?
            # Let's align Mean(Ax_meas) to Mean(GPS_Accel) during straights?
            gps_accel = np.gradient(speeds) * fs
            bias_ax = np.mean(raw_ax[straight_mask] - gps_accel[straight_mask])
            
        else:
            print("WARN: No straights detected >50m. Using default biases.")
            bias_ay = 0.0
            bias_gx = 0.0
            bias_gz = 0.0
            bias_ax = 0.0
            
        print(f"Biases Detected: Ay={bias_ay:.2f}, Ax={bias_ax:.2f}, Gx={bias_gx:.2f}")
        
        # Apply Corrections
        ax = raw_ax - bias_ax
        ay = raw_ay - bias_ay
        gx = raw_gx - bias_gx
        # Az? Assume 1g avg?
        
        # Apply Heavy Filter (User Requirement)
        ax = lowpass(ax, 0.5, fs)
        ay = lowpass(ay, 0.5, fs)
        gx = lowpass(gx, 1.0, fs)
        
        # --- PHASE 3: Processing with Constraints ---
        # Complementary Filter
        angles = []
        curr = 0.0
        dt = 1.0/fs
        
        for i in range(len(ax)):
            # Constraint: If Straight Mask is True, Force Decay to 0 Harder
            if straight_mask[i]:
                # We are in a straight
                # Force lean to 0?
                # Interpolate to 0
                curr = curr * 0.8 # Fast decay
            else:
                # Normal integration
                curr = curr * 0.99 + gx[i] * dt
                
            # Clamp
            curr = max(-60, min(60, curr))
            angles.append(curr)
            
        # Physics Check on Ax
        # "Force no braking if accelerating"
        # GPS Trend
        gps_trend = np.gradient(speeds)
        
        final_ax = []
        for i in range(len(ax)):
            val = ax[i]
            # Logic: If GPS accel > 0.5 m/s^2 (clearly accel), Ax must be >= 0
            if gps_trend[i] > 0.5:
                if val < 0: val = 0.0 # Clamp negative drag spikes
            # If GPS accel < -0.5 (braking), Ax must be <= 0
            if gps_trend[i] < -0.5:
                if val > 0: val = 0.0
            
            final_ax.append(val)
            
        final_ax = lowpass(np.array(final_ax), 1.0, fs)
        
        return {
            "lean": lowpass(np.array(angles), 1.0, fs),
            "ax": final_ax,
            "ay": ay, # ay is corrected for bias but not clamped to 0 on straights in final output? User said "normalize". Bias removal is good.
            "az": raw_az 
        }

# --- Main Test Runner ---

def run_suite(file_path):
    print(f"Loading {file_path}...")
    df = load_data(file_path)
    
    # Estimate FS
    ts = df['timestamp'].values
    fs = 1.0 / np.median(np.diff(ts))
    print(f"Data FS: {fs:.1f} Hz")
    
    algos = {
        "Complementary_Old": Algo_Complementary(),
        "TwoPhase_Calib": Algo_TwoPhase_Calibration()
    }
    
    best_score = -999
    best_algo = None
    
    for name, algo in algos.items():
        print(f"\n--- Testing {name} ---")
        try:
            res = algo.process(df, fs)
            score, report = validate(res, df['speed'], fs)
            
            print(f"Score: {score}/100")
            for r in report: print(f"  {r}")
            
            if score > best_score:
                best_score = score
                best_algo = name
                
            # Valid or not, save for inspection
            out_file = save_result(df, res, name)
            print(f"Saved: {out_file}")
            
        except Exception as e:
            print(f"CRITICAL FAIL: {e}")
            import traceback
            traceback.print_exc()

    print(f"\nWinner: {best_algo} ({best_score})")

if __name__ == "__main__":
    import sys
    f = sys.argv[1] if len(sys.argv)>1 else "output/learning/testCoastt.csv"
    run_suite(f)
