import math
import statistics
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


G_FORCE = 9.81


def _dot(a: List[float], b: List[float]) -> float:
    return (a[0] * b[0]) + (a[1] * b[1]) + (a[2] * b[2])


def _cross(a: List[float], b: List[float]) -> List[float]:
    return [
        (a[1] * b[2]) - (a[2] * b[1]),
        (a[2] * b[0]) - (a[0] * b[2]),
        (a[0] * b[1]) - (a[1] * b[0]),
    ]


def _norm(v: List[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _normalize(v: List[float], fallback: Optional[List[float]] = None) -> List[float]:
    mag = _norm(v)
    if mag <= 1e-9:
        return list(fallback or [0.0, 0.0, 1.0])
    return [x / mag for x in v]


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _variance(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    try:
        return statistics.variance(values)
    except statistics.StatisticsError:
        return 0.0


def _pearson(xs: List[float], ys: List[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 3:
        return 0.0

    mean_x = _mean(xs)
    mean_y = _mean(ys)
    num = 0.0
    den_x = 0.0
    den_y = 0.0

    for x, y in zip(xs, ys):
        dx = x - mean_x
        dy = y - mean_y
        num += dx * dy
        den_x += dx * dx
        den_y += dy * dy

    if den_x <= 1e-9 or den_y <= 1e-9:
        return 0.0
    return num / math.sqrt(den_x * den_y)


def _unwrap_angles_deg(headings: List[float]) -> List[float]:
    if not headings:
        return []

    unwrapped = [headings[0]]
    for heading in headings[1:]:
        prev = unwrapped[-1]
        delta = heading - (prev % 360.0)
        while delta > 180.0:
            delta -= 360.0
        while delta < -180.0:
            delta += 360.0
        unwrapped.append(prev + delta)
    return unwrapped


def _smooth_series(values: List[float], window: int) -> List[float]:
    if window <= 1 or not values:
        return list(values)

    q: deque[float] = deque(maxlen=window)
    smoothed: List[float] = []
    for value in values:
        q.append(value)
        smoothed.append(sum(q) / len(q))
    return smoothed


def _median(values: List[float]) -> float:
    if not values:
        return 0.0
    return statistics.median(values)


def _despike_series(values: List[float], window: int, threshold: float) -> List[float]:
    if window <= 1 or len(values) < 5:
        return list(values)

    half = max(1, window // 2)
    cleaned = list(values)
    for i in range(len(values)):
        left = max(0, i - half)
        right = min(len(values), i + half + 1)
        neighborhood = values[left:right]
        local_median = _median(neighborhood)
        deviations = [abs(v - local_median) for v in neighborhood]
        mad = _median(deviations)
        scale = max(0.01, 1.4826 * mad)
        if abs(values[i] - local_median) > threshold * scale:
            cleaned[i] = local_median
    return cleaned


def _min_duration_mask(mask: List[bool], min_samples: int) -> List[bool]:
    if min_samples <= 1 or not mask:
        return list(mask)

    out = [False] * len(mask)
    start = None
    for i, value in enumerate(mask + [False]):
        if value and start is None:
            start = i
        elif not value and start is not None:
            if i - start >= min_samples:
                for j in range(start, i):
                    out[j] = True
            start = None
    return out


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_r = math.radians(lat1)
    lon1_r = math.radians(lon1)
    lat2_r = math.radians(lat2)
    lon2_r = math.radians(lon2)

    dlon = lon2_r - lon1_r
    x = math.sin(dlon) * math.cos(lat2_r)
    y = (math.cos(lat1_r) * math.sin(lat2_r)) - (math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlon))
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    lat1_r = math.radians(lat1)
    lon1_r = math.radians(lon1)
    lat2_r = math.radians(lat2)
    lon2_r = math.radians(lon2)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = math.sin(dlat / 2.0) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * (math.sin(dlon / 2.0) ** 2)
    return 2.0 * r * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def _median_dt_seconds(timestamps: List[float]) -> float:
    if len(timestamps) < 2:
        return 0.01

    deltas = [timestamps[i] - timestamps[i - 1] for i in range(1, len(timestamps)) if timestamps[i] > timestamps[i - 1]]
    if not deltas:
        return 0.01

    median_dt = statistics.median(deltas)
    if median_dt > 2.0:
        return median_dt / 1000.0
    return median_dt


@dataclass
class IMUConfig:
    cog_offset: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.15])
    sample_rate_est: float = 100.0
    lean_warning_deg: float = 55.0
    lean_fail_deg: float = 60.0
    straight_speed_min_kmh: float = 25.0
    straight_heading_rate_max_deg_s: float = 3.0
    static_window_sec: float = 2.5
    static_accel_var_max: float = 0.015
    static_gyro_var_max: float = 25.0
    forward_prior_weight: float = 0.25
    imu_despike_window: int = 9
    imu_accel_despike_threshold: float = 3.5
    imu_gyro_despike_threshold: float = 4.0


@dataclass
class EvidenceWindow:
    start: int
    end: int
    duration_s: float
    kind: str
    score: float = 0.0


class IMUValidationEngine:
    def __init__(self, config: Optional[IMUConfig] = None):
        self.config = config or IMUConfig()

    def validate(
        self,
        lean_angle: List[float],
        acceleration_g: List[float],
        braking_g: List[float],
        lateral_g: List[float],
        vertical_g: List[float],
        speeds: List[float],
        straight_mask: List[bool],
        gps_longitudinal_g: List[float],
        yaw_rate_deg_s: List[float],
        mount_confidence: str,
    ) -> Dict[str, Any]:
        failures: List[str] = []
        warnings: List[str] = []
        score = 100.0

        if any(abs(v) > self.config.lean_fail_deg for v in lean_angle):
            failures.append(f"lean exceeded {self.config.lean_fail_deg:.0f} degrees")
            score -= 60.0

        near_limit = sum(1 for v in lean_angle if abs(v) >= self.config.lean_warning_deg)
        if near_limit > max(5, len(lean_angle) // 50):
            turn_supported = sum(
                1
                for i, v in enumerate(lean_angle)
                if abs(v) >= self.config.lean_warning_deg and abs(yaw_rate_deg_s[i]) >= 5.0 and speeds[i] >= 40.0
            )
            if turn_supported < max(3, near_limit // 3):
                failures.append("high lean spikes lack matching turn evidence")
                score -= 25.0
            else:
                warnings.append("lean approached physical limit")
                score -= 10.0

        extreme_lean_samples = sum(1 for v in lean_angle if abs(v) >= 57.5)
        if extreme_lean_samples > max(3, len(lean_angle) // 80):
            strong_turn_supported = sum(
                1
                for i, v in enumerate(lean_angle)
                if abs(v) >= 57.5 and abs(yaw_rate_deg_s[i]) >= 8.0 and speeds[i] >= 55.0
            )
            if strong_turn_supported < max(2, extreme_lean_samples // 2):
                failures.append("extreme lean lacks strong turn evidence")
                score -= 20.0
            else:
                warnings.append("lean spent sustained time in extreme range")
                score -= 8.0

        contradiction_count = 0
        for accel, brake, gps_long in zip(acceleration_g, braking_g, gps_longitudinal_g):
            if brake > 0.15 and gps_long > 0.12:
                contradiction_count += 1
            elif accel > 0.15 and gps_long < -0.12:
                contradiction_count += 1
        if contradiction_count > max(10, len(lean_angle) // 80):
            failures.append("accel/brake sign contradicts GPS speed derivative")
            score -= 20.0

        gps_brake_samples = 0
        matched_brake_samples = 0
        false_brake_samples = 0
        for brake, gps_long, speed in zip(braking_g, gps_longitudinal_g, speeds):
            if speed < 15.0:
                continue
            gps_braking = gps_long <= -0.06
            imu_braking = brake >= 0.05
            if gps_braking:
                gps_brake_samples += 1
                if imu_braking:
                    matched_brake_samples += 1
            elif imu_braking and gps_long > -0.02:
                false_brake_samples += 1

        brake_match_ratio = (
            matched_brake_samples / gps_brake_samples
            if gps_brake_samples > 0
            else 1.0
        )
        if gps_brake_samples >= max(12, len(braking_g) // 120):
            if brake_match_ratio < 0.35:
                failures.append("braking does not align with GPS speed drop")
                score -= 20.0
            elif brake_match_ratio < 0.55:
                warnings.append("braking only weakly matches GPS speed drop")
                score -= 8.0
        if false_brake_samples > max(20, len(braking_g) // 80):
            warnings.append("braking detected without matching GPS speed drop")
            score -= 8.0

        lateral_mismatch = 0
        for lean, lat in zip(lean_angle, lateral_g):
            expected_lat = math.tan(math.radians(_clamp(lean, -60.0, 60.0)))
            if abs(expected_lat - lat) > 0.45:
                lateral_mismatch += 1
        if lateral_mismatch > max(10, len(lean_angle) // 40):
            failures.append("lateral g inconsistent with lean angle")
            score -= 20.0

        straight_lean_samples = sum(
            1
            for is_straight, speed, lean in zip(straight_mask, speeds, lean_angle)
            if is_straight and speed >= self.config.straight_speed_min_kmh and abs(lean) > 12.0
        )
        if straight_lean_samples > max(10, len(lean_angle) // 60):
            failures.append("prolonged non-zero lean detected on straights")
            score -= 15.0

        if vertical_g:
            low_dynamic_idxs = [
                i for i, (gps_long, yaw) in enumerate(zip(gps_longitudinal_g, yaw_rate_deg_s))
                if abs(gps_long) < 0.05 and abs(yaw) < 2.0 and speeds[i] >= 20.0
            ]
            if len(low_dynamic_idxs) >= 20:
                vertical_samples = [vertical_g[i] for i in low_dynamic_idxs]
                mean_vertical = _mean(vertical_samples)
                if abs(mean_vertical - 1.0) > 0.2:
                    warnings.append("vertical load inconsistent in low-dynamic windows")
                    score -= 8.0

        lean_rate_fail = 0
        if len(lean_angle) > 1:
            dt = 1.0 / max(1.0, self.config.sample_rate_est)
            for i in range(1, len(lean_angle)):
                rate = abs(lean_angle[i] - lean_angle[i - 1]) / dt
                if rate > 220.0:
                    lean_rate_fail += 1
        if lean_rate_fail > max(5, len(lean_angle) // 100):
            warnings.append("lean rate contains unrealistic spikes")
            score -= 10.0

        net_force = [a - b for a, b in zip(acceleration_g, braking_g)]
        switches = 0
        prev_sign = 0
        for value in net_force:
            sign = 1 if value > 0.05 else -1 if value < -0.05 else 0
            if sign and prev_sign and sign != prev_sign:
                switches += 1
            if sign:
                prev_sign = sign
        duration_s = len(net_force) / max(1.0, self.config.sample_rate_est)
        switches_per_10s = (switches / duration_s) * 10.0 if duration_s > 0 else 0.0
        if switches_per_10s > 6.0:
            warnings.append("accel/brake output switches too frequently")
            score -= 8.0

        if mount_confidence == "HIGH" and failures:
            failures.append("high confidence mount estimate failed physical validation")
            score -= 20.0

        score = _clamp(score, 0.0, 100.0)
        return {
            "passed": not failures,
            "score": round(score, 1),
            "failures": failures,
            "warnings": warnings,
            "max_abs_lean_deg": round(max((abs(v) for v in lean_angle), default=0.0), 2),
            "straight_lean_samples": straight_lean_samples,
            "sign_contradictions": contradiction_count,
            "gps_brake_samples": gps_brake_samples,
            "matched_brake_samples": matched_brake_samples,
            "brake_match_ratio": round(brake_match_ratio, 3),
            "false_brake_samples": false_brake_samples,
            "lateral_mismatch_samples": lateral_mismatch,
            "switches_per_10s": round(switches_per_10s, 2),
        }


class AdvancedIMUProcessor:
    """
    Evidence-gated per-session mount resolver with validation-aware fallback.
    """

    def __init__(self, imu_smoothing_window: int = 50):
        self.config = IMUConfig()
        self.imu_smoothing_window = imu_smoothing_window
        self.rot_X = [1.0, 0.0, 0.0]
        self.rot_Y = [0.0, 1.0, 0.0]
        self.rot_Z = [0.0, 0.0, 1.0]
        self.gx_bias = 0.0
        self.gy_bias = 0.0
        self.gz_bias = 0.0
        self._validation = IMUValidationEngine(self.config)

    def process(
        self,
        timestamps: List[float],
        ax_raw: List[float],
        ay_raw: List[float],
        az_raw: List[float],
        gx_raw: List[float],
        gy_raw: List[float],
        gz_raw: List[float],
        speeds: Optional[List[float]] = None,
        lats: Optional[List[float]] = None,
        lons: Optional[List[float]] = None,
        calibration_profile: Optional[Dict[str, Any]] = None,
        runtime_validation: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not timestamps:
            return self._empty_result()

        speeds = list(speeds or [0.0] * len(timestamps))
        lats = list(lats or [0.0] * len(timestamps))
        lons = list(lons or [0.0] * len(timestamps))

        dt = _median_dt_seconds(timestamps)
        self.config.sample_rate_est = 1.0 / dt if dt > 0 else 100.0

        gps_features = self._build_gps_features(timestamps, speeds, lats, lons)
        if calibration_profile and calibration_profile.get("rotation_matrix"):
            calibrated = self._compute_calibrated_profile_outputs(
                timestamps=timestamps,
                ax_raw=ax_raw,
                ay_raw=ay_raw,
                az_raw=az_raw,
                gx_raw=gx_raw,
                gy_raw=gy_raw,
                gz_raw=gz_raw,
                gps_features=gps_features,
                calibration_profile=calibration_profile,
                runtime_validation=runtime_validation,
            )
            calibrated["validation"] = self._validation.validate(
                lean_angle=calibrated["lean_angle"],
                acceleration_g=calibrated["acceleration_g"],
                braking_g=calibrated["braking_g"],
                lateral_g=calibrated["lateral_g"],
                vertical_g=calibrated["az_cg"],
                speeds=speeds,
                straight_mask=gps_features["straight_mask"],
                gps_longitudinal_g=gps_features["gps_accel_g"],
                yaw_rate_deg_s=gps_features["yaw_rate_deg_s"],
                mount_confidence=calibrated.get("mount_confidence", "HIGH"),
            )
            calibrated["diagnostics"] = {
                "selected_algorithm": "calibrated_profile",
                "candidate_scores": {"calibrated_profile": calibrated["validation"]["score"]},
                "candidate_pass": {"calibrated_profile": calibrated["validation"]["passed"]},
            }
            if not calibrated["validation"]["passed"]:
                gps_only = self._compute_gps_fallback(gps_features)
                gps_only["mount_confidence"] = "LOW"
                gps_only["mount_method"] = "gps_primary_after_calibrated_profile_failure"
                gps_only["rotation_matrix"] = calibrated.get("rotation_matrix", [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
                gps_only["gyro_bias"] = calibrated.get("gyro_bias", [0.0, 0.0, 0.0])
                gps_only["gravity_vector"] = calibrated.get("gravity_vector", [0.0, 0.0, 1.0])
                gps_only["evidence_summary"] = {
                    "source": "gps_fallback",
                    "reason": "calibrated_profile_validation_failed",
                    "calibrated_profile_failures": calibrated["validation"].get("failures", []),
                }
                gps_only["confidence"] = 0.35
                gps_only["validation"] = self._validation.validate(
                    lean_angle=gps_only["lean_angle"],
                    acceleration_g=gps_only["acceleration_g"],
                    braking_g=gps_only["braking_g"],
                    lateral_g=gps_only["lateral_g"],
                    vertical_g=gps_only["az_cg"],
                    speeds=speeds,
                    straight_mask=gps_features["straight_mask"],
                    gps_longitudinal_g=gps_features["gps_accel_g"],
                    yaw_rate_deg_s=gps_features["yaw_rate_deg_s"],
                    mount_confidence="LOW",
                )
                gps_only["diagnostics"] = {
                    "selected_algorithm": "gps_primary",
                    "candidate_scores": {
                        "calibrated_profile": calibrated["validation"]["score"],
                        "gps_primary": gps_only["validation"]["score"],
                    },
                    "candidate_pass": {
                        "calibrated_profile": False,
                        "gps_primary": gps_only["validation"]["passed"],
                    },
                }
                gps_only["primary_validation"] = calibrated["validation"]
                if gps_only["validation"]["score"] > calibrated["validation"]["score"]:
                    return gps_only
            return calibrated
        mount = self._resolve_mount(
            timestamps=timestamps,
            ax_raw=ax_raw,
            ay_raw=ay_raw,
            az_raw=az_raw,
            gx_raw=gx_raw,
            gy_raw=gy_raw,
            gz_raw=gz_raw,
            gps_features=gps_features,
        )

        self.rot_X = mount["rotation_matrix"][0]
        self.rot_Y = mount["rotation_matrix"][1]
        self.rot_Z = mount["rotation_matrix"][2]
        self.gx_bias, self.gy_bias, self.gz_bias = mount["gyro_bias"]

        primary = self._compute_orientation_outputs(
            timestamps=timestamps,
            ax_raw=ax_raw,
            ay_raw=ay_raw,
            az_raw=az_raw,
            gx_raw=gx_raw,
            gy_raw=gy_raw,
            gz_raw=gz_raw,
            speeds=speeds,
            gps_features=gps_features,
            imu_trust=self._imu_trust_from_confidence(mount["confidence_score"]),
        )
        primary["mount_confidence"] = mount["mount_confidence"]
        primary["mount_method"] = mount["mount_method"]
        primary["rotation_matrix"] = mount["rotation_matrix"]
        primary["gyro_bias"] = list(mount["gyro_bias"])
        primary["gravity_vector"] = list(mount["gravity_vector"])
        primary["evidence_summary"] = mount["evidence_summary"]
        primary["confidence"] = mount["confidence_score"]

        legacy = self._compute_legacy_outputs(
            timestamps=timestamps,
            ax_raw=ax_raw,
            ay_raw=ay_raw,
            az_raw=az_raw,
            gx_raw=gx_raw,
            gy_raw=gy_raw,
            gz_raw=gz_raw,
            speeds=speeds,
            gps_features=gps_features,
        )

        gps_only = self._compute_gps_fallback(gps_features)
        gps_only["mount_confidence"] = "LOW"
        gps_only["mount_method"] = "gps_primary"
        gps_only["rotation_matrix"] = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        gps_only["gyro_bias"] = [0.0, 0.0, 0.0]
        gps_only["gravity_vector"] = [0.0, 0.0, 1.0]
        gps_only["evidence_summary"] = {"source": "gps_only"}
        gps_only["confidence"] = 0.35

        candidates = [
            ("orientation_solver", primary),
            ("legacy_two_pass", legacy),
            ("gps_primary", gps_only),
        ]

        evaluated: List[Tuple[str, Dict[str, Any]]] = []
        for name, candidate in candidates:
            candidate["validation"] = self._validation.validate(
                lean_angle=candidate["lean_angle"],
                acceleration_g=candidate["acceleration_g"],
                braking_g=candidate["braking_g"],
                lateral_g=candidate["lateral_g"],
                vertical_g=candidate["az_cg"],
                speeds=speeds,
                straight_mask=gps_features["straight_mask"],
                gps_longitudinal_g=gps_features["gps_accel_g"],
                yaw_rate_deg_s=gps_features["yaw_rate_deg_s"],
                mount_confidence=candidate.get("mount_confidence", "LOW"),
            )
            evaluated.append((name, candidate))

        selected_name, selected = self._select_best_candidate(evaluated)
        selected["diagnostics"] = {
            "selected_algorithm": selected_name,
            "candidate_scores": {name: candidate["validation"]["score"] for name, candidate in evaluated},
            "candidate_pass": {name: candidate["validation"]["passed"] for name, candidate in evaluated},
        }
        if selected_name != "orientation_solver":
            selected["primary_validation"] = primary["validation"]
        return selected

    def _resolve_mount(
        self,
        timestamps: List[float],
        ax_raw: List[float],
        ay_raw: List[float],
        az_raw: List[float],
        gx_raw: List[float],
        gy_raw: List[float],
        gz_raw: List[float],
        gps_features: Dict[str, List[float]],
    ) -> Dict[str, Any]:
        startup = self._resolve_startup_calibration(
            ax_raw=ax_raw,
            ay_raw=ay_raw,
            az_raw=az_raw,
            gx_raw=gx_raw,
            gy_raw=gy_raw,
            gz_raw=gz_raw,
            gps_features=gps_features,
        )

        if startup:
            gravity_vector = startup["gravity_vector"]
            gyro_bias = startup["gyro_bias"]
            method = f"{startup['method']}_frontfacing"
            static_seconds = startup["static_seconds"]
            startup_forward = startup["forward_vector"]
            startup_forward_score = startup["forward_score"]
            startup_rollout_seconds = startup["rollout_seconds"]
        else:
            static_windows = self._find_static_windows(ax_raw, ay_raw, az_raw, gx_raw, gy_raw, gz_raw)
            if static_windows:
                best_static = static_windows[0]
                gravity_vector = self._mean_vector(ax_raw, ay_raw, az_raw, best_static.start, best_static.end)
                gyro_bias = self._mean_vector(gx_raw, gy_raw, gz_raw, best_static.start, best_static.end)
                method = "static_window_frontfacing"
                static_seconds = sum(window.duration_s for window in static_windows)
            else:
                best_dynamic = self._find_low_dynamic_window(ax_raw, ay_raw, az_raw, gps_features)
                gravity_vector = self._mean_vector(ax_raw, ay_raw, az_raw, best_dynamic.start, best_dynamic.end)
                gyro_bias = self._mean_vector(gx_raw, gy_raw, gz_raw, best_dynamic.start, best_dynamic.end)
                method = "ride_derived_frontfacing"
                static_seconds = 0.0
            startup_forward = None
            startup_forward_score = 0.0
            startup_rollout_seconds = 0.0

        up_vector = _normalize(gravity_vector, [0.0, 0.0, 1.0])
        forward_vector = self._project_sensor_forward_prior(up_vector)
        brake_anchor = self._find_hard_brake_anchor(
            ax_raw=ax_raw,
            ay_raw=ay_raw,
            az_raw=az_raw,
            up_vector=up_vector,
            gps_accel_g=gps_features["gps_accel_g"],
            yaw_rate_deg_s=gps_features["yaw_rate_deg_s"],
            speeds=gps_features["speeds"],
        )

        brake_seconds = 0.0
        rollout_alignment = 0.0
        brake_alignment = 0.0

        # Front-facing mount is now a hard assumption. We use ride-derived
        # forward vectors only to validate the canonical direction, not to
        # redefine it per session.
        forward_score = 0.55 if startup else 0.45

        if startup_forward is not None and startup_forward_score > 0.0:
            rollout_alignment = _dot(startup_forward, forward_vector)
            if rollout_alignment >= 0.6:
                forward_score += 0.20 * min(1.0, startup_forward_score)
                method = f"{method}+rollout_confirmed"
            elif rollout_alignment <= -0.35:
                forward_score -= 0.20
                method = f"{method}+rollout_conflict"

        if brake_anchor is not None:
            brake_seconds = brake_anchor["duration_s"]
            brake_alignment = _dot(brake_anchor["forward_vector"], forward_vector)
            if brake_alignment >= 0.6:
                forward_score += 0.20 * min(1.0, brake_anchor["score"])
                method = f"{method}+hard_brake_confirmed"
            elif brake_alignment <= -0.35:
                forward_score -= 0.25
                method = f"{method}+hard_brake_conflict"
            else:
                forward_score -= 0.05

        if forward_score < 0.25:
            method = "gps_only_fallback"

        lateral_vector = _normalize(_cross(up_vector, forward_vector), [0.0, 1.0, 0.0])
        forward_vector = _normalize(_cross(lateral_vector, up_vector), [1.0, 0.0, 0.0])

        straight_seconds = self._mask_duration(gps_features["straight_mask"])
        turn_seconds = self._mask_duration(gps_features["turn_mask"])
        longitudinal_events = self._count_longitudinal_events(gps_features["gps_accel_g"])

        confidence_score = self._score_mount_confidence(
            static_seconds=static_seconds,
            straight_seconds=straight_seconds,
            turn_seconds=turn_seconds,
            forward_score=forward_score,
            longitudinal_events=longitudinal_events,
            brake_seconds=brake_seconds,
            brake_score=max(0.0, brake_alignment),
            method=method,
        )

        mount_confidence = "HIGH" if confidence_score >= 0.8 else "MEDIUM" if confidence_score >= 0.55 else "LOW"
        if method == "gps_only_fallback":
            mount_confidence = "LOW"

        return {
            "rotation_matrix": [forward_vector, lateral_vector, up_vector],
            "gyro_bias": gyro_bias,
            "gravity_vector": gravity_vector,
            "mount_method": method,
            "mount_confidence": mount_confidence,
            "confidence_score": round(confidence_score, 2),
            "evidence_summary": {
                "static_seconds_used": round(static_seconds, 2),
                "straight_seconds_used": round(straight_seconds, 2),
                "turn_seconds_used": round(turn_seconds, 2),
                "longitudinal_event_count": longitudinal_events,
                "forward_fit_score": round(forward_score, 3),
                "startup_rollout_seconds": round(startup_rollout_seconds, 2),
                "hard_brake_seconds": round(brake_seconds, 2),
                "hard_brake_score": round(max(0.0, brake_alignment), 3),
                "rollout_alignment": round(rollout_alignment, 3),
                "brake_alignment": round(brake_alignment, 3),
                "gps_heading_quality": round(gps_features["heading_quality"], 3),
            },
        }

    def _resolve_startup_calibration(
        self,
        ax_raw: List[float],
        ay_raw: List[float],
        az_raw: List[float],
        gx_raw: List[float],
        gy_raw: List[float],
        gz_raw: List[float],
        gps_features: Dict[str, List[float]],
    ) -> Optional[Dict[str, Any]]:
        startup_samples = min(len(ax_raw), max(50, int(self.config.sample_rate_est * 15.0)))
        if startup_samples < max(20, int(self.config.sample_rate_est * 2.0)):
            return None

        startup_static = self._find_startup_static_window(
            ax_raw=ax_raw,
            ay_raw=ay_raw,
            az_raw=az_raw,
            gx_raw=gx_raw,
            gy_raw=gy_raw,
            gz_raw=gz_raw,
            speeds=gps_features["speeds"],
            yaw_rate=gps_features["yaw_rate_deg_s"],
            limit=startup_samples,
        )
        startup_dynamic = self._find_startup_low_dynamic_window(
            ax_raw=ax_raw,
            ay_raw=ay_raw,
            az_raw=az_raw,
            gx_raw=gx_raw,
            gy_raw=gy_raw,
            gz_raw=gz_raw,
            speeds=gps_features["speeds"],
            yaw_rate=gps_features["yaw_rate_deg_s"],
            limit=startup_samples,
        )

        if startup_static is not None:
            gravity_vector = self._mean_vector(ax_raw, ay_raw, az_raw, startup_static.start, startup_static.end)
            gyro_bias = self._mean_vector(gx_raw, gy_raw, gz_raw, startup_static.start, startup_static.end)
            static_seconds = startup_static.duration_s
            method = "startup_static"
        elif startup_dynamic is not None:
            gravity_vector = self._mean_vector(ax_raw, ay_raw, az_raw, startup_dynamic.start, startup_dynamic.end)
            gyro_bias = self._mean_vector(gx_raw, gy_raw, gz_raw, startup_dynamic.start, startup_dynamic.end)
            static_seconds = 0.0
            method = "startup_rollout_only"
        else:
            return None

        up_vector = _normalize(list(gravity_vector), [0.0, 0.0, 1.0])

        rollout_mask = [
            (
                i < startup_samples
                and gps_features["speeds"][i] >= 1.0
                and gps_features["speeds"][i] <= 30.0
                and abs(gps_features["yaw_rate_deg_s"][i]) <= 2.5
            )
            for i in range(len(ax_raw))
        ]
        rollout_mask = _min_duration_mask(rollout_mask, max(1, int(self.config.sample_rate_est * 1.5)))

        rollout_seconds = self._mask_duration(rollout_mask)
        if rollout_seconds > 0.5:
            forward_candidates = self._project_forward_candidates(
                ax_raw=ax_raw,
                ay_raw=ay_raw,
                az_raw=az_raw,
                up_vector=up_vector,
                gps_accel_g=gps_features["gps_accel_g"],
                straight_mask=rollout_mask,
                speeds=gps_features["speeds"],
            )
            forward_vector, forward_score = self._select_forward_axis(forward_candidates)
        else:
            forward_vector, forward_score = [1.0, 0.0, 0.0], 0.0

        if rollout_seconds > 0.5 and forward_score >= 0.2:
            method = "startup_static+rollout" if startup_static is not None else "startup_rollout_only"

        return {
            "gravity_vector": gravity_vector,
            "gyro_bias": gyro_bias,
            "forward_vector": forward_vector if forward_score > 0.0 else None,
            "forward_score": forward_score,
            "static_seconds": static_seconds,
            "rollout_seconds": rollout_seconds,
            "method": method,
        }

    def _find_startup_static_window(
        self,
        ax_raw: List[float],
        ay_raw: List[float],
        az_raw: List[float],
        gx_raw: List[float],
        gy_raw: List[float],
        gz_raw: List[float],
        speeds: List[float],
        yaw_rate: List[float],
        limit: int,
    ) -> Optional[EvidenceWindow]:
        window_size = max(20, int(self.config.sample_rate_est * 2.0))
        step = max(5, window_size // 4)
        best: Optional[EvidenceWindow] = None

        for start in range(0, max(1, limit - window_size + 1), step):
            end = start + window_size
            accel_mag = [
                math.sqrt((ax_raw[i] * ax_raw[i]) + (ay_raw[i] * ay_raw[i]) + (az_raw[i] * az_raw[i]))
                for i in range(start, end)
            ]
            gyro_mag = [
                math.sqrt((gx_raw[i] * gx_raw[i]) + (gy_raw[i] * gy_raw[i]) + (gz_raw[i] * gz_raw[i]))
                for i in range(start, end)
            ]
            speed_mean = _mean(speeds[start:end])
            yaw_mean = _mean([abs(v) for v in yaw_rate[start:end]])
            accel_var = _variance(accel_mag)
            gyro_var = _variance(gyro_mag)
            gravity_error = abs(_mean(accel_mag) - 1.0)

            if speed_mean > 8.0 or yaw_mean > 3.0:
                continue
            if accel_var > 0.02 or gyro_var > 30.0 or gravity_error > 0.12:
                continue

            score = 1.0
            score -= accel_var * 15.0
            score -= min(0.4, gyro_var / 30.0)
            score -= min(0.4, gravity_error / 0.12)
            score -= min(0.2, speed_mean / 10.0)

            candidate = EvidenceWindow(
                start=start,
                end=end,
                duration_s=window_size / max(1.0, self.config.sample_rate_est),
                kind="startup_static",
                score=score,
            )
            if best is None or candidate.score > best.score:
                best = candidate

        return best

    def _find_startup_low_dynamic_window(
        self,
        ax_raw: List[float],
        ay_raw: List[float],
        az_raw: List[float],
        gx_raw: List[float],
        gy_raw: List[float],
        gz_raw: List[float],
        speeds: List[float],
        yaw_rate: List[float],
        limit: int,
    ) -> Optional[EvidenceWindow]:
        window_size = max(20, int(self.config.sample_rate_est * 2.0))
        step = max(5, window_size // 4)
        best: Optional[EvidenceWindow] = None

        for start in range(0, max(1, limit - window_size + 1), step):
            end = start + window_size
            accel_mag = [
                math.sqrt((ax_raw[i] * ax_raw[i]) + (ay_raw[i] * ay_raw[i]) + (az_raw[i] * az_raw[i]))
                for i in range(start, end)
            ]
            speed_mean = _mean(speeds[start:end])
            yaw_mean = _mean([abs(v) for v in yaw_rate[start:end]])
            accel_var = _variance(accel_mag)
            gx_var = _variance(gx_raw[start:end])
            gy_var = _variance(gy_raw[start:end])
            gz_var = _variance(gz_raw[start:end])
            gyro_axis_var = gx_var + gy_var + gz_var
            gravity_error = abs(_mean(accel_mag) - 1.0)

            if speed_mean < 2.0 or speed_mean > 15.0 or yaw_mean > 2.5:
                continue
            if accel_var > 0.03 or gravity_error > 0.15:
                continue

            score = 1.0
            score -= accel_var * 12.0
            score -= min(0.4, gravity_error / 0.15)
            score -= min(0.2, abs(speed_mean - 6.0) / 12.0)
            score -= min(0.2, gyro_axis_var / 40000.0)

            candidate = EvidenceWindow(
                start=start,
                end=end,
                duration_s=window_size / max(1.0, self.config.sample_rate_est),
                kind="startup_low_dynamic",
                score=score,
            )
            if best is None or candidate.score > best.score:
                best = candidate

        return best

    def _build_gps_features(
        self,
        timestamps: List[float],
        speeds: List[float],
        lats: List[float],
        lons: List[float],
    ) -> Dict[str, List[float]]:
        dt = _median_dt_seconds(timestamps)
        speeds_ms = [s / 3.6 for s in speeds]

        gps_accel = [0.0] * len(speeds_ms)
        for i in range(1, len(speeds_ms) - 1):
            dv = speeds_ms[i + 1] - speeds_ms[i - 1]
            gps_accel[i] = dv / (2.0 * dt) if dt > 0 else 0.0
        if len(gps_accel) > 1:
            gps_accel[0] = gps_accel[1]
            gps_accel[-1] = gps_accel[-2]
        gps_accel_g = [value / G_FORCE for value in _smooth_series(gps_accel, max(1, int(self.config.sample_rate_est // 4)))]

        headings, yaw_rate = self._build_stable_heading_and_yaw(timestamps, speeds, lats, lons)

        raw_straight_mask = [
            speed >= self.config.straight_speed_min_kmh and abs(yaw) <= 1.5
            for speed, yaw in zip(speeds, yaw_rate)
        ]
        raw_turn_mask = [speed >= 35.0 and abs(yaw) >= 4.0 for speed, yaw in zip(speeds, yaw_rate)]
        straight_mask = _min_duration_mask(raw_straight_mask, max(1, int(self.config.sample_rate_est * 3.0)))
        turn_mask = _min_duration_mask(raw_turn_mask, max(1, int(self.config.sample_rate_est * 1.0)))

        heading_quality_samples = [
            abs(yaw)
            for speed, yaw, lat, lon in zip(speeds, yaw_rate, lats, lons)
            if speed >= self.config.straight_speed_min_kmh and lat != 0.0 and lon != 0.0
        ]
        mean_heading_noise = _mean(heading_quality_samples) if heading_quality_samples else 99.0
        heading_quality = _clamp(1.0 - (mean_heading_noise / 15.0), 0.0, 1.0)

        return {
            "speeds": speeds,
            "speeds_ms": speeds_ms,
            "gps_accel_g": gps_accel_g,
            "headings_deg": headings,
            "yaw_rate_deg_s": yaw_rate,
            "straight_mask": straight_mask,
            "turn_mask": turn_mask,
            "heading_quality": heading_quality,
        }

    def _find_hard_brake_anchor(
        self,
        ax_raw: List[float],
        ay_raw: List[float],
        az_raw: List[float],
        up_vector: List[float],
        gps_accel_g: List[float],
        yaw_rate_deg_s: List[float],
        speeds: List[float],
    ) -> Optional[Dict[str, Any]]:
        window_size = max(40, int(self.config.sample_rate_est * 1.5))
        step = max(10, window_size // 4)
        best: Optional[Dict[str, Any]] = None

        for start in range(0, max(1, len(ax_raw) - window_size + 1), step):
            end = start + window_size
            speed_mean = _mean(speeds[start:end])
            gps_brake = [-value for value in gps_accel_g[start:end]]
            gps_brake_mean = _mean(gps_brake)
            yaw_mean = _mean([abs(v) for v in yaw_rate_deg_s[start:end]])

            if speed_mean < 35.0 or gps_brake_mean < 0.08 or yaw_mean > 10.0:
                continue

            accel_mean = self._mean_vector(ax_raw, ay_raw, az_raw, start, end)
            horizontal = [
                accel_mean[0] - (_dot(accel_mean, up_vector) * up_vector[0]),
                accel_mean[1] - (_dot(accel_mean, up_vector) * up_vector[1]),
                accel_mean[2] - (_dot(accel_mean, up_vector) * up_vector[2]),
            ]
            horizontal_mag = _norm(horizontal)
            if horizontal_mag < 0.04:
                continue

            forward_vector = _normalize([-horizontal[0], -horizontal[1], -horizontal[2]], [1.0, 0.0, 0.0])
            score = min(1.0, gps_brake_mean / 0.35)
            score *= min(1.0, (window_size / max(1.0, self.config.sample_rate_est)) / 2.5)
            score *= _clamp(1.0 - (yaw_mean / 12.0), 0.25, 1.0)
            score *= _clamp(horizontal_mag / 0.25, 0.25, 1.0)

            candidate = {
                "forward_vector": forward_vector,
                "score": score,
                "duration_s": window_size / max(1.0, self.config.sample_rate_est),
                "start": start,
                "end": end,
            }
            if best is None or candidate["score"] > best["score"]:
                best = candidate

        return best

    def _build_stable_heading_and_yaw(
        self,
        timestamps: List[float],
        speeds: List[float],
        lats: List[float],
        lons: List[float],
    ) -> Tuple[List[float], List[float]]:
        n = len(timestamps)
        if n == 0:
            return [], []

        dt = _median_dt_seconds(timestamps)
        sample_rate = max(1.0, self.config.sample_rate_est)
        look = max(5, int(sample_rate * 0.30))
        headings = [0.0] * n

        for i in range(n):
            left = max(0, i - look)
            right = min(n - 1, i + look)
            if right <= left:
                headings[i] = headings[i - 1] if i > 0 else 0.0
                continue

            lat1, lon1 = lats[left], lons[left]
            lat2, lon2 = lats[right], lons[right]
            moved_m = _haversine_m(lat1, lon1, lat2, lon2)
            if moved_m < 2.0 or speeds[i] < 8.0 or (lat1 == 0.0 and lon1 == 0.0) or (lat2 == 0.0 and lon2 == 0.0):
                headings[i] = headings[i - 1] if i > 0 else 0.0
                continue

            headings[i] = _bearing_deg(lat1, lon1, lat2, lon2)

        unwrapped = _unwrap_angles_deg(headings)
        yaw_rate = [0.0] * n
        yaw_look = max(5, int(sample_rate * 0.25))
        for i in range(n):
            left = max(0, i - yaw_look)
            right = min(n - 1, i + yaw_look)
            if right <= left:
                yaw_rate[i] = yaw_rate[i - 1] if i > 0 else 0.0
                continue
            delta_t = timestamps[right] - timestamps[left]
            if delta_t > 2.0:
                delta_t /= 1000.0
            if delta_t <= 0.0:
                yaw_rate[i] = yaw_rate[i - 1] if i > 0 else 0.0
                continue
            yaw_rate[i] = (unwrapped[right] - unwrapped[left]) / delta_t

        yaw_rate = _smooth_series(yaw_rate, max(3, int(sample_rate * 0.20)))
        yaw_rate = [_clamp(v, -85.0, 85.0) for v in yaw_rate]
        return headings, yaw_rate

    def _find_static_windows(
        self,
        ax_raw: List[float],
        ay_raw: List[float],
        az_raw: List[float],
        gx_raw: List[float],
        gy_raw: List[float],
        gz_raw: List[float],
    ) -> List[EvidenceWindow]:
        windows: List[EvidenceWindow] = []
        window_size = max(20, int(self.config.sample_rate_est * self.config.static_window_sec))
        step = max(5, window_size // 3)

        for start in range(0, max(1, len(ax_raw) - window_size + 1), step):
            end = start + window_size
            accel_mag = [
                math.sqrt((ax_raw[i] * ax_raw[i]) + (ay_raw[i] * ay_raw[i]) + (az_raw[i] * az_raw[i]))
                for i in range(start, end)
            ]
            gyro_mag = [
                math.sqrt((gx_raw[i] * gx_raw[i]) + (gy_raw[i] * gy_raw[i]) + (gz_raw[i] * gz_raw[i]))
                for i in range(start, end)
            ]
            accel_var = _variance(accel_mag)
            gyro_var = _variance(gyro_mag)
            score = 1.0 - min(1.0, (accel_var / max(self.config.static_accel_var_max, 1e-6)))
            score -= min(0.5, gyro_var / max(self.config.static_gyro_var_max, 1e-6))

            if accel_var <= self.config.static_accel_var_max and gyro_var <= self.config.static_gyro_var_max:
                windows.append(
                    EvidenceWindow(
                        start=start,
                        end=end,
                        duration_s=window_size / max(1.0, self.config.sample_rate_est),
                        kind="static",
                        score=score,
                    )
                )

        windows.sort(key=lambda window: window.score, reverse=True)
        return windows

    def _find_low_dynamic_window(
        self,
        ax_raw: List[float],
        ay_raw: List[float],
        az_raw: List[float],
        gps_features: Dict[str, List[float]],
    ) -> EvidenceWindow:
        window_size = max(30, int(self.config.sample_rate_est * 2.0))
        step = max(10, window_size // 2)
        best = EvidenceWindow(0, min(len(ax_raw), window_size), min(len(ax_raw), window_size) / max(1.0, self.config.sample_rate_est), "low_dynamic", -999.0)

        for start in range(0, max(1, len(ax_raw) - window_size + 1), step):
            end = start + window_size
            gps_long = gps_features["gps_accel_g"][start:end]
            yaw = gps_features["yaw_rate_deg_s"][start:end]
            accel_mag = [
                math.sqrt((ax_raw[i] * ax_raw[i]) + (ay_raw[i] * ay_raw[i]) + (az_raw[i] * az_raw[i]))
                for i in range(start, end)
            ]
            score = 0.0
            score -= _variance(accel_mag) * 10.0
            score -= _mean([abs(v) for v in gps_long]) * 2.0
            score -= _mean([abs(v) for v in yaw]) / 8.0
            if score > best.score:
                best = EvidenceWindow(
                    start=start,
                    end=end,
                    duration_s=window_size / max(1.0, self.config.sample_rate_est),
                    kind="low_dynamic",
                    score=score,
                )
        return best

    def _project_forward_candidates(
        self,
        ax_raw: List[float],
        ay_raw: List[float],
        az_raw: List[float],
        up_vector: List[float],
        gps_accel_g: List[float],
        straight_mask: List[bool],
        speeds: List[float],
        forward_prior: Optional[List[float]] = None,
    ) -> List[Tuple[List[float], float]]:
        basis = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, -1.0, 0.0], [-1.0, 0.0, 0.0]]
        candidates: List[Tuple[List[float], float]] = []

        usable_indices = [
            i
            for i, (is_straight, speed, gps_long) in enumerate(zip(straight_mask, speeds, gps_accel_g))
            if is_straight and speed >= self.config.straight_speed_min_kmh and abs(gps_long) >= 0.03
        ]

        if len(usable_indices) < 20:
            usable_indices = [i for i, gps_long in enumerate(gps_accel_g) if abs(gps_long) >= 0.05 and speeds[i] >= 30.0]

        for axis in basis:
            tangent = [
                axis[0] - (_dot(axis, up_vector) * up_vector[0]),
                axis[1] - (_dot(axis, up_vector) * up_vector[1]),
                axis[2] - (_dot(axis, up_vector) * up_vector[2]),
            ]
            tangent = _normalize(tangent, [1.0, 0.0, 0.0])
            imu_longitudinal = [
                _dot([ax_raw[i], ay_raw[i], az_raw[i]], tangent)
                for i in usable_indices
            ]
            gps_longitudinal = [gps_accel_g[i] for i in usable_indices]
            score = abs(_pearson(imu_longitudinal, gps_longitudinal))
            score *= min(1.0, len(usable_indices) / 120.0)
            sign = _pearson(imu_longitudinal, gps_longitudinal)
            if sign < 0:
                tangent = [-tangent[0], -tangent[1], -tangent[2]]
            if forward_prior is not None:
                alignment = _dot(tangent, forward_prior)
                score += self.config.forward_prior_weight * max(0.0, alignment)
            candidates.append((tangent, score))

        return candidates

    def _project_sensor_forward_prior(self, up_vector: List[float]) -> List[float]:
        sensor_x = [1.0, 0.0, 0.0]
        projected = [
            sensor_x[0] - (_dot(sensor_x, up_vector) * up_vector[0]),
            sensor_x[1] - (_dot(sensor_x, up_vector) * up_vector[1]),
            sensor_x[2] - (_dot(sensor_x, up_vector) * up_vector[2]),
        ]
        return _normalize(projected, [1.0, 0.0, 0.0])

    def _blend_direction_vectors(self, vector_a: List[float], vector_b: List[float], weight_b: float) -> List[float]:
        weight_b = _clamp(weight_b, 0.0, 1.0)
        weight_a = 1.0 - weight_b
        blended = [
            (weight_a * vector_a[0]) + (weight_b * vector_b[0]),
            (weight_a * vector_a[1]) + (weight_b * vector_b[1]),
            (weight_a * vector_a[2]) + (weight_b * vector_b[2]),
        ]
        return _normalize(blended, vector_a)

    def _select_forward_axis(self, candidates: List[Tuple[List[float], float]]) -> Tuple[List[float], float]:
        if not candidates:
            return [1.0, 0.0, 0.0], 0.0
        best_vector, best_score = max(candidates, key=lambda item: item[1])
        return best_vector, best_score

    def _compute_orientation_outputs(
        self,
        timestamps: List[float],
        ax_raw: List[float],
        ay_raw: List[float],
        az_raw: List[float],
        gx_raw: List[float],
        gy_raw: List[float],
        gz_raw: List[float],
        speeds: List[float],
        gps_features: Dict[str, List[float]],
        imu_trust: float = 0.6,
    ) -> Dict[str, Any]:
        ax_clean = _despike_series(ax_raw, self.config.imu_despike_window, self.config.imu_accel_despike_threshold)
        ay_clean = _despike_series(ay_raw, self.config.imu_despike_window, self.config.imu_accel_despike_threshold)
        az_clean = _despike_series(az_raw, self.config.imu_despike_window, self.config.imu_accel_despike_threshold)
        gx_clean = _despike_series(gx_raw, self.config.imu_despike_window, self.config.imu_gyro_despike_threshold)
        gy_clean = _despike_series(gy_raw, self.config.imu_despike_window, self.config.imu_gyro_despike_threshold)
        gz_clean = _despike_series(gz_raw, self.config.imu_despike_window, self.config.imu_gyro_despike_threshold)

        ax_q: deque[float] = deque(maxlen=self.imu_smoothing_window)
        ay_q: deque[float] = deque(maxlen=self.imu_smoothing_window)
        az_q: deque[float] = deque(maxlen=self.imu_smoothing_window)
        roll_rate_q: deque[float] = deque(maxlen=max(5, self.imu_smoothing_window // 2))

        lean_angle: List[float] = []
        ax_cg: List[float] = []
        ay_cg: List[float] = []
        az_cg: List[float] = []
        acceleration_g: List[float] = []
        braking_g: List[float] = []
        pitch_angle: List[float] = []
        yaw_angle: List[float] = []

        gps_lean_lp = 0.0
        imu_delta_lp = 0.0
        gps_long_lp = 0.0
        imu_long_delta_lp = 0.0
        imu_trust = _clamp(imu_trust, 0.2, 0.9)

        for i in range(len(timestamps)):
            accel_vec = [ax_clean[i], ay_clean[i], az_clean[i]]
            gyro_vec = [
                gx_clean[i] - self.gx_bias,
                gy_clean[i] - self.gy_bias,
                gz_clean[i] - self.gz_bias,
            ]

            a_long = _dot(accel_vec, self.rot_X)
            a_lat = _dot(accel_vec, self.rot_Y)
            a_up = _dot(accel_vec, self.rot_Z)
            w_roll = _dot(gyro_vec, self.rot_X)
            w_yaw = _dot(gyro_vec, self.rot_Z)

            ax_q.append(a_long)
            ay_q.append(a_lat)
            az_q.append(a_up)
            roll_rate_q.append(w_roll)

            a_long_sm = sum(ax_q) / len(ax_q)
            a_lat_sm = sum(ay_q) / len(ay_q)
            a_up_sm = sum(az_q) / len(az_q)
            roll_rate_sm = sum(roll_rate_q) / len(roll_rate_q)

            gps_lean = self._lean_from_gps(i, gps_features)
            gps_long = gps_features["gps_accel_g"][i]
            accel_lean = math.degrees(math.atan2(-a_lat_sm, max(0.35, a_up_sm)))
            if i == 0:
                gps_lean_lp = gps_lean
                gps_long_lp = gps_long
                imu_delta_lp = 0.0
                imu_long_delta_lp = 0.0
            else:
                gps_lean_lp = (0.04 * gps_lean) + (0.96 * gps_lean_lp)
                gps_long_lp = (0.08 * gps_long) + (0.92 * gps_long_lp)
            speed = speeds[i]
            baseline_lean = gps_lean_lp

            accel_low_dynamic = (
                speed >= 20.0
                and abs(a_long_sm) <= 0.10
                and abs(gps_features["yaw_rate_deg_s"][i]) <= 10.0
                and 0.80 <= a_up_sm <= 1.30
            )
            accel_correction = 0.0
            if accel_low_dynamic:
                accel_correction = 0.12 * (accel_lean - baseline_lean)

            roll_dynamic = _clamp(roll_rate_sm * 0.10, -4.0, 4.0)
            if speed < 20.0:
                roll_dynamic *= 0.4
            elif not gps_features["turn_mask"][i]:
                roll_dynamic *= 0.65

            imu_delta_target = (imu_trust * roll_dynamic) + accel_correction
            imu_delta_lp = (0.15 * imu_delta_target) + (0.85 * imu_delta_lp)

            if gps_features["straight_mask"][i] and abs(gps_features["yaw_rate_deg_s"][i]) < 1.5:
                imu_delta_lp *= 0.82

            raw_lean = baseline_lean + imu_delta_lp
            smoothed_lean = _clamp(raw_lean, -60.0, 60.0)
            imu_long_target = _clamp(a_long_sm - gps_long_lp, -0.30, 0.30)
            if speed < 20.0:
                imu_long_target *= 0.35
            elif abs(gps_features["yaw_rate_deg_s"][i]) > 10.0:
                imu_long_target *= 0.60

            if abs(imu_long_target) < 0.03:
                imu_long_target = 0.0

            imu_long_delta_lp = (0.12 * (imu_trust * imu_long_target)) + (0.88 * imu_long_delta_lp)
            if gps_features["straight_mask"][i] and abs(gps_long_lp) < 0.03:
                imu_long_delta_lp *= 0.80

            smoothed_longitudinal = gps_long_lp + imu_long_delta_lp
            smoothed_longitudinal = _clamp(smoothed_longitudinal, -1.5, 1.2)

            if abs(smoothed_longitudinal) < 0.02:
                smoothed_longitudinal = 0.0

            lat_g = math.tan(math.radians(_clamp(smoothed_lean, -60.0, 60.0)))

            lean_angle.append(round(smoothed_lean, 1))
            ax_cg.append(round(smoothed_longitudinal, 3))
            ay_cg.append(round(a_lat_sm, 3))
            az_cg.append(round(a_up_sm, 3))
            acceleration_g.append(round(max(smoothed_longitudinal, 0.0), 3))
            braking_g.append(round(abs(min(smoothed_longitudinal, 0.0)), 3))
            pitch_angle.append(round(math.degrees(math.atan2(smoothed_longitudinal, max(0.2, a_up_sm))), 2))
            yaw_angle.append(round(w_yaw, 2))

        return {
            "lean_angle": lean_angle,
            "pitch_angle": pitch_angle,
            "yaw_angle": yaw_angle,
            "ax_cg": ax_cg,
            "ay_cg": ay_cg,
            "az_cg": az_cg,
            "acceleration_g": acceleration_g,
            "braking_g": braking_g,
            "lateral_g": [round(math.tan(math.radians(_clamp(v, -60.0, 60.0))), 3) for v in lean_angle],
        }

    def _compute_calibrated_profile_outputs(
        self,
        timestamps: List[float],
        ax_raw: List[float],
        ay_raw: List[float],
        az_raw: List[float],
        gx_raw: List[float],
        gy_raw: List[float],
        gz_raw: List[float],
        gps_features: Dict[str, List[float]],
        calibration_profile: Dict[str, Any],
        runtime_validation: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        rotation = calibration_profile.get("rotation_matrix") or [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        gyro_bias = calibration_profile.get("gyro_bias") or [0.0, 0.0, 0.0]
        accel_bias = calibration_profile.get("accel_bias") or [0.0, 0.0, 0.0]
        self.rot_X = list(rotation[0])
        self.rot_Y = list(rotation[1])
        self.rot_Z = list(rotation[2])
        self.gx_bias = float(gyro_bias[0]) if len(gyro_bias) > 0 else 0.0
        self.gy_bias = float(gyro_bias[1]) if len(gyro_bias) > 1 else 0.0
        self.gz_bias = float(gyro_bias[2]) if len(gyro_bias) > 2 else 0.0

        ax_clean = _despike_series([a - float(accel_bias[0] if len(accel_bias) > 0 else 0.0) for a in ax_raw], self.config.imu_despike_window, self.config.imu_accel_despike_threshold)
        ay_clean = _despike_series([a - float(accel_bias[1] if len(accel_bias) > 1 else 0.0) for a in ay_raw], self.config.imu_despike_window, self.config.imu_accel_despike_threshold)
        az_clean = _despike_series([a - float(accel_bias[2] if len(accel_bias) > 2 else 0.0) for a in az_raw], self.config.imu_despike_window, self.config.imu_accel_despike_threshold)
        gx_clean = _despike_series(gx_raw, self.config.imu_despike_window, self.config.imu_gyro_despike_threshold)
        gy_clean = _despike_series(gy_raw, self.config.imu_despike_window, self.config.imu_gyro_despike_threshold)
        gz_clean = _despike_series(gz_raw, self.config.imu_despike_window, self.config.imu_gyro_despike_threshold)

        dt = max(0.005, min(0.05, _median_dt_seconds(timestamps)))
        roll_est = 0.0
        pitch_est = 0.0
        validation_mode = (runtime_validation or {}).get("source_mode", "imu_trusted")
        trust_scale = 1.0 if validation_mode == "imu_trusted" else 0.7 if validation_mode == "imu_warn" else 0.45

        lean_angle: List[float] = []
        pitch_angle: List[float] = []
        yaw_angle: List[float] = []
        ax_cg: List[float] = []
        ay_cg: List[float] = []
        az_cg: List[float] = []
        acceleration_g: List[float] = []
        braking_g: List[float] = []

        for i in range(len(timestamps)):
            accel_vec = [ax_clean[i], ay_clean[i], az_clean[i]]
            gyro_vec = [
                gx_clean[i] - self.gx_bias,
                gy_clean[i] - self.gy_bias,
                gz_clean[i] - self.gz_bias,
            ]
            a_long = _dot(accel_vec, self.rot_X)
            a_lat = _dot(accel_vec, self.rot_Y)
            a_up = _dot(accel_vec, self.rot_Z)
            g_roll = _dot(gyro_vec, self.rot_X)
            g_pitch = _dot(gyro_vec, self.rot_Y)
            g_yaw = _dot(gyro_vec, self.rot_Z)

            accel_roll = math.degrees(math.atan2(-a_lat, max(0.15, a_up)))
            accel_pitch = math.degrees(math.atan2(a_long, max(0.15, a_up)))
            roll_est = (0.985 * (roll_est + (g_roll * dt))) + (0.015 * accel_roll)
            pitch_est = (0.985 * (pitch_est + (g_pitch * dt))) + (0.015 * accel_pitch)

            lean = _clamp(roll_est * trust_scale, -60.0, 60.0)
            longitudinal = _clamp(a_long * trust_scale, -1.5, 1.2)
            lean_angle.append(round(lean, 1))
            pitch_angle.append(round(pitch_est, 2))
            yaw_angle.append(round(g_yaw, 2))
            ax_cg.append(round(longitudinal, 3))
            ay_cg.append(round(a_lat, 3))
            az_cg.append(round(a_up, 3))
            acceleration_g.append(round(max(longitudinal, 0.0), 3))
            braking_g.append(round(abs(min(longitudinal, 0.0)), 3))

        mount_confidence = "HIGH" if validation_mode == "imu_trusted" else "MEDIUM" if validation_mode == "imu_warn" else "LOW"
        return {
            "lean_angle": lean_angle,
            "pitch_angle": pitch_angle,
            "yaw_angle": yaw_angle,
            "ax_cg": ax_cg,
            "ay_cg": ay_cg,
            "az_cg": az_cg,
            "acceleration_g": acceleration_g,
            "braking_g": braking_g,
            "lateral_g": [round(math.tan(math.radians(_clamp(v, -60.0, 60.0))), 3) for v in lean_angle],
            "mount_confidence": mount_confidence,
            "mount_method": "stored_profile",
            "rotation_matrix": rotation,
            "gyro_bias": [self.gx_bias, self.gy_bias, self.gz_bias],
            "gravity_vector": calibration_profile.get("gravity_vector", [0.0, 0.0, 1.0]),
            "evidence_summary": {
                "source": "stored_profile",
                "profile_id": calibration_profile.get("id"),
                "profile_label": calibration_profile.get("label"),
                "profile_quality": calibration_profile.get("quality_score"),
                "runtime_validation": runtime_validation or {},
                "gps_heading_quality": round(gps_features.get("heading_quality", 0.0), 3),
            },
            "confidence": 0.95 if validation_mode == "imu_trusted" else 0.7 if validation_mode == "imu_warn" else 0.4,
        }

    def _compute_gps_fallback(self, gps_features: Dict[str, List[float]]) -> Dict[str, Any]:
        lean_angle = [round(self._lean_from_gps(i, gps_features), 1) for i in range(len(gps_features["speeds"]))]
        acceleration_g = [round(max(value, 0.0), 3) for value in gps_features["gps_accel_g"]]
        braking_g = [round(abs(min(value, 0.0)), 3) for value in gps_features["gps_accel_g"]]
        lateral_g = [round(math.tan(math.radians(_clamp(v, -60.0, 60.0))), 3) for v in lean_angle]

        return {
            "lean_angle": lean_angle,
            "pitch_angle": [0.0] * len(lean_angle),
            "yaw_angle": [round(v, 2) for v in gps_features["yaw_rate_deg_s"]],
            "ax_cg": [round(v, 3) for v in gps_features["gps_accel_g"]],
            "ay_cg": lateral_g,
            "az_cg": [1.0] * len(lean_angle),
            "acceleration_g": acceleration_g,
            "braking_g": braking_g,
            "lateral_g": lateral_g,
        }

    def _compute_legacy_outputs(
        self,
        timestamps: List[float],
        ax_raw: List[float],
        ay_raw: List[float],
        az_raw: List[float],
        gx_raw: List[float],
        gy_raw: List[float],
        gz_raw: List[float],
        speeds: List[float],
        gps_features: Dict[str, List[float]],
    ) -> Dict[str, Any]:
        window_sz = min(100, len(timestamps))
        gx_bias = 0.0
        gy_bias = 0.0
        gz_bias = 0.0
        best_var = float("inf")

        for start in range(0, max(1, len(timestamps) - window_sz), max(1, window_sz)):
            gx_slice = gx_raw[start:start + window_sz]
            gy_slice = gy_raw[start:start + window_sz]
            gz_slice = gz_raw[start:start + window_sz]
            current_var = _variance(gx_slice) + _variance(gy_slice) + _variance(gz_slice)
            if current_var < best_var:
                best_var = current_var
                gx_bias = _mean(gx_slice)
                gy_bias = _mean(gy_slice)
                gz_bias = _mean(gz_slice)

        mid_start = len(ax_raw) // 4
        mid_end = max(mid_start + 1, (3 * len(ax_raw)) // 4)
        gravity = [
            _mean(ax_raw[mid_start:mid_end]),
            _mean(ay_raw[mid_start:mid_end]),
            _mean(az_raw[mid_start:mid_end]),
        ]
        up_vector = _normalize(gravity, [0.0, 0.0, 1.0])
        forward_candidates = self._project_forward_candidates(
            ax_raw=ax_raw,
            ay_raw=ay_raw,
            az_raw=az_raw,
            up_vector=up_vector,
            gps_accel_g=gps_features["gps_accel_g"],
            straight_mask=[True] * len(gps_features["straight_mask"]),
            speeds=speeds,
        )
        forward_vector, forward_score = self._select_forward_axis(forward_candidates)
        lateral_vector = _normalize(_cross(up_vector, forward_vector), [0.0, 1.0, 0.0])
        forward_vector = _normalize(_cross(lateral_vector, up_vector), [1.0, 0.0, 0.0])

        original_rot_x, original_rot_y, original_rot_z = self.rot_X, self.rot_Y, self.rot_Z
        original_bias = (self.gx_bias, self.gy_bias, self.gz_bias)
        self.rot_X = forward_vector
        self.rot_Y = lateral_vector
        self.rot_Z = up_vector
        self.gx_bias = gx_bias
        self.gy_bias = gy_bias
        self.gz_bias = gz_bias
        try:
            result = self._compute_orientation_outputs(
                timestamps=timestamps,
                ax_raw=ax_raw,
                ay_raw=ay_raw,
                az_raw=az_raw,
                gx_raw=gx_raw,
                gy_raw=gy_raw,
                gz_raw=gz_raw,
                speeds=speeds,
                gps_features=gps_features,
                imu_trust=0.3,
            )
        finally:
            self.rot_X, self.rot_Y, self.rot_Z = original_rot_x, original_rot_y, original_rot_z
            self.gx_bias, self.gy_bias, self.gz_bias = original_bias

        result["mount_confidence"] = "LOW"
        result["mount_method"] = "legacy_correlation"
        result["rotation_matrix"] = [forward_vector, lateral_vector, up_vector]
        result["gyro_bias"] = [gx_bias, gy_bias, gz_bias]
        result["gravity_vector"] = gravity
        result["evidence_summary"] = {
            "source": "legacy",
            "forward_fit_score": round(forward_score, 3),
        }
        result["confidence"] = 0.4
        return result

    def _select_best_candidate(self, candidates: List[Tuple[str, Dict[str, Any]]]) -> Tuple[str, Dict[str, Any]]:
        primary = next((candidate for candidate in candidates if candidate[0] == "orientation_solver"), None)
        if primary:
            _, primary_result = primary
            if primary_result["validation"]["passed"] and primary_result["validation"]["score"] >= 80.0:
                return primary

        passing = [(name, candidate) for name, candidate in candidates if candidate["validation"]["passed"]]
        pool = passing if passing else candidates
        return max(pool, key=lambda item: item[1]["validation"]["score"])

    def _lean_from_gps(self, index: int, gps_features: Dict[str, List[float]]) -> float:
        speed_ms = gps_features["speeds_ms"][index]
        yaw_rate_rad = math.radians(gps_features["yaw_rate_deg_s"][index])
        if speed_ms < 2.0:
            return 0.0
        tan_lean = (speed_ms * yaw_rate_rad) / G_FORCE
        return math.degrees(math.atan(_clamp(tan_lean, -3.0, 3.0)))

    def _mean_vector(
        self,
        xs: List[float],
        ys: List[float],
        zs: List[float],
        start: int,
        end: int,
    ) -> Tuple[float, float, float]:
        end = min(end, len(xs))
        if start >= end:
            return (0.0, 0.0, 1.0)
        return (
            _mean(xs[start:end]),
            _mean(ys[start:end]),
            _mean(zs[start:end]),
        )

    def _mask_duration(self, mask: List[bool]) -> float:
        return sum(1 for value in mask if value) / max(1.0, self.config.sample_rate_est)

    def _count_longitudinal_events(self, gps_accel_g: List[float]) -> int:
        count = 0
        in_event = False
        for value in gps_accel_g:
            if abs(value) >= 0.08:
                if not in_event:
                    count += 1
                    in_event = True
            else:
                in_event = False
        return count

    def _score_mount_confidence(
        self,
        static_seconds: float,
        straight_seconds: float,
        turn_seconds: float,
        forward_score: float,
        longitudinal_events: int,
        brake_seconds: float,
        brake_score: float,
        method: str,
    ) -> float:
        score = 0.0
        score += min(0.3, static_seconds / 10.0)
        score += min(0.2, straight_seconds / 12.0)
        score += min(0.15, turn_seconds / 10.0)
        score += min(0.25, forward_score)
        score += min(0.1, longitudinal_events / 8.0)
        score += min(0.08, brake_seconds / 3.0)
        score += min(0.12, brake_score * 0.5)
        if method == "gps_only_fallback":
            score = min(score, 0.45)
        return _clamp(score, 0.0, 1.0)

    def _imu_trust_from_confidence(self, confidence_score: float) -> float:
        return _clamp(0.25 + (0.65 * confidence_score), 0.25, 0.85)

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "lean_angle": [],
            "pitch_angle": [],
            "yaw_angle": [],
            "ax_cg": [],
            "ay_cg": [],
            "az_cg": [],
            "acceleration_g": [],
            "braking_g": [],
            "lateral_g": [],
            "validation": {"passed": False, "score": 0.0, "failures": ["no samples"], "warnings": []},
            "mount_confidence": "LOW",
            "mount_method": "failed",
            "rotation_matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            "gyro_bias": [0.0, 0.0, 0.0],
            "gravity_vector": [0.0, 0.0, 1.0],
            "evidence_summary": {},
            "confidence": 0.0,
            "diagnostics": {"selected_algorithm": "none", "primary_algorithm_failed": True},
        }
