import matplotlib.pyplot as plt
import os
from typing import List, Dict
from src.analysis.processing.geo import haversine_distance

class TrackVisualizer:
    @staticmethod
    def generate_track_map(lats: List[float], lons: List[float], track_data: Dict, output_path: str):
        """
        Generates a static map of the track with annotations.
        """
        try:
            plt.figure(figsize=(12, 10))
            
            # Close the loop for visualization if not closed
            if lats and lons:
                if haversine_distance(lats[0], lons[0], lats[-1], lons[-1]) * 1000 > 5:
                    lats.append(lats[0])
                    lons.append(lons[0])
            
            # Plot Main Track Path
            plt.plot(lons, lats, 'k-', linewidth=2, label='Track Geometry', alpha=0.7)
            
            # Annotate Start/Finish
            sl = track_data.get("start_line", {})
            if sl:
                plt.plot(sl['lon'], sl['lat'], 'g*', markersize=18, label='Start/Finish', zorder=10)
            
            # Annotate Sectors
            sectors = track_data.get("sectors", [])
            colors = ['r', 'b', 'm', 'c', 'y']
            
            num_sectors = len(sectors)
            for i, sec in enumerate(sectors):
                # Sector End Point
                s_lat = sec.get("end_lat")
                s_lon = sec.get("end_lon")
                s_id = sec.get("id", f"S{i+1}")
                
                
                if s_lat and s_lon:
                    # Alternating colors
                    c = colors[i % len(colors)]
                    plt.plot(s_lon, s_lat, marker='|', color=c, markersize=14, markeredgewidth=3)
                    plt.text(s_lon, s_lat, f" {s_id}", fontsize=12, fontweight='bold', color=c)
            
            plt.title(f"Track Map: {track_data.get('name', 'Unknown')}", fontsize=14)
            plt.xlabel("Longitude")
            plt.ylabel("Latitude")
            plt.legend()
            plt.grid(True, linestyle='--', alpha=0.5)
            plt.axis('equal')
            
            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            plt.close()
            print(f"[TrackVisualizer] Saved map to {output_path}")
            return True
            
        except Exception as e:
            print(f"[TrackVisualizer] Visualization failed: {e}")
            return False
