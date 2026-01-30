import csv
import math
import random
import time

# Kari Motor Speedway (Approximate Waypoints)
# Start/Finish Straight -> C1 -> ...
TRACK_POINTS = [
    (10.92650, 77.06200), # Start/Finish Line (Straight)
    (10.92500, 77.06200), # End of Straight (Braking for C1)
    (10.92480, 77.06220), # C1 Apex (Right)
    (10.92500, 77.06250), # C2 (Left)
    (10.92550, 77.06300), # Back Straight start
    (10.92600, 77.06300), # Back Straight end
    (10.92650, 77.06200)  # Loop back to Start
]

def interpolate_points(p1, p2, steps):
    points = []
    lat1, lon1 = p1
    lat2, lon2 = p2
    
    for i in range(steps):
        f = i / steps
        lat = lat1 + (lat2 - lat1) * f
        lon = lon1 + (lon2 - lon1) * f
        points.append((lat, lon))
    return points

def generate_track(filename="kari_simulation.csv", laps=3):
    print(f"Generating {laps} laps of Kari Motor Speedway...")
    
    # 10Hz Simulation
    hz = 10
    timestamp = 1700000000.0
    
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp","latitude","longitude","speed","satellites","imu_x","imu_y","imu_z","pressure","temp"])
        
        for lap in range(laps):
            for i in range(len(TRACK_POINTS) - 1):
                p1 = TRACK_POINTS[i]
                p2 = TRACK_POINTS[i+1]
                
                # Simulate speed: Fast on straights, slow in corners
                segment_len = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
                speed_kmh = 100.0 if segment_len > 0.001 else 40.0
                
                # Points in this segment
                steps = 50 # 5 seconds per segment roughly
                points = interpolate_points(p1, p2, steps)
                
                for pt in points:
                    # Add GPS Drift/Noise
                    lat = pt[0] + random.uniform(-0.00001, 0.00001)
                    lon = pt[1] + random.uniform(-0.00001, 0.00001)
                    
                    writer.writerow([
                        f"{timestamp:.2f}",
                        f"{lat:.6f}",
                        f"{lon:.6f}",
                        f"{speed_kmh + random.uniform(-1, 1):.1f}",
                        "10", # Sats
                        "0.1", "0.2", "9.8", # IMU
                        "1013.2", "30.5"
                    ])
                    timestamp += (1.0 / hz)
                    
    print(f"Saved to {filename}")

if __name__ == "__main__":
    generate_track("src/analysis/tests/kari_simulation.csv")
