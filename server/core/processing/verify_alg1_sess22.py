import os
import sys

# Add server directory to path to allow importing from src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.analysis.ingestion.csv_loader import CSVLoader
from src.analysis.processing.advanced_imu import AdvancedIMUProcessor

def verify_alg1():
    print("Testing Algorithm 1 Integration")
    file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'Session backup', 'infopark led.csv'))
    
    loader = CSVLoader()
    try:
        session = loader.load(file_path)
    except Exception as e:
        print(f"Failed to load CSV: {e}")
        return

    print(f"Loaded {len(session.samples)} samples")

    timestamps = [s.timestamp for s in session.samples]
    ax_raw = [s.imu.accel_x for s in session.samples]
    ay_raw = [s.imu.accel_y for s in session.samples]
    az_raw = [s.imu.accel_z for s in session.samples]
    gx_raw = [s.imu.gyro_x if s.imu.gyro_x else 0.0 for s in session.samples]
    gy_raw = [s.imu.gyro_y if s.imu.gyro_y else 0.0 for s in session.samples]
    gz_raw = [s.imu.gyro_z if s.imu.gyro_z else 0.0 for s in session.samples]
    lats = [s.gps.lat for s in session.samples]
    lons = [s.gps.lon for s in session.samples]
    speeds = [s.gps.speed for s in session.samples]

    imu_proc = AdvancedIMUProcessor()
    
    try:
        results = imu_proc.process(timestamps, ax_raw, ay_raw, az_raw, gx_raw, gy_raw, gz_raw, speeds, lats, lons)
    except Exception as e:
        print(f"Algorithm 1 processing failed: {e}")
        import traceback
        traceback.print_exc()
        return

    print("--- Algorithm 1 Peak Results ---")
    
    def get_peaks(data, n=5, reverse=True):
        sorted_idx = sorted(range(len(data)), key=lambda i: data[i], reverse=reverse)
        peaks = []
        for i in sorted_idx:
            # simple distance check based on index (assuming 100hz -> 1sec = 100 samples)
            if all(abs(i - p) > 300 for p in peaks): 
                peaks.append(i)
                if len(peaks) == n: break
        return peaks

    print("\nTOP LEAN ANGLES:")
    top_lean = get_peaks(results["lean_angle"], 5, reverse=True)
    for i in top_lean:
        print(f"Lean: {results['lean_angle'][i]:.1f}° | Speed: {speeds[i]:.1f}km/h | GPS: {lats[i]:.6f}, {lons[i]:.6f}")
        
    print("\nHARD ACCEL:")
    top_accel = get_peaks(results["acceleration_g"], 3, reverse=True)
    for i in top_accel:
         print(f"Accel: {results['acceleration_g'][i]:.2f}g | Speed: {speeds[i]:.1f}km/h | GPS: {lats[i]:.6f}, {lons[i]:.6f}")

    print("\nHARD BRAKING:")
    top_brake = get_peaks(results["braking_g"], 3, reverse=True)
    for i in top_brake:
         print(f"Braking: {results['braking_g'][i]:.2f}g | Speed: {speeds[i]:.1f}km/h | GPS: {lats[i]:.6f}, {lons[i]:.6f}")

if __name__ == "__main__":
    verify_alg1()

