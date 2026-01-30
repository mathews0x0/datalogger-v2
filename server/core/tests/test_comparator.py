import unittest
from src.analysis.processing.comparator import Comparator
from src.analysis.core.models import Lap, Session, Sample, GPSSample, IMUSample, EnvSample

class TestComparator(unittest.TestCase):
    def create_lap(self, speed_kmh):
        """Creates a straight-line lap at constant speed."""
        session = Session()
        # 0m, t=0
        session.add_sample(Sample(100.0, GPSSample(0,0,speed_kmh,0), IMUSample(0,0,0), EnvSample(0,0)))
        
        # 20m later.
        # Speed v (km/h) = v/3.6 (m/s).
        # Time = Dist / Speed.
        speed_ms = speed_kmh / 3.6
        duration = 20.0 / speed_ms
        
        # 20m approx 0.00018 deg lat
        session.add_sample(Sample(100.0 + duration, GPSSample(0.00018,0,speed_kmh,0), IMUSample(0,0,0), EnvSample(0,0)))
        
        return Lap(session, 0, 2, number=1)

    def test_compare_fast_vs_slow(self):
        # Reference: 36 km/h (10 m/s). 20m takes 2.0s.
        ref = self.create_lap(36.0)
        
        # Target: 72 km/h (20 m/s). 20m takes 1.0s.
        target = self.create_lap(72.0)
        
        comp = Comparator(step_meters=10.0)
        result = comp.compare(ref, target)
        
        # Expect points at 0, 10, 20 (Length 3)
        self.assertEqual(len(result["distance"]), 3)
        
        # Check Deltas at 20m mark (Index 2)
        # Speed Delta: 72 - 36 = +36 km/h
        self.assertAlmostEqual(result["delta_speed"][2], 36.0, delta=1.0)
        
        # Time Delta: Target (1.0s) - Ref (2.0s) = -1.0s (Faster)
        self.assertAlmostEqual(result["delta_time"][2], -1.0, delta=0.1)

if __name__ == '__main__':
    unittest.main()
