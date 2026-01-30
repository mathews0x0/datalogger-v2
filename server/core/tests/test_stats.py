import unittest
from src.analysis.processing.stats import StatsEngine
from src.analysis.core.models import Lap, Session, Sample, GPSSample, IMUSample, EnvSample

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

if __name__ == '__main__':
    unittest.main()
