import math
import unittest
from unittest.mock import patch

from src.analysis.core.models import EnvSample, GPSSample, IMUSample, Sample, Session
from src.analysis.core.session_processor import SessionProcessor
from src.analysis.processing.advanced_imu import AdvancedIMUProcessor, IMUConfig, IMUValidationEngine


class TestAdvancedIMUProcessor(unittest.TestCase):
    def test_validation_rejects_impossible_lean(self):
        config = IMUConfig()
        config.sample_rate_est = 100.0
        validator = IMUValidationEngine(config)

        validation = validator.validate(
            lean_angle=[0.0, 10.0, 68.0, 12.0],
            acceleration_g=[0.0, 0.1, 0.0, 0.0],
            braking_g=[0.0, 0.0, 0.2, 0.0],
            lateral_g=[0.0, 0.2, 0.8, 0.1],
            vertical_g=[1.0, 1.0, 1.0, 1.0],
            speeds=[50.0, 55.0, 60.0, 58.0],
            straight_mask=[True, False, False, True],
            gps_longitudinal_g=[0.0, 0.05, 0.1, -0.02],
            yaw_rate_deg_s=[0.0, 8.0, 2.0, 0.5],
            mount_confidence="HIGH",
        )

        self.assertFalse(validation["passed"])
        self.assertTrue(any("lean exceeded" in failure for failure in validation["failures"]))

    def test_processor_returns_mount_metadata(self):
        processor = AdvancedIMUProcessor()
        timestamps = [i * 0.01 for i in range(400)]

        ax = []
        ay = []
        az = []
        gx = []
        gy = []
        gz = []
        speeds = []
        lats = []
        lons = []

        base_lat = 12.0000
        base_lon = 77.0000

        for i, t in enumerate(timestamps):
            if i < 150:
                speed = 0.0
                yaw_rate = 0.0
                accel_long = 0.0
            else:
                speed = 70.0
                yaw_rate = 0.0
                accel_long = 0.08 if i < 280 else 0.0

            ax.append(accel_long)
            ay.append(0.0)
            az.append(1.0)
            gx.append(0.0)
            gy.append(0.0)
            gz.append(yaw_rate)
            speeds.append(speed)

            distance_step = (speed / 3.6) * 0.01
            base_lon += distance_step / (111320.0 * math.cos(math.radians(base_lat)))
            lats.append(base_lat)
            lons.append(base_lon)

        result = processor.process(
            timestamps=timestamps,
            ax_raw=ax,
            ay_raw=ay,
            az_raw=az,
            gx_raw=gx,
            gy_raw=gy,
            gz_raw=gz,
            speeds=speeds,
            lats=lats,
            lons=lons,
        )

        self.assertIn("mount_confidence", result)
        self.assertIn("mount_method", result)
        self.assertIn("rotation_matrix", result)
        self.assertIn("validation", result)
        self.assertEqual(len(result["lean_angle"]), len(timestamps))

    def test_validation_rejects_braking_that_misses_gps_speed_drop(self):
        config = IMUConfig()
        config.sample_rate_est = 100.0
        validator = IMUValidationEngine(config)

        n = 240
        validation = validator.validate(
            lean_angle=[0.0] * n,
            acceleration_g=[0.0] * n,
            braking_g=[0.0] * n,
            lateral_g=[0.0] * n,
            vertical_g=[1.0] * n,
            speeds=[80.0] * n,
            straight_mask=[True] * n,
            gps_longitudinal_g=([-0.12] * 120) + ([0.0] * 120),
            yaw_rate_deg_s=[0.0] * n,
            mount_confidence="MEDIUM",
        )

        self.assertFalse(validation["passed"])
        self.assertTrue(any("braking does not align with GPS speed drop" in failure for failure in validation["failures"]))

    def test_startup_rollout_calibration_detects_static_plus_rollout(self):
        processor = AdvancedIMUProcessor()
        processor.config.sample_rate_est = 100.0

        n = 1500
        timestamps = [i * 0.01 for i in range(n)]
        ax = [0.0] * n
        ay = [0.0] * n
        az = [1.0] * n
        gx = [0.0] * n
        gy = [0.0] * n
        gz = [0.0] * n
        speeds = [0.0] * n
        lats = [12.0] * n
        lons = [77.0] * n

        lon = 77.0
        for i in range(200, 450):
            speeds[i] = 2.0 + ((i - 200) * 0.03)
            ax[i] = 0.06
            lon += ((speeds[i] / 3.6) * 0.01) / (111320.0 * math.cos(math.radians(12.0)))
            lons[i] = lon
        for i in range(450, n):
            lons[i] = lon

        gps = processor._build_gps_features(timestamps, speeds, lats, lons)
        startup = processor._resolve_startup_calibration(ax, ay, az, gx, gy, gz, gps)

        self.assertIsNotNone(startup)
        self.assertTrue(startup["method"].startswith("startup_"))
        self.assertGreater(startup["rollout_seconds"], 0.5)

    def test_startup_rollout_only_detects_low_dynamic_forward_motion(self):
        processor = AdvancedIMUProcessor()
        processor.config.sample_rate_est = 100.0

        n = 1200
        timestamps = [i * 0.01 for i in range(n)]
        ax = [0.02] * n
        ay = [0.0] * n
        az = [1.0] * n
        gx = [30.0] * n
        gy = [25.0] * n
        gz = [20.0] * n
        speeds = [9.0] * n
        lats = [12.0] * n
        lons = []

        lon = 77.0
        for _ in range(n):
            lon += ((8.0 / 3.6) * 0.01) / (111320.0 * math.cos(math.radians(12.0)))
            lons.append(lon)

        gps = processor._build_gps_features(timestamps, speeds, lats, lons)
        startup = processor._resolve_startup_calibration(ax, ay, az, gx, gy, gz, gps)

        self.assertIsNotNone(startup)
        self.assertTrue(startup["method"].startswith("startup_"))
        self.assertGreaterEqual(startup["rollout_seconds"], 0.5)

    def test_processor_uses_calibration_profile_when_provided(self):
        processor = AdvancedIMUProcessor()
        timestamps = [i * 0.01 for i in range(300)]
        ax = [0.05] * 300
        ay = [0.0] * 300
        az = [1.0] * 300
        gx = [0.0] * 300
        gy = [0.0] * 300
        gz = [0.0] * 300
        speeds = [40.0] * 300
        lats = [12.0] * 300
        lons = [77.0 + (i * 0.00001) for i in range(300)]
        profile = {
            "id": "tank",
            "label": "tank",
            "rotation_matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            "gyro_bias": [0.0, 0.0, 0.0],
            "accel_bias": [0.0, 0.0, 0.0],
            "gravity_vector": [0.0, 0.0, 1.0],
            "quality_score": 0.9,
        }
        validation = {"source_mode": "imu_trusted", "status_text": "ORIENTATION OK"}

        result = processor.process(
            timestamps=timestamps,
            ax_raw=ax,
            ay_raw=ay,
            az_raw=az,
            gx_raw=gx,
            gy_raw=gy,
            gz_raw=gz,
            speeds=speeds,
            lats=lats,
            lons=lons,
            calibration_profile=profile,
            runtime_validation=validation,
        )

        self.assertEqual(result["mount_method"], "stored_profile")
        self.assertEqual(result["diagnostics"]["selected_algorithm"], "calibrated_profile")
        self.assertEqual(len(result["lean_angle"]), len(timestamps))

    def test_repairs_legacy_bmi323_gyro_scale(self):
        session = Session("legacy")
        for i in range(200):
            session.add_sample(
                Sample(
                    timestamp=i * 0.02,
                    gps=GPSSample(12.0, 77.0, 40.0, 8),
                    imu=IMUSample(0.0, 0.0, 1.0, 640.0, -320.0, 160.0),
                    env=EnvSample(0.0, 4.0),
                    gps_is_fix=False,
                )
            )

        profile = {"gyro_bias": [16.0, -32.0, 48.0]}
        validation = {"reason": "gyro_mismatch"}
        gx, gy, gz, repaired_profile = SessionProcessor._repair_legacy_bmi323_gyro_scale(
            [640.0] * 200,
            [-320.0] * 200,
            [160.0] * 200,
            profile,
            validation,
            session,
        )

        self.assertAlmostEqual(gx[0], 40.0)
        self.assertAlmostEqual(gy[0], -20.0)
        self.assertAlmostEqual(gz[0], 10.0)
        self.assertEqual(repaired_profile["gyro_bias"], [1.0, -2.0, 3.0])
        self.assertEqual(repaired_profile["postprocess_repairs"][0]["type"], "bmi323_gyro_range_scale")

    def test_playback_signals_follow_selected_candidate(self):
        processor = AdvancedIMUProcessor()
        timestamps = [0.0, 0.1, 0.2]
        zeros = [0.0, 0.0, 0.0]
        speeds = [60.0, 60.0, 60.0]
        lats = [12.0, 12.0, 12.0]
        lons = [77.0, 77.0001, 77.0002]

        primary = {
            "lean_angle": [1.0, 1.0, 1.0],
            "ax_cg": [0.1, 0.1, 0.1],
            "ay_cg": [0.2, 0.2, 0.2],
            "acceleration_g": [0.1, 0.1, 0.1],
            "braking_g": [0.0, 0.0, 0.0],
            "lateral_g": [0.2, 0.2, 0.2],
            "az_cg": [1.0, 1.0, 1.0],
        }
        legacy = {
            "lean_angle": [9.0, 8.0, 7.0],
            "ax_cg": [0.4, 0.5, 0.6],
            "ay_cg": [0.7, 0.8, 0.9],
            "acceleration_g": [0.4, 0.5, 0.6],
            "braking_g": [0.0, 0.0, 0.0],
            "lateral_g": [0.7, 0.8, 0.9],
            "az_cg": [1.0, 1.0, 1.0],
        }
        gps_only = {
            "lean_angle": [3.0, 3.0, 3.0],
            "ax_cg": [0.0, 0.0, 0.0],
            "ay_cg": [0.0, 0.0, 0.0],
            "acceleration_g": [0.0, 0.0, 0.0],
            "braking_g": [0.0, 0.0, 0.0],
            "lateral_g": [0.0, 0.0, 0.0],
            "az_cg": [1.0, 1.0, 1.0],
        }

        with patch.object(processor, "_build_gps_features", return_value={
            "speeds": speeds,
            "gps_accel_g": [0.0, 0.0, 0.0],
            "yaw_rate_deg_s": [0.0, 0.0, 0.0],
            "straight_mask": [True, True, True],
            "turn_mask": [False, False, False],
            "heading_quality": 1.0,
        }), patch.object(processor, "_build_gps_reference_payload", return_value={"gps_lean_deg": [0.0, 0.0, 0.0], "gps_long_g": [0.0, 0.0, 0.0]}), patch.object(processor, "_resolve_mount", return_value={
            "rotation_matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            "gyro_bias": [0.0, 0.0, 0.0],
            "gravity_vector": [0.0, 0.0, 1.0],
            "mount_confidence": "HIGH",
            "mount_method": "mock_mount",
            "evidence_summary": {"source": "mock"},
            "confidence_score": 0.9,
        }), patch.object(processor, "_compute_orientation_outputs", return_value=primary), patch.object(processor, "_compute_legacy_outputs", return_value=legacy), patch.object(processor, "_compute_gps_fallback", return_value=gps_only), patch.object(processor._validation, "validate", side_effect=[
            {"score": 70.0, "passed": True},
            {"score": 90.0, "passed": True},
            {"score": 20.0, "passed": False},
        ]):
            result = processor.process(
                timestamps=timestamps,
                ax_raw=zeros,
                ay_raw=zeros,
                az_raw=[1.0, 1.0, 1.0],
                gx_raw=zeros,
                gy_raw=zeros,
                gz_raw=zeros,
                speeds=speeds,
                lats=lats,
                lons=lons,
            )

        self.assertEqual(result["diagnostics"]["selected_algorithm"], "legacy_two_pass")
        self.assertEqual(result["playback_signals"]["lean_deg"], legacy["lean_angle"])
        self.assertEqual(result["playback_signals"]["long_g"], legacy["ax_cg"])

    def test_calibrated_profile_fallback_uses_gps_only_playback_signals(self):
        processor = AdvancedIMUProcessor()
        timestamps = [0.0, 0.1, 0.2]
        zeros = [0.0, 0.0, 0.0]
        speeds = [60.0, 60.0, 60.0]
        lats = [12.0, 12.0, 12.0]
        lons = [77.0, 77.0001, 77.0002]
        profile = {
            "id": "mock",
            "label": "mock",
            "rotation_matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            "gyro_bias": [0.0, 0.0, 0.0],
            "accel_bias": [0.0, 0.0, 0.0],
            "gravity_vector": [0.0, 0.0, 1.0],
            "quality_score": 0.9,
        }

        calibrated = {
            "lean_angle": [1.0, 1.0, 1.0],
            "ax_cg": [0.1, 0.1, 0.1],
            "ay_cg": [0.2, 0.2, 0.2],
            "acceleration_g": [0.1, 0.1, 0.1],
            "braking_g": [0.0, 0.0, 0.0],
            "lateral_g": [0.2, 0.2, 0.2],
            "az_cg": [1.0, 1.0, 1.0],
            "mount_confidence": "HIGH",
        }
        gps_only = {
            "lean_angle": [8.0, 8.5, 9.0],
            "ax_cg": [0.3, 0.4, 0.5],
            "ay_cg": [0.0, 0.0, 0.0],
            "acceleration_g": [0.3, 0.4, 0.5],
            "braking_g": [0.0, 0.0, 0.0],
            "lateral_g": [0.0, 0.0, 0.0],
            "az_cg": [1.0, 1.0, 1.0],
        }

        with patch.object(processor, "_build_gps_features", return_value={
            "speeds": speeds,
            "gps_accel_g": [0.0, 0.0, 0.0],
            "yaw_rate_deg_s": [0.0, 0.0, 0.0],
            "straight_mask": [True, True, True],
            "turn_mask": [False, False, False],
            "heading_quality": 1.0,
        }), patch.object(processor, "_build_gps_reference_payload", return_value={"gps_lean_deg": [0.0, 0.0, 0.0], "gps_long_g": [0.0, 0.0, 0.0]}), patch.object(processor, "_compute_calibrated_profile_outputs", return_value=calibrated), patch.object(processor, "_compute_gps_fallback", return_value=gps_only), patch.object(processor._validation, "validate", side_effect=[
            {"score": 10.0, "passed": False, "failures": ["mock fail"]},
            {"score": 40.0, "passed": True, "failures": []},
        ]):
            result = processor.process(
                timestamps=timestamps,
                ax_raw=zeros,
                ay_raw=zeros,
                az_raw=[1.0, 1.0, 1.0],
                gx_raw=zeros,
                gy_raw=zeros,
                gz_raw=zeros,
                speeds=speeds,
                lats=lats,
                lons=lons,
                calibration_profile=profile,
                runtime_validation={"source_mode": "imu_trusted"},
            )

        self.assertEqual(result["diagnostics"]["selected_algorithm"], "gps_primary")
        self.assertEqual(result["playback_signals"]["lean_deg"], gps_only["lean_angle"])
        self.assertEqual(result["playback_signals"]["long_g"], gps_only["ax_cg"])


if __name__ == "__main__":
    unittest.main()
