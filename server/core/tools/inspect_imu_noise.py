import sys
import pandas as pd
import numpy as np

def inspect(file_path):
    try:
        df = pd.read_csv(file_path)
        print(f"Loaded {len(df)} samples from {file_path}")
        
        # Check IMU columns
        imu_cols = ['imu_x', 'imu_y', 'imu_z', 'gyro_x', 'gyro_y', 'gyro_z']
        for col in imu_cols:
            if col not in df.columns:
                print(f"Missing column: {col}")
                continue
                
            data = df[col].dropna()
            if len(data) == 0:
                print(f"{col}: All NaN")
                continue
                
            # Stats
            avg = np.mean(data)
            std = np.std(data)
            min_v = np.min(data)
            max_v = np.max(data)
            
            print(f"-- {col} --")
            print(f"  Mean: {avg:.2f}")
            print(f"  StdDev: {std:.2f}")
            print(f"  Range: [{min_v}, {max_v}]")
            
            # Derivative (Jerk/Noise)
            diff = np.diff(data)
            avg_jerk = np.mean(np.abs(diff))
            max_jerk = np.max(np.abs(diff))
            print(f"  Avg Step Change: {avg_jerk:.2f}")
            print(f"  Max Step Change: {max_jerk:.2f}")
            
            # Vibration Metric (Zero Crossings of derivative? Or high freq energy?)
            # Simple check: How often does it flip sign relative to mean?
            # centered = data - avg
            # flips = np.sum(np.diff(np.sign(centered)) != 0)
            # print(f"  Sign Flips: {flips} ({flips/len(data)*100:.1f}%)")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python inspect_imu_noise.py <csv_file>")
    else:
        inspect(sys.argv[1])
