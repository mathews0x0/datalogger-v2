import unittest
from src.analysis.core.track_manager import TrackManager
from src.analysis.core.models import Session, Sample, GPSSample, IMUSample, EnvSample

class TestTrackManager(unittest.TestCase):
    def setUp(self):
        # Initialize manager (will load tracks.json)
        self.manager = TrackManager()

    def create_dummy_session(self, lat, lon):
        session = Session()
        # Add a sample near the target coordinates
        session.add_sample(Sample(
            timestamp=1000.0,
            gps=GPSSample(lat, lon, 0, 0),
            imu=IMUSample(0,0,0),
            env=EnvSample(0,0)
        ))
        return session

    def test_identify_kari(self):
        """Test identification of Kari Motor Speedway."""
        # Point exactly at Kari start line
        session = self.create_dummy_session(10.92650, 77.06200)
        
        track = self.manager.identify_track(session)
        self.assertIsNotNone(track)
        self.assertEqual(track['id'], "kari_motor_speedway")

    def test_unknown_track(self):
        """Test identification of an unknown location."""
        # Random point in Antarctica
        session = self.create_dummy_session(-80.0, 0.0)
        
        track = self.manager.identify_track(session)
        self.assertIsNone(track)

if __name__ == '__main__':
    unittest.main()
