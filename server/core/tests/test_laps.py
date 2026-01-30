import unittest
from src.analysis.core.models import Session, Sample, GPSSample, IMUSample, EnvSample
from src.analysis.processing.laps import LapDetector, StartLine

class TestLapDetection(unittest.TestCase):
    
    def setUp(self):
        # Define a Start Line at (0, 0) with 10m radius
        self.start_line = StartLine(lat=0.0, lon=0.0, radius_m=10.0)
        self.detector = LapDetector(self.start_line)

    def create_dummy_sample(self, time, lat, lon):
        return Sample(
            timestamp=time,
            gps=GPSSample(lat, lon, 50.0, 8),
            imu=IMUSample(0,0,0),
            env=EnvSample(0,0)
        )

    def test_single_lap_detection(self):
        """
        Simulate a bike leaving the line, going around, and returning.
        """
        session = Session()
        
        # 1. Start at line (t=0)
        session.add_sample(self.create_dummy_sample(1000, 0.0, 0.0))
        
        # 2. Driving away (t=10 to 50) - 1 degree (~111km) away
        for i in range(1, 6):
            session.add_sample(self.create_dummy_sample(1000 + i*10, 0.1 * i, 0.0))
            
        # 3. Returning (t=60 to 100)
        for i in range(5, -1, -1):
            session.add_sample(self.create_dummy_sample(1060 + (5-i)*10, 0.1 * i, 0.0))
            
        # Total time: ~120s
        # Should detect:
        # Lap 1: Start at t=1000, End at t=~1110 (when it crosses back)
        
        laps = self.detector.detect(session)
        
        # We expect at least 1 closed lap
        self.assertTrue(len(laps) >= 1)
        self.assertAlmostEqual(laps[0].duration, 110.0, delta=10.0)

if __name__ == '__main__':
    unittest.main()
