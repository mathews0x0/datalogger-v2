import argparse
import sys
import os

# Add project root to sys.path to allow 'from src...' imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.analysis.ingestion.csv_loader import CSVLoader
from src.analysis.processing.laps import LapDetector, StartLine
from src.analysis.core.track_manager import TrackManager
from src.analysis.processing.stats import StatsEngine
from src.analysis.processing.comparator import Comparator
import src.config as config

def main():
    parser = argparse.ArgumentParser(description="Analyze Motorcycle Telemetry Log")
    parser.add_argument("file", help="Path to input CSV file")
    parser.add_argument("--lat", type=float, help="Start Line Latitude")
    parser.add_argument("--lon", type=float, help="Start Line Longitude")
    parser.add_argument("--radius", type=float, default=None, help="Detection Radius (meters)")
    
    args = parser.parse_args()
    
    # Delegate to SessionProcessor
    from src.analysis.core.session_processor import SessionProcessor
    
    print("-" * 50)
    print(" Datalogger Analysis Pipeline (Phase 5)")
    print("-" * 50)
    
    processor = SessionProcessor()
    # We can pass specific override ID if --track is added to args (future)
    # For now, just pass the file.
    
    success = processor.process_session(args.file)
    
    if success:
        print("-" * 50)
        print(" Processing Complete.")
    else:
        print(" Processing Failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
