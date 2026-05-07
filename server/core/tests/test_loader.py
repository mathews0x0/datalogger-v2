import unittest
import io
from src.analysis.ingestion.csv_loader import CSVLoader

class TestCSVLoader(unittest.TestCase):
    def test_rejects_csv_without_row_type(self):
        """Old all-fields-per-row CSVs are no longer supported."""
        csv_data = """timestamp,latitude,longitude,speed,satellites,imu_x,imu_y,imu_z,pressure
1700000001.0,12.34,56.78,10.0,8,0.1,0.2,9.8,1013.2
1700000002.0,12.35,56.79,12.0,9,0.0,0.1,9.7,1013.1
"""
        f = io.StringIO(csv_data)

        with self.assertRaisesRegex(ValueError, "row_type"):
            CSVLoader().load(f, source_name="old_log.csv")

    def test_fixed_100hz_csv_basic(self):
        """Test loading a fixed telemetry CSV with I and G rows."""
        csv_data = """tick_ms,row_type,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,lat,lon,alt,speed,sats,vbat
1000,I,0.10,0.20,1.00,1.0,2.0,3.0,,,,,,
1010,I,0.11,0.21,1.01,1.1,2.1,3.1,,,,,,
1020,I,0.12,0.22,1.02,1.2,2.2,3.2,,,,,,
1030,I,0.13,0.23,1.03,1.3,2.3,3.3,,,,,,
1040,I,0.14,0.24,1.04,1.4,2.4,3.4,,,,,,
1050,I,0.15,0.25,1.05,1.5,2.5,3.5,,,,,,
1060,I,0.16,0.26,1.06,1.6,2.6,3.6,,,,,,
1070,I,0.17,0.27,1.07,1.7,2.7,3.7,,,,,,
1080,I,0.18,0.28,1.08,1.8,2.8,3.8,,,,,,
1090,I,0.19,0.29,1.09,1.9,2.9,3.9,,,,,,
1100,G,0.20,0.30,1.10,2.0,3.0,4.0,12.0000,77.0000,920.0,80.0,8,3.80
1110,I,0.21,0.31,1.11,2.1,3.1,4.1,,,,,,
1120,I,0.22,0.32,1.12,2.2,3.2,4.2,,,,,,
1200,G,0.30,0.40,1.20,3.0,4.0,5.0,12.0010,77.0010,921.0,82.0,9,3.79
"""
        f = io.StringIO(csv_data)
        loader = CSVLoader()
        session = loader.load(f, source_name="fixed_100hz_test.csv")
        
        # Should have 14 samples total (12 I rows + 2 G rows)
        self.assertEqual(len(session), 14)
        
        # First sample: tick_ms=1000 → timestamp = 0.0s
        s0 = session.samples[0]
        self.assertAlmostEqual(s0.timestamp, 0.0)
        self.assertAlmostEqual(s0.imu.accel_x, 0.10)
        
        # Sample at GPS row (tick_ms=1100 → ts=0.1s)
        # G row at index 10 (9 I rows before it + the G row itself)
        s_gps = session.samples[10]
        self.assertAlmostEqual(s_gps.timestamp, 0.1)
        self.assertAlmostEqual(s_gps.gps.lat, 12.0000)
        self.assertAlmostEqual(s_gps.gps.speed, 80.0)
    
    def test_fixed_100hz_gps_interpolation(self):
        """Test that GPS data is linearly interpolated between fixes."""
        csv_data = """tick_ms,row_type,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,lat,lon,alt,speed,sats,vbat
1000,G,0.10,0.20,1.00,1.0,2.0,3.0,10.0000,20.0000,100.0,50.0,8,3.80
1050,I,0.15,0.25,1.05,1.5,2.5,3.5,,,,,,
1100,G,0.20,0.30,1.10,2.0,3.0,4.0,10.0010,20.0010,110.0,60.0,10,3.79
"""
        f = io.StringIO(csv_data)
        session = CSVLoader().load(f)
        
        # 3 samples: G at 1000, I at 1050, G at 1100
        self.assertEqual(len(session), 3)
        
        # Middle sample (tick_ms=1050) should have GPS interpolated halfway
        s_mid = session.samples[1]
        self.assertAlmostEqual(s_mid.gps.lat, 10.0005, places=4)
        self.assertAlmostEqual(s_mid.gps.lon, 20.0005, places=4)
        self.assertAlmostEqual(s_mid.gps.speed, 55.0, places=1)  # Midpoint of 50 and 60

    def test_fixed_100hz_no_gps_rows(self):
        """Test fixed telemetry CSV with only IMU rows (no GPS fix yet)."""
        csv_data = """tick_ms,row_type,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,lat,lon,alt,speed,sats,vbat
1000,I,0.10,0.20,1.00,1.0,2.0,3.0,,,,,,
1010,I,0.11,0.21,1.01,1.1,2.1,3.1,,,,,,
"""
        f = io.StringIO(csv_data)
        session = CSVLoader().load(f)
        
        self.assertEqual(len(session), 2)
        # GPS should be all zeros when no GPS rows exist
        self.assertAlmostEqual(session.samples[0].gps.lat, 0.0)
        self.assertAlmostEqual(session.samples[0].gps.lon, 0.0)

    def test_fixed_100hz_marker_metadata(self):
        csv_data = """tick_ms,row_type,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,lat,lon,alt,speed,sats,vbat,gps_epoch
1000,M,,,,,,,MARKER,IMU_PROFILE,1,"{""id"": ""tank"", ""label"": ""tank"", ""rotation_matrix"": [[1,0,0],[0,1,0],[0,0,1]]}",,3.80,
1010,I,0.11,0.21,1.01,1.1,2.1,3.1,,,,,,,
1020,M,,,,,,,MARKER,IMU_VALIDATION,2,"{""source_mode"": ""imu_trusted"", ""status_text"": ""ORIENTATION OK""}",,3.80,
"""
        session = CSVLoader().load(io.StringIO(csv_data))
        self.assertEqual(getattr(session, "mount_profile", {}).get("id"), "tank")
        self.assertEqual(getattr(session, "runtime_validation", {}).get("source_mode"), "imu_trusted")

if __name__ == '__main__':
    unittest.main()
