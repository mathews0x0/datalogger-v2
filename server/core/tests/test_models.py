import unittest
from datetime import datetime
from src.analysis.core.models import Sample, GPSSample, IMUSample, EnvSample, Session

class TestAnalysisModels(unittest.TestCase):
    
    def test_sample_creation(self):
        """Test that a Sample can be created with component parts."""
        gps = GPSSample(lat=12.34, lon=56.78, speed=10.5, sats=8)
        imu = IMUSample(accel_x=0.1, accel_y=0.2, accel_z=9.8)
        env = EnvSample(temp=25.0, pressure=1013.2)
        
        sample = Sample(timestamp=1000.0, gps=gps, imu=imu, env=env)
        
        self.assertEqual(sample.timestamp, 1000.0)
        self.assertEqual(sample.gps.lat, 12.34)
        self.assertEqual(sample.imu.accel_z, 9.8)

    def test_session_management(self):
        """Test adding samples to a Session."""
        session = Session(description="Test Ride")
        
        # Add 3 samples
        for i in range(3):
            s = Sample(
                timestamp=1000.0 + i,
                gps=GPSSample(0,0,0,0),
                imu=IMUSample(0,0,0),
                env=EnvSample(0,0)
            )
            session.add_sample(s)
            
        self.assertEqual(len(session), 3)
        self.assertEqual(session.duration, 2.0) # 1002 - 1000
        self.assertEqual(session.start_time, 1000.0)
        self.assertEqual(session.end_time, 1002.0)

    def test_session_slicing(self):
        """Test slicing a session by time."""
        session = Session()
        # Add samples at t=10, 20, 30, 40
        times = [10, 20, 30, 40]
        for t in times:
            session.add_sample(Sample(t, GPSSample(0,0,0,0), IMUSample(0,0,0), EnvSample(0,0)))
            
        # Slice from 15 to 35 (Should include 20 and 30)
        sliced = session.slice(15, 35)
        
        self.assertEqual(len(sliced), 2)
        self.assertEqual(sliced.samples[0].timestamp, 20)
        self.assertEqual(sliced.samples[1].timestamp, 30)

if __name__ == '__main__':
    unittest.main()
