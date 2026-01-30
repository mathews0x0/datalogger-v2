import argparse
import json
import os
import sys
# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.analysis.ingestion.csv_loader import CSVLoader
from src.analysis.processing.laps import LapDetector, StartLine
from src.analysis.processing.geo import haversine_distance
import src.config as config

def calculate_cumulative_distances(lap):
    """
    Returns a list of cumulative distances in meters for every sample in the lap.
    """
    dists = [0.0]
    total = 0.0
    for i in range(1, len(lap.samples)):
        s1 = lap.samples[i-1]
        s2 = lap.samples[i]
        d = haversine_distance(s1.gps.lat, s1.gps.lon, s2.gps.lat, s2.gps.lon) * 1000.0 # to meters
        total += d
        dists.append(total)
    return dists

def find_point_at_distance(samples, dists, target_dist):
    """
    Find the sample closest to the target cumulative distance.
    """
    # Simple search (could be binary search for optimization)
    closest_idx = 0
    min_diff = float('inf')
    
    for i, d in enumerate(dists):
        diff = abs(d - target_dist)
        if diff < min_diff:
            min_diff = diff
            closest_idx = i
            
    return samples[closest_idx]

def main():
    parser = argparse.ArgumentParser(description="Generate Track JSON from Learning Data")
    parser.add_argument("file", help="Path to learning CSV file (e.g. src/learning/Fri/123456.csv)")
    parser.add_argument("name", help="Name of the Track (e.g. 'Kari Motor Speedway')")
    parser.add_argument("id", help="Unique ID (e.g. 'kari')")
    parser.add_argument("--radius", type=float, default=20.0, help="Start Line Radius (m)")
    
    args = parser.parse_args()
    
    # 1. Load Data
    print(f"Loading {args.file}...")
    loader = CSVLoader()
    try:
        session = loader.load(args.file)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
        
    if not session.samples:
        print("Error: Session is empty")
        sys.exit(1)
        
    # 2. Identify Start Line (First Point)
    first_point = session.samples[0]
    start_lat = first_point.gps.lat
    start_lon = first_point.gps.lon
    
    print(f"Start Line derived from first point: {start_lat}, {start_lon}")
    
    # 3. Detect Laps (to find geometry)
    sl_obj = StartLine(start_lat, start_lon, args.radius)
    detector = LapDetector(sl_obj)
    laps = detector.detect(session)
    
    sectors = []
    
    if not laps:
        print("Warning: No laps detected in learning file. Cannot generate sectors.")
        print("Tip: Ensure you drove a complete loop and returned to the start point.")
    else:
        # Use the BEST LAP as the "Official Geometry" to ensure points are on the racing line.
        # The first lap is often an out-lap with stops or odd lines.
        ref_lap = min(laps, key=lambda l: l.duration)
        print(f"Using Lap {ref_lap.lap_number} ({ref_lap.duration:.1f}s) as Reference Geometry ({len(ref_lap.samples)} samples).")
        
        # Calculate Total Distance
        dists = calculate_cumulative_distances(ref_lap)
        total_dist = dists[-1]
        print(f"Reference Lap Length: {total_dist:.1f} meters")
        
        # Generate Split Points
        # Enforce Fixed Sector Count
        num_sectors = config.SECTOR_COUNT
        
        step = total_dist / num_sectors
        
        for i in range(1, num_sectors + 1):
            target_dist = step * i
            
            if i == num_sectors:
                # Last sector ends at Start Line
                s_lat = start_lat
                s_lon = start_lon
            else:
                target_sample = find_point_at_distance(ref_lap.samples, dists, target_dist)
                s_lat = target_sample.gps.lat
                s_lon = target_sample.gps.lon
                
            sectors.append({
                "id": f"S{i}",
                "end_lat": s_lat,
                "end_lon": s_lon,
                "radius_m": 50.0 # Increased for reliability with test data
            })
            print(f"  Sector {i} End: {target_dist:.1f}m ({s_lat:.5f}, {s_lon:.5f})")

    # 4. Construct Track Structure
    track_data = {
        "id": args.id,
        "name": args.name,
        "start_line": {
            "lat": start_lat,
            "lon": start_lon,
            "radius_m": args.radius,
            "heading": 0.0
        },
        "metadata": {
            "sector_strategy": "distance_equal_v1",
            "num_sectors": config.SECTOR_COUNT
        },
        "sectors": sectors,
        "records": {
            "best_real_lap": {"time": None, "session": None},
            "sector_bests": {} 
        },
        "location": "Unknown",
        "created_from": args.file
    }
    
    # Initialize sector bests
    for s in sectors:
        track_data["records"]["sector_bests"][s["id"]] = {"time": None, "session": None}
    
    # 5. Save to Tracks Directory
    os.makedirs(config.TRACKS_DIR, exist_ok=True)
    out_path = os.path.join(config.TRACKS_DIR, f"{args.id}.json")
    
    with open(out_path, 'w') as f:
        json.dump(track_data, f, indent=4)
        
    print(f"Track saved to: {out_path}")
    print("You can verify this track in specific analysis runs.")

if __name__ == "__main__":
    main()
