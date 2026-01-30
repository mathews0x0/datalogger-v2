import unittest
import io
from src.analysis.ingestion.csv_loader import CSVLoader
from src.analysis.core.models import Session

class TestCSVLoader(unittest.TestCase):
    def test_load_valid_csv(self):
        """Test loading a standard CSV string."""
        csv_data = """timestamp,latitude,longitude,speed,satellites,imu_x,imu_y,imu_z,pressure
1700000001.0,12.34,56.78,10.0,8,0.1,0.2,9.8,1013.2
1700000002.0,12.35,56.79,12.0,9,0.0,0.1,9.7,1013.1
"""
        # Simulate file
        f = io.StringIO(csv_data)
        
        loader = CSVLoader()
        session = loader.load(f, source_name="test_log.csv")
        
        self.assertIsInstance(session, Session)
        self.assertEqual(len(session), 2)
        self.assertEqual(session.description, "test_log.csv")
        
        s1 = session.samples[0]
        self.assertEqual(s1.timestamp, 1700000001.0)
        self.assertEqual(s1.gps.lat, 12.34)
        self.assertEqual(s1.imu.accel_z, 9.8)
        self.assertEqual(s1.env.pressure, 1013.2)
        # Temp should be default 0.0 since not in CSV
        self.assertEqual(s1.env.temp, 0.0)

    def test_handle_empty_values(self):
        """Test CSV with missing values (e.g. no GPS fix)."""
        csv_data = """timestamp,latitude,longitude,speed,satellites,imu_x,imu_y,imu_z,pressure
1700000003.0,,,0.0,0,0.1,0.2,9.8,1013.2
"""
        f = io.StringIO(csv_data)
        session = CSVLoader().load(f)
        
        s1 = session.samples[0]
        self.assertEqual(s1.timestamp, 1700000003.0)
        self.assertEqual(s1.gps.lat, 0.0) # Should default to 0.0
        self.assertEqual(s1.gps.sats, 0)

if __name__ == '__main__':
    unittest.main()
