import io
import unittest

from src.analysis.core.models import Session, Sample, GPSSample, IMUSample, EnvSample, Lap
from src.analysis.core.track_generator import TrackGenerator
from src.analysis.ingestion.csv_loader import CSVLoader


class TestTrackGenerator(unittest.TestCase):
    def test_dual_rate_loader_marks_real_gps_fixes_and_metadata(self):
        csv_text = """tick_ms,row_type,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,lat,lon,alt,speed,sats,vbat,gps_epoch,imu_sensor_us
1000,I,0,0,0,0,0,0,,,,,,,,1000000
1100,G,0,0,0,0,0,0,10.0,77.0,0,50,6,4.1,1000,1100000
1200,I,0,0,0,0,0,0,,,,,,,,1200000
1300,G,0,0,0,0,0,0,10.0001,77.0001,0,52,7,4.1,1000,1300000
"""
        session = CSVLoader().load(io.StringIO(csv_text), source_name="inline.csv")

        self.assertEqual(len(session.samples), 4)
        self.assertEqual(sum(1 for sample in session.samples if sample.gps_is_fix), 2)
        self.assertEqual(
            [(sample.gps.lat, sample.gps.lon) for sample in session.samples if sample.gps_is_fix],
            [(10.0, 77.0), (10.0001, 77.0001)],
        )
        self.assertEqual(session.device_metadata["gps_fix_count"], 2)
        self.assertAlmostEqual(session.device_metadata["gps_fix_span_s"], 0.2)

    def test_rejects_sparse_gps_coverage(self):
        session = Session(description="sparse")
        session.add_sample(Sample(0.0, GPSSample(10.0, 77.0, 0.0, 0), IMUSample(0, 0, 0), EnvSample(0, 0), gps_is_fix=True))
        session.add_sample(Sample(400.0, GPSSample(10.0, 77.0, 0.0, 0), IMUSample(0, 0, 0), EnvSample(0, 0), gps_is_fix=True))
        session.device_metadata = {"gps_fix_count": 10, "gps_fix_span_s": 2.0}

        self.assertFalse(TrackGenerator._has_sufficient_gps_coverage(session))

    def test_prefers_real_gps_fix_samples_for_path_geometry(self):
        session = Session(description="lap")
        for idx in range(20):
            session.add_sample(
                Sample(
                    float(idx),
                    GPSSample(10.0 + idx * 0.0001, 77.0, 80.0, 8),
                    IMUSample(0, 0, 0),
                    EnvSample(0, 0),
                    gps_is_fix=True,
                )
            )
            session.add_sample(
                Sample(
                    float(idx) + 0.01,
                    GPSSample(0.0, 0.0, 80.0, 0),
                    IMUSample(0, 0, 0),
                    EnvSample(0, 0),
                    gps_is_fix=False,
                )
            )

        lap = Lap(session, 0, len(session.samples), number=1)
        path_samples = TrackGenerator._lap_path_samples(lap)

        self.assertEqual(len(path_samples), 20)
        self.assertTrue(all(sample.gps_is_fix for sample in path_samples))

    def test_gps_only_session_keeps_only_real_fixes_in_log_order(self):
        session = Session(description="mixed")
        session.add_sample(Sample(10.0, GPSSample(10.0, 77.0, 50.0, 6), IMUSample(0, 0, 0), EnvSample(0, 0), gps_is_fix=False))
        session.add_sample(Sample(9.0, GPSSample(10.1, 77.1, 51.0, 7), IMUSample(1, 2, 3, 4, 5, 6), EnvSample(0, 0), gps_is_fix=True))
        session.add_sample(Sample(11.0, GPSSample(0.0, 0.0, 0.0, 0), IMUSample(0, 0, 0), EnvSample(0, 0), gps_is_fix=True))
        session.add_sample(Sample(8.0, GPSSample(10.2, 77.2, 52.0, 8), IMUSample(7, 8, 9, 10, 11, 12), EnvSample(0, 0), gps_is_fix=True))

        gps_session = TrackGenerator._gps_only_session(session)

        self.assertEqual(len(gps_session.samples), 2)
        self.assertEqual([sample.timestamp for sample in gps_session.samples], [9.0, 8.0])
        self.assertTrue(all(sample.gps_is_fix for sample in gps_session.samples))

    def test_sector_generation_includes_progress_markers(self):
        generator = TrackGenerator(tracks_dir="/tmp/track-generator-tests")
        lats = [10.0, 10.0001, 10.0002, 10.0003, 10.0]
        lons = [77.0, 77.0001, 77.0002, 77.0003, 77.0]

        sectors, _ = generator._calculate_sectors_from_coords(lats, lons, lats[0], lons[0])

        self.assertTrue(all(sector.get("progress_m") is not None for sector in sectors))
        self.assertEqual(
            [sector["progress_m"] for sector in sectors],
            sorted(sector["progress_m"] for sector in sectors),
        )


if __name__ == "__main__":
    unittest.main()
