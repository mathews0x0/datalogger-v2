import json
import math
import os
import tempfile
import unittest

from src.analysis.core.models import EnvSample, GPSSample, IMUSample, Lap, Sample, Session
from src.analysis.core.session_exporter import SessionExporter
from src.analysis.core.session_processor import SessionProcessor
from src.analysis.core.playback_tuner import apply_tune_to_playback_payload, build_tune_preview_patch, estimate_playback_reference_alignment, normalize_playback_tune


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
            session.add_sample(Sample(101.0, GPSSample(10.0001, 77.0001, 81.0, 8), IMUSample(0.1, 0.2, 1.0), EnvSample(0, 0), gps_is_fix=False, gps_is_valid=False))
            session.add_sample(Sample(102.0, GPSSample(10.0002, 77.0002, 82.0, 8), IMUSample(0.2, 0.3, 1.0), EnvSample(0, 0), gps_is_fix=True, gps_is_valid=True))
            lap = Lap(session, 0, 2, number=1)
            lap.sector_times = {"S1": 1.0, "S2": 1.0}
            session.laps = [lap]
            playback_lap = Lap(session, 0, 3, number=1)
            playback_lap.sector_times = {"S1": 0.9, "S2": 1.1}
            playback_lap.delta_to_official = 0.0
            session.playback_laps = [playback_lap]
            session.playback_dataset = {
                "config": {"gpsLagMs": 2000},
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
                "display_signals": {
                    "display_lean_deg": [1.0, 1.5, 2.0],
                    "display_long_g": [0.1, 0.15, 0.2],
                    "display_lat_g": [0.4, 0.45, 0.5],
                },
            }
            session.device_metadata = {"timestamp_source": "gps_epoch"}

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

            self.assertEqual(payload["meta"]["gps_lag_ms_applied"], 2000)
            self.assertEqual(payload["meta"]["timestamp_source"], "gps_epoch")
            self.assertEqual(payload["meta"]["duration_sec"], 2.0)
            self.assertIsNotNone(payload["meta"]["start_time"])
            self.assertEqual(len(payload["rows"]), 3)
            self.assertEqual(payload["rows"][0]["lap_number"], 1)
            self.assertTrue(payload["rows"][0]["lap_start"])
            self.assertEqual(payload["rows"][0]["sector_index"], 1)
            self.assertEqual(payload["laps"][0]["lap_time"], round(playback_lap.duration, 3))
            self.assertEqual(payload["laps"][0]["sector_times"], [0.9, 1.1])
            self.assertEqual(payload["rows"][1]["lean_deg"], 2.0)
            self.assertEqual(payload["rows"][1]["long_g"], 0.2)
            self.assertEqual(payload["rows"][1]["imu_lean_base_deg"], None)
            self.assertIsNone(payload["rows"][1]["speed_kmh"])
            self.assertIsNotNone(payload["rows"][1]["display_speed_kmh"])
            self.assertIsNotNone(payload["rows"][1]["display_lat"])
            self.assertIsNotNone(payload["rows"][1]["display_lon"])
            self.assertIsNotNone(payload["rows"][1]["race_lat"])
            self.assertIsNotNone(payload["rows"][1]["race_lon"])
            self.assertIsNotNone(payload["rows"][1]["aligned_speed_kmh"])
            self.assertIsNotNone(payload["rows"][1]["aligned_lat"])
            self.assertIsNotNone(payload["rows"][1]["aligned_lon"])
            self.assertEqual(payload["rows"][1]["display_lean_deg"], 1.5)
            self.assertEqual(payload["rows"][1]["display_long_g"], 0.15)
            self.assertEqual(payload["rows"][1]["gps_lean_base_deg"], 11.0)
            self.assertEqual(payload["rows"][2]["heading_deg"], payload["rows"][1]["heading_deg"])

            second_out_path = exporter.export(session, track_info, tbl_data, source_file="playback.csv")
            primary_files = [
                filename for filename in os.listdir(output_dir)
                if filename.endswith(".json") and not filename.endswith(("_telemetry.json", "_playback.json"))
            ]
            self.assertEqual(second_out_path, out_path)
            self.assertEqual(primary_files, [os.path.basename(out_path)])

    def test_reference_alignment_detects_lag_and_inverted_polarity(self):
        times = [index * 0.1 for index in range(120)]
        lag_samples = 5
        imu_lean = [math.sin(index / 8.0) * 30.0 for index in range(len(times))]
        imu_long = [math.sin(index / 10.0) * 0.3 for index in range(len(times))]
        gps_lean = [-(imu_lean[min(len(imu_lean) - 1, index + lag_samples)]) for index in range(len(times))]
        gps_long = [-(imu_long[min(len(imu_long) - 1, index + lag_samples)]) for index in range(len(times))]

        alignment = estimate_playback_reference_alignment(
            times,
            imu_lean,
            imu_long,
            gps_lean,
            gps_long,
            {
                "gpsLagMs": 2000,
                "gpsLagAutoEnabled": True,
                "gpsLagMinMs": 0,
                "gpsLagMaxMs": 1000,
                "gpsLagStepMs": 100,
            },
        )

        self.assertEqual(alignment["gps_lag_source"], "auto")
        self.assertEqual(alignment["gps_lag_ms_applied"], 500)
        self.assertEqual(alignment["gps_lean_ref_sign"], -1)
        self.assertEqual(alignment["gps_long_ref_sign"], -1)

    def test_reference_alignment_uses_longitudinal_as_primary_timing_signal(self):
        times = [index * 0.1 for index in range(180)]
        lag_samples = 5
        imu_lean = [math.sin(index / 7.0) * 25.0 for index in range(len(times))]
        imu_long = [
            (math.sin(index / 3.5) + (0.45 * math.sin(index / 11.0))) * 0.25
            for index in range(len(times))
        ]
        gps_lean = list(imu_lean)
        gps_long = [
            imu_long[min(len(imu_long) - 1, index + lag_samples)]
            for index in range(len(times))
        ]

        alignment = estimate_playback_reference_alignment(
            times,
            imu_lean,
            imu_long,
            gps_lean,
            gps_long,
            {
                "gpsLagMs": 0,
                "gpsLagAutoEnabled": True,
                "gpsLagMinMs": 0,
                "gpsLagMaxMs": 1000,
                "gpsLagStepMs": 100,
            },
        )

        self.assertEqual(alignment["gps_lag_source"], "auto")
        self.assertEqual(alignment["gps_lag_ms_applied"], 500)

    def test_tuner_preview_updates_display_fields_only(self):
        payload = {
            "config": {"flipLean": False, "flipForce": False, "gpsLagMs": 1800},
            "rows": [
                {
                    "time": 0.0,
                    "lat": 10.0,
                    "lon": 77.0,
                    "speed_kmh": 100.0,
                    "lean_deg": -5.0,
                    "long_g": 0.2,
                    "lat_g": 0.1,
                    "imu_lean_base_deg": -5.0,
                    "imu_long_base_g": 0.2,
                    "imu_lat_base_g": 0.1,
                    "gps_lean_base_deg": 4.0,
                    "gps_long_base_g": -0.2,
                    "gps_is_valid": True,
                },
                {
                    "time": 0.1,
                    "lat": 10.0001,
                    "lon": 77.0001,
                    "speed_kmh": 101.0,
                    "lean_deg": -10.0,
                    "long_g": 0.3,
                    "lat_g": 0.2,
                    "imu_lean_base_deg": -10.0,
                    "imu_long_base_g": 0.3,
                    "imu_lat_base_g": 0.2,
                    "gps_lean_base_deg": 8.0,
                    "gps_long_base_g": -0.3,
                    "gps_is_valid": True,
                },
            ],
        }
        tuned = apply_tune_to_playback_payload(payload, tune={
            "flipLean": True,
            "flipForce": True,
            "gpsLagMs": 1200,
        }, tune_source="preview", feature_enabled=True)

        self.assertEqual(tuned["rows"][0]["lean_deg"], -5.0)
        self.assertEqual(tuned["rows"][0]["display_lean_deg"], 5.0)
        self.assertEqual(tuned["rows"][1]["display_long_g"], -0.3)
        self.assertEqual(tuned["rows"][0]["gps_lean_ref_deg"], 4.0)
        self.assertEqual(tuned["rows"][0]["gps_long_ref_g"], 0.2)
        self.assertEqual(tuned["meta"]["tune_source"], "preview")
        self.assertTrue(tuned["meta"]["tuner_feature_enabled"])

    def test_gyro_scale_changes_display_lean(self):
        payload = {
            "config": {},
            "rows": [
                {
                    "time": 0.0,
                    "lat": 10.0,
                    "lon": 77.0,
                    "speed_kmh": 100.0,
                    "lean_deg": 10.0,
                    "long_g": 0.02,
                    "lat_g": 0.4,
                    "imu_lean_base_deg": 10.0,
                    "imu_long_base_g": 0.02,
                    "imu_lat_base_g": 0.4,
                    "gps_is_valid": True,
                },
                {
                    "time": 0.1,
                    "lat": 10.0001,
                    "lon": 77.0001,
                    "speed_kmh": 101.0,
                    "lean_deg": 12.0,
                    "long_g": 0.02,
                    "lat_g": 0.4,
                    "imu_lean_base_deg": 12.0,
                    "imu_long_base_g": 0.02,
                    "imu_lat_base_g": 0.4,
                    "gps_is_valid": True,
                },
            ],
        }
        default_tuned = apply_tune_to_playback_payload(payload, tune={
            "gyroScale": 0.04,
        })
        adjusted = apply_tune_to_playback_payload(payload, tune={
            "gyroScale": 0.08,
        })

        self.assertNotEqual(default_tuned["rows"][0]["display_lean_deg"], adjusted["rows"][0]["display_lean_deg"])
        self.assertNotEqual(default_tuned["rows"][1]["display_lean_deg"], adjusted["rows"][1]["display_lean_deg"])

    def test_normalize_maps_new_config_to_internal_alignment_fields(self):
        normalized = normalize_playback_tune({
            "gyroScale": 0.04,
            "leanGaussianSigma": 1.2,
            "longGaussianSigma": 1.0,
            "flipLean": True,
            "flipForce": True,
            "autoAlignEnabled": False,
        })

        self.assertEqual(normalized["leanGaussianSigma"], 1.2)
        self.assertEqual(normalized["longGaussianSigma"], 1.0)
        self.assertTrue(normalized["flipLean"])
        self.assertTrue(normalized["flipForce"])
        self.assertFalse(normalized["gpsLagAutoEnabled"])
        self.assertEqual(normalized["leanSign"], -1)
        self.assertEqual(normalized["gpsLongRefSign"], -1)

    def test_preview_uses_single_lag_for_path_and_references(self):
        rows = []
        for index in range(4):
            rows.append({
                "time": float(index),
                "lat": 10.0 + index * 0.0001,
                "lon": 77.0 + index * 0.0001,
                "speed_kmh": 100.0 + index,
                "lean_deg": 0.0,
                "long_g": 0.0,
                "lat_g": 0.0,
                "imu_lean_base_deg": 0.0,
                "imu_long_base_g": 0.0,
                "imu_lat_base_g": 0.0,
                "gps_lean_base_deg": 10.0 + index,
                "gps_long_base_g": round(index * 0.1, 3),
                "gps_is_valid": True,
            })

        normalized = normalize_playback_tune({
            "gpsLagMs": 1000,
            "autoAlignEnabled": False,
            "gpsLeanRefSign": 1,
            "gpsLongRefSign": 1,
        })

        self.assertEqual(normalized["gpsLagMs"], 1000)
        self.assertEqual(normalized["gpsLeanLagMs"], 1000)
        self.assertEqual(normalized["gpsLongLagMs"], 1000)

        patch = build_tune_preview_patch(
            {"config": {}, "rows": rows},
            tune=normalized,
            start_index=2,
            end_index=3,
        )

        self.assertEqual(patch["meta"]["gps_lag_ms_applied"], 1000)
        self.assertEqual(patch["meta"]["gps_lean_lag_ms_applied"], 1000)
        self.assertEqual(patch["meta"]["gps_long_lag_ms_applied"], 1000)
        self.assertEqual(patch["meta"]["alignment_frame_label"], "session_window")
        self.assertEqual(patch["meta"]["alignment_frame_points"], 1)
        self.assertEqual(patch["columns"]["gps_lean_ref_deg"][0], 11.0)
        self.assertEqual(patch["columns"]["gps_long_ref_g"][0], 0.1)

    def test_alignment_meta_reports_confidence_and_match_counts(self):
        times = [index * 0.1 for index in range(120)]
        lag_samples = 5
        imu_lean = [math.sin(index / 8.0) * 30.0 for index in range(len(times))]
        imu_long = [math.sin(index / 10.0) * 0.3 for index in range(len(times))]
        gps_lean = [-(imu_lean[min(len(imu_lean) - 1, index + lag_samples)]) for index in range(len(times))]
        gps_long = [-(imu_long[min(len(imu_long) - 1, index + lag_samples)]) for index in range(len(times))]

        alignment = estimate_playback_reference_alignment(
            times,
            imu_lean,
            imu_long,
            gps_lean,
            gps_long,
            {
                "gpsLagMs": 2000,
                "gpsLagAutoEnabled": True,
                "gpsLagMinMs": 0,
                "gpsLagMaxMs": 1000,
                "gpsLagStepMs": 100,
            },
        )

        self.assertIsNotNone(alignment["alignment_confidence"])
        self.assertGreater(alignment["alignment_lean_points"], 0)
        self.assertGreater(alignment["alignment_long_points"], 0)

    def test_path_trim_moves_path_series_without_changing_graph_reference_sampling(self):
        rows = []
        for index in range(5):
            rows.append({
                "time": float(index),
                "lat": 10.0 + index * 0.001,
                "lon": 77.0 + index * 0.001,
                "speed_kmh": 100.0 + index,
                "lean_deg": 0.0,
                "long_g": 0.0,
                "lat_g": 0.0,
                "imu_lean_base_deg": 0.0,
                "imu_long_base_g": 0.0,
                "imu_lat_base_g": 0.0,
                "gps_lean_base_deg": 10.0 + index,
                "gps_long_base_g": round(index * 0.1, 3),
                "gps_is_valid": True,
            })

        base_tune = normalize_playback_tune({
            "gpsLagMs": 1000,
            "autoAlignEnabled": False,
            "gpsLeanRefSign": 1,
            "gpsLongRefSign": 1,
            "pathTrimMs": 0,
        })
        trimmed_tune = dict(base_tune)
        trimmed_tune["pathTrimMs"] = 1000

        base_patch = build_tune_preview_patch({"config": {}, "rows": rows}, tune=base_tune, start_index=2, end_index=3)
        trimmed_patch = build_tune_preview_patch({"config": {}, "rows": rows}, tune=trimmed_tune, start_index=2, end_index=3)

        self.assertEqual(base_patch["columns"]["gps_lean_ref_deg"][0], trimmed_patch["columns"]["gps_lean_ref_deg"][0])
        self.assertNotEqual(base_patch["columns"]["aligned_lat"][0], trimmed_patch["columns"]["aligned_lat"][0])
        self.assertNotEqual(base_patch["columns"]["display_lat"][0], trimmed_patch["columns"]["display_lat"][0])

    def test_gaussian_smoothing_changes_display_lean_and_persists_in_tune(self):
        payload = {
            "config": {},
            "rows": [
                {
                    "time": float(index),
                    "lat": 10.0,
                    "lon": 77.0,
                    "speed_kmh": 100.0,
                    "lean_deg": value,
                    "long_g": 0.0,
                    "lat_g": 0.0,
                    "imu_lean_base_deg": value,
                    "imu_long_base_g": 0.0,
                    "imu_lat_base_g": 0.0,
                    "gps_lean_base_deg": value,
                    "gps_long_base_g": 0.0,
                    "gps_is_valid": True,
                }
                for index, value in enumerate([0.0, 0.0, 20.0, 0.0, 0.0])
            ],
        }
        base = apply_tune_to_playback_payload(payload, tune=normalize_playback_tune({
            "leanGaussianSigma": 0.0,
            "autoAlignEnabled": False,
        }))
        smoothed = apply_tune_to_playback_payload(payload, tune=normalize_playback_tune({
            "leanGaussianSigma": 1.5,
            "autoAlignEnabled": False,
        }))

        self.assertEqual(smoothed["config"]["leanGaussianSigma"], 1.5)
        self.assertNotEqual(base["rows"][2]["display_lean_deg"], smoothed["rows"][2]["display_lean_deg"])
        self.assertGreater(abs(smoothed["rows"][1]["display_lean_deg"]), 0.0)

    def test_force_gaussian_smoothing_changes_display_force_and_persists_in_tune(self):
        payload = {
            "config": {},
            "rows": [
                {
                    "time": float(index),
                    "lat": 10.0,
                    "lon": 77.0,
                    "speed_kmh": 100.0,
                    "lean_deg": 0.0,
                    "long_g": value,
                    "lat_g": 0.0,
                    "imu_lean_base_deg": 0.0,
                    "imu_long_base_g": value,
                    "imu_lat_base_g": 0.0,
                    "gps_lean_base_deg": 0.0,
                    "gps_long_base_g": value,
                    "gps_is_valid": True,
                }
                for index, value in enumerate([0.0, 0.0, 1.0, 0.0, 0.0])
            ],
        }
        base = apply_tune_to_playback_payload(payload, tune=normalize_playback_tune({
            "longGaussianSigma": 0.0,
            "autoAlignEnabled": False,
        }))
        smoothed = apply_tune_to_playback_payload(payload, tune=normalize_playback_tune({
            "longGaussianSigma": 1.5,
            "autoAlignEnabled": False,
        }))

        self.assertEqual(smoothed["config"]["longGaussianSigma"], 1.5)
        self.assertNotEqual(base["rows"][2]["display_long_g"], smoothed["rows"][2]["display_long_g"])
        self.assertGreater(abs(smoothed["rows"][1]["display_long_g"]), 0.0)


if __name__ == "__main__":
    unittest.main()
