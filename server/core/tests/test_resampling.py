import unittest
from src.analysis.processing.resampling import Resampler
from src.analysis.core.models import Session, Sample, GPSSample, IMUSample, EnvSample

class TestResampling(unittest.TestCase):
    
    def create_linear_session(self):
        """
        Creates a session moving North at constant speed.
        1 degree lat approx 111km.
        Let's do smaller steps: 0.00009 degrees is approx 10 meters.
        """
        session = Session()
        
        # Point A: 0, 0
        s1 = Sample(1000.0, GPSSample(0.0, 0.0, 36.0, 8), IMUSample(0,0,0), EnvSample(0,0))
        # Point B: 0.00018, 0 (Approx 20 meters North) - Time 1002.0 (Speed 10m/s = 36kmh)
        s2 = Sample(1002.0, GPSSample(0.00018, 0.0, 36.0, 8), IMUSample(0,0,0), EnvSample(0,0))
        
        session.add_sample(s1)
        session.add_sample(s2)
        return session

    def test_resample_10m(self):
        """Test resampling a 20m segment into 10m chunks."""
        session = self.create_linear_session() # 0m -> 20m
        
        resampler = Resampler(step_meters=10.0)
        new_samples = resampler.resample_session(session)
        
        # Expect 3 samples: 0m, 10m, 20m
        self.assertEqual(len(new_samples), 3)
        
        # Check timestamps
        # 0m = 1000s
        # 20m = 1002s
        # 10m should be 1001s
        self.assertAlmostEqual(new_samples[0].timestamp, 1000.0)
        self.assertAlmostEqual(new_samples[1].timestamp, 1001.0, delta=0.1)
        self.assertAlmostEqual(new_samples[2].timestamp, 1002.0)

    def test_empty_session(self):
        session = Session()
        resampler = Resampler(10.0)
        self.assertEqual(len(resampler.resample_session(session)), 0)

if __name__ == '__main__':
    unittest.main()
