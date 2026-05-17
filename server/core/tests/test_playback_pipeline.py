import json
import os
import tempfile
import unittest

from src.analysis.core.models import EnvSample, GPSSample, IMUSample, Lap, Sample, Session
from src.analysis.core.session_exporter import SessionExporter
from src.analysis.core.session_processor import SessionProcessor


class TestPlaybackPipeline(unittest.TestCase):
    def test_timing_session_keeps_only_true_gps_fixes(self):
        session = Session(description="mixed")
        session.add_sample(Sample(0.0, GPSSample(10.0, 77.0, 50.0, 8), IMUSample(0, 0, 1), EnvSample(0, 0), gps_is_fix=True, gps_is_valid=True))
        session.add_sample(Sample(0.01, GPSSample(10.0001, 77.0001, 50.5, 8), IMUSample(0, 0, 1), EnvSample(0, 0), gps_is_fix=False, gps_is_valid=True))
        session.add_sample(Sample(0.02, GPSSample(10.0002, 77.0002, 51.0, 8), IMUSample(0, 0, 1), EnvSample(0, 0), gps_is_fix=True, gps_is_valid=True))

        timing_session = SessionProcessor._build_timing_session(session)

        self.assertEqual(len(timing_session.samples), 2)
        self.assertTrue(all(sample.gps_is_fix for sample in timing_session.samples))
        self.assertEqual([sample.timestamp for sample in timing_session.samples], [0.0, 0.02])

    def test_export_playback_dataset_uses_rows_and_official_laps(self):
        with tempfile.TemporaryDirectory() as output_dir, tempfile.TemporaryDirectory() as tracks_dir:
            session = Session(description="playback")
            session.add_sample(Sample(100.0, GPSSample(10.0, 77.0, 80.0, 8), IMUSample(0.0, 0.1, 1.0), EnvSample(0, 0), gps_is_fix=True, gps_is_valid=True))
            session.add_sample(Sample(101.0, GPSSample(10.0001, 77.0001, 81.0, 8), IMUSample(0.1, 0.2, 1.0), EnvSample(0, 0), gps_is_fix=False, gps_is_valid=True))
            session.add_sample(Sample(102.0, GPSSample(10.0002, 77.0002, 82.0, 8), IMUSample(0.2, 0.3, 1.0), EnvSample(0, 0), gps_is_fix=True, gps_is_valid=True))
            lap = Lap(session, 0, 2, number=1)
            lap.sector_times = {"S1": 1.0, "S2": 1.0}
            session.laps = [lap]
            playback_lap = Lap(session, 0, 3, number=1)
            playback_lap.sector_times = {"S1": 0.9, "S2": 1.1}
            playback_lap.delta_to_official = 0.0
            session.playback_laps = [playback_lap]
            session.playback_dataset = {
                "config": {"gpsLagMs": 175},
                "signals": {
                    "lean_deg": [1.0, 2.0, 3.0],
                    "long_g": [0.1, 0.2, 0.3],
                    "lat_g": [0.4, 0.5, 0.6],
                    "accel_g": [0.1, 0.2, 0.3],
                    "brake_g": [0.0, 0.0, 0.0],
                },
                "gps_references": {
                    "gps_lean_deg": [10.0, 11.0, 12.0],
                    "gps_long_g": [0.01, 0.02, 0.03],
                },
            }

            exporter = SessionExporter(output_dir=output_dir, tracks_dir=tracks_dir)
            track_info = {
                "track_id": 1,
                "track_name": "Test Track",
                "folder_name": "track_1",
                "sectors": [{"sector_index": 1}, {"sector_index": 2}],
            }
            tbl_data = {"sectors": [], "total_best_time": None}

            out_path = exporter.export(session, track_info, tbl_data, source_file="playback.csv")
            playback_path = out_path.replace(".json", "_playback.json")

            self.assertTrue(os.path.exists(playback_path))
            with open(playback_path, "r") as handle:
                payload = json.load(handle)

            self.assertEqual(payload["meta"]["gps_lag_ms_applied"], 175)
            self.assertEqual(len(payload["rows"]), 3)
            self.assertEqual(payload["rows"][0]["lap_number"], 1)
            self.assertTrue(payload["rows"][0]["lap_start"])
            self.assertEqual(payload["rows"][0]["sector_index"], 1)
            self.assertEqual(payload["laps"][0]["lap_time"], round(playback_lap.duration, 3))
            self.assertEqual(payload["laps"][0]["sector_times"], [0.9, 1.1])
            self.assertEqual(payload["rows"][1]["lean_deg"], 2.0)
            self.assertEqual(payload["rows"][1]["long_g"], 0.2)
            self.assertEqual(payload["rows"][2]["heading_deg"], payload["rows"][1]["heading_deg"])


if __name__ == "__main__":
    unittest.main()
