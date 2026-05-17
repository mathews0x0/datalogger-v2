import unittest
import tempfile
import os
import json
from src.analysis.processing.stats import StatsEngine
from src.analysis.core.models import Lap, Session, Sample, GPSSample, IMUSample, EnvSample
from core.core.tbl_manager import TBLManager

class TestStats(unittest.TestCase):
    def create_lap(self, duration):
        session = Session()
        # Start
        session.add_sample(Sample(1000.0, GPSSample(0,0,0,0), IMUSample(0,0,0), EnvSample(0,0)))
        # End
        session.add_sample(Sample(1000.0 + duration, GPSSample(0,0,0,0), IMUSample(0,0,0), EnvSample(0,0)))
        
        return Lap(session, 0, 2, number=1)

    def test_best_lap(self):
        l1 = self.create_lap(100.0)
        l2 = self.create_lap(98.5) # Best
        l3 = self.create_lap(99.0)
        
        best = StatsEngine.find_best_lap([l1, l2, l3])
        self.assertEqual(best, l2)
        self.assertEqual(best.duration, 98.5)

    def test_lap_duration_uses_boundary_crossing_sample(self):
        session = Session()
        session.add_sample(Sample(100.0, GPSSample(0, 0, 0, 0), IMUSample(0, 0, 0), EnvSample(0, 0)))
        session.add_sample(Sample(109.5, GPSSample(0, 0, 0, 0), IMUSample(0, 0, 0), EnvSample(0, 0)))
        session.add_sample(Sample(110.0, GPSSample(0, 0, 0, 0), IMUSample(0, 0, 0), EnvSample(0, 0)))

        lap = Lap(session, 0, 2, number=1)

        self.assertEqual(len(lap.samples), 2)
        self.assertEqual(lap.start_time, 100.0)
        self.assertEqual(lap.end_time, 110.0)
        self.assertEqual(lap.duration, 10.0)

    def test_sectors(self):
        # 1. Define Track Info
        track_info = {
            "sectors": [
                {"id": "s1", "end_lat": 0.1, "end_lon": 0.0, "radius_m": 500.0},
                {"id": "s2", "end_lat": 0.2, "end_lon": 0.0, "radius_m": 500.0}
            ]
        }
        
        # 2. Create Lap Samples
        # Use large lat steps to be "far" then "close"
        # 0.1 lat is ~11km, so radius needs to be big or points close.
        # Let's use small lat steps. 0.0001 ~ 11m.
        # Sector 1 end: 0.0001, Sector 2 end: 0.0002
        
        track_info["sectors"][0]["end_lat"] = 0.0001
        track_info["sectors"][1]["end_lat"] = 0.0002
        track_info["sectors"][0]["radius_m"] = 20.0
        track_info["sectors"][1]["radius_m"] = 20.0

        session = Session()
        # t=0, lat=0 (Start)
        session.add_sample(Sample(100.0, GPSSample(0,0,0,0), IMUSample(0,0,0), EnvSample(0,0)))
        # t=10, lat=0.0001 (Cross S1)
        session.add_sample(Sample(110.0, GPSSample(0.0001,0,0,0), IMUSample(0,0,0), EnvSample(0,0)))
        # t=25, lat=0.0002 (Cross S2)
        session.add_sample(Sample(125.0, GPSSample(0.0002,0,0,0), IMUSample(0,0,0), EnvSample(0,0)))
        
        laps = [Lap(session, 0, 3, number=1)]
        
        # 3. Calculate
        StatsEngine.calculate_sectors(laps, track_info)
        
        # 4. Verify
        # S1: 110.0 - 100.0 = 10.0s
        # S2: 125.0 - 110.0 = 15.0s
        self.assertEqual(laps[0].sector_times["s1"], 10.0)
        self.assertEqual(laps[0].sector_times["s2"], 15.0)

    def test_canonical_sector_indices_normalize_to_standard_keys(self):
        track_info = {
            "sectors": [
                {"id": "gate_alpha", "sector_index": 1, "end_lat": 0.0001, "end_lon": 0.0, "radius_m": 20.0},
                {"id": "gate_beta", "sector_index": 2, "end_lat": 0.0002, "end_lon": 0.0, "radius_m": 20.0}
            ]
        }

        session = Session()
        session.add_sample(Sample(100.0, GPSSample(0, 0, 0, 0), IMUSample(0, 0, 0), EnvSample(0, 0)))
        session.add_sample(Sample(110.0, GPSSample(0.0001, 0, 0, 0), IMUSample(0, 0, 0), EnvSample(0, 0)))
        session.add_sample(Sample(125.0, GPSSample(0.0002, 0, 0, 0), IMUSample(0, 0, 0), EnvSample(0, 0)))

        laps = [Lap(session, 0, 3, number=1)]
        StatsEngine.calculate_sectors(laps, track_info)

        self.assertEqual(laps[0].sector_times["S1"], 10.0)
        self.assertEqual(laps[0].sector_times["S2"], 15.0)

    def test_progress_based_sector_detection_uses_centerline_progress(self):
        track_info = {
            "start_line": {"lat": 0.0, "lon": 0.0, "radius_m": 20.0},
            "centerline": [
                {"lat": 0.0, "lon": 0.0},
                {"lat": 0.0001, "lon": 0.0},
                {"lat": 0.0002, "lon": 0.0},
                {"lat": 0.0003, "lon": 0.0},
            ],
            "sectors": [
                {"id": "S1", "sector_index": 1, "end_lat": 1.0, "end_lon": 1.0, "radius_m": 1.0, "progress_m": 11.1},
                {"id": "S2", "sector_index": 2, "end_lat": 1.0, "end_lon": 1.0, "radius_m": 1.0, "progress_m": 22.2},
                {"id": "S3", "sector_index": 3, "end_lat": 1.0, "end_lon": 1.0, "radius_m": 1.0, "progress_m": 33.3},
            ],
        }

        session = Session()
        session.add_sample(Sample(100.0, GPSSample(0.0, 0.0, 0, 0), IMUSample(0, 0, 0), EnvSample(0, 0)))
        session.add_sample(Sample(110.0, GPSSample(0.0001, 0.0, 0, 0), IMUSample(0, 0, 0), EnvSample(0, 0)))
        session.add_sample(Sample(120.0, GPSSample(0.0002, 0.0, 0, 0), IMUSample(0, 0, 0), EnvSample(0, 0)))
        session.add_sample(Sample(130.0, GPSSample(0.0003, 0.0, 0, 0), IMUSample(0, 0, 0), EnvSample(0, 0)))

        laps = [Lap(session, 0, 4, number=1)]
        StatsEngine.calculate_sectors(laps, track_info)

        self.assertEqual(laps[0].sector_times["S1"], 10.0)
        self.assertEqual(laps[0].sector_times["S2"], 10.0)
        self.assertEqual(laps[0].sector_times["S3"], 10.0)

    def test_tbl_manager_uses_local_tracks_registry(self):
        with tempfile.TemporaryDirectory() as tracks_dir:
            with open(os.path.join(tracks_dir, "registry.json"), "w") as f:
                json.dump({
                    "next_id": 1000002,
                    "tracks": [
                        {
                            "track_id": 1000001,
                            "track_name": "Global Mirror",
                            "folder_name": "global_track_1000001"
                        }
                    ]
                }, f)

            mgr = TBLManager(tracks_dir=tracks_dir)
            path = mgr._get_tbl_path(1000001)
            self.assertTrue(path.endswith(os.path.join("global_track_1000001", "tbl.json")))

    def test_tbl_total_best_requires_all_sectors(self):
        with tempfile.TemporaryDirectory() as tracks_dir:
            with open(os.path.join(tracks_dir, "registry.json"), "w") as f:
                json.dump({
                    "next_id": 2,
                    "tracks": [
                        {
                            "track_id": 1,
                            "track_name": "Partial Track",
                            "folder_name": "track_1"
                        }
                    ]
                }, f)

            os.makedirs(os.path.join(tracks_dir, "track_1"), exist_ok=True)
            mgr = TBLManager(tracks_dir=tracks_dir)

            session = Session(description="session-a")
            lap = self.create_lap(130.0)
            lap.sector_times = {"S1": 19.5}
            session.laps = [lap]

            updated = mgr.update_from_session(session, {
                "track_id": 1,
                "track_name": "Partial Track",
                "sectors": [{"sector_index": i + 1} for i in range(7)],
            })
            self.assertTrue(updated)

            tbl = mgr.load_tbl(1)
            self.assertEqual(len(tbl["sectors"]), 1)
            self.assertIsNone(tbl["total_best_time"])

if __name__ == '__main__':
    unittest.main()
