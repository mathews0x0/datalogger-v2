import math
import unittest

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


if __name__ == "__main__":
    unittest.main()
