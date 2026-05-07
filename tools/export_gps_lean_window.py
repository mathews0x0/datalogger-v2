#!/usr/bin/env python3
import argparse
import csv
import json
import math
import os
import statistics
from typing import Dict, List, Optional


G_FORCE = 9.81


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def smooth_series(values: List[float], window: int) -> List[float]:
    if window <= 1 or not values:
        return list(values)
    smoothed: List[float] = []
    running: List[float] = []
    for value in values:
        running.append(value)
        if len(running) > window:
            running.pop(0)
        smoothed.append(sum(running) / len(running))
    return smoothed


def median_absolute_deviation(values: List[float], center: Optional[float] = None) -> float:
    if not values:
        return 0.0
    if center is None:
        center = statistics.median(values)
    deviations = [abs(value - center) for value in values]
    return statistics.median(deviations)


def robust_mean(values: List[float]) -> float:
    if not values:
        return 0.0
    if len(values) <= 2:
        return sum(values) / len(values)

    center = statistics.median(values)
    mad = median_absolute_deviation(values, center=center)
    threshold = max(2.0, 2.5 * (1.4826 * mad))
    kept = [value for value in values if abs(value - center) <= threshold]
    if not kept:
        kept = [center]
    return sum(kept) / len(kept)


def lean_from_sample(sample: Dict[str, float], rotation: List[List[float]], accel_bias: List[float]) -> Dict[str, float]:
    accel_vec = [
        sample["acc_x"] - accel_bias[0],
        sample["acc_y"] - accel_bias[1],
        sample["acc_z"] - accel_bias[2],
    ]
    a_long = dot(accel_vec, rotation[0])
    a_lat = dot(accel_vec, rotation[1])
    a_up = dot(accel_vec, rotation[2])
    lean_deg = math.degrees(math.atan2(-a_lat, max(0.15, a_up)))
    return {
        "lean_deg": lean_deg,
        "a_long": a_long,
        "a_lat": a_lat,
        "a_up": a_up,
    }


def accel_lean_from_sample(sample: Dict[str, float], rotation: List[List[float]], accel_bias: List[float]) -> float:
    return lean_from_sample(sample, rotation, accel_bias)["lean_deg"]


def angle_delta_deg(target: float, current: float) -> float:
    delta = target - current
    while delta > 180.0:
        delta -= 360.0
    while delta < -180.0:
        delta += 360.0
    return delta


def correlation(xs: List[float], ys: List[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 3:
        return 0.0
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denom_x = sum((x - mean_x) ** 2 for x in xs)
    denom_y = sum((y - mean_y) ** 2 for y in ys)
    if denom_x <= 1e-9 or denom_y <= 1e-9:
        return 0.0
    return numerator / math.sqrt(denom_x * denom_y)


def estimate_attitude_leans(
    data_rows: List[Dict[str, float]],
    profile: Dict[str, object],
    gps_indices: Optional[List[int]] = None,
    gps_leans: Optional[List[float]] = None,
) -> List[float]:
    rotation = profile.get("rotation_matrix") or [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    accel_bias = list(profile.get("accel_bias") or [0.0, 0.0, 0.0])
    gyro_bias = list(profile.get("gyro_bias") or [0.0, 0.0, 0.0])
    while len(accel_bias) < 3:
        accel_bias.append(0.0)
    while len(gyro_bias) < 3:
        gyro_bias.append(0.0)

    if not data_rows:
        return []

    tick_dts = [
        (data_rows[idx]["tick_ms"] - data_rows[idx - 1]["tick_ms"]) / 1000.0
        for idx in range(1, len(data_rows))
        if data_rows[idx]["tick_ms"] > data_rows[idx - 1]["tick_ms"]
    ]
    sample_rate_hz = 1.0 / statistics.median(tick_dts) if tick_dts else 0.0
    gyro_abs = sorted(
        abs(row[key])
        for row in data_rows
        for key in ("gyro_x", "gyro_y", "gyro_z")
    )
    gyro_p99 = gyro_abs[min(len(gyro_abs) - 1, int(len(gyro_abs) * 0.99))] if gyro_abs else 0.0
    gyro_scale = 1.0 / 16.0 if 45.0 <= sample_rate_hz <= 60.0 and gyro_p99 > 250.0 else 1.0
    gyro_bias = [value * gyro_scale for value in gyro_bias]

    def run_filter(roll_axis: List[float]) -> List[float]:
        first_lean = accel_lean_from_sample(data_rows[0], rotation, accel_bias)
        roll_est = clamp(first_lean, -45.0, 45.0)
        leans: List[float] = []

        for idx, row in enumerate(data_rows):
            if idx == 0:
                dt = 0.02
            else:
                dt = (row["tick_ms"] - data_rows[idx - 1]["tick_ms"]) / 1000.0
                dt = clamp(dt, 0.005, 0.08)

            gyro_vec = [
                (row["gyro_x"] * gyro_scale) - gyro_bias[0],
                (row["gyro_y"] * gyro_scale) - gyro_bias[1],
                (row["gyro_z"] * gyro_scale) - gyro_bias[2],
            ]
            roll_rate = dot(gyro_vec, roll_axis)
            roll_est += roll_rate * dt

            accel_vec = [
                row["acc_x"] - accel_bias[0],
                row["acc_y"] - accel_bias[1],
                row["acc_z"] - accel_bias[2],
            ]
            acc_mag = math.sqrt(sum(value * value for value in accel_vec))
            a_long = dot(accel_vec, rotation[0])
            a_lat = dot(accel_vec, rotation[1])
            a_up = dot(accel_vec, rotation[2])
            accel_lean = math.degrees(math.atan2(-a_lat, max(0.15, a_up)))

            # Accelerometer correction is only trusted when the force vector looks gravity-like.
            # In corners/braking/bump events it measures dynamics, so it should not dominate roll.
            gyro_activity = math.sqrt(sum(value * value for value in gyro_vec))
            force_error = abs(acc_mag - 1.0)
            stable_force = force_error < 0.16 and a_up > 0.65 and abs(a_long) < 0.35
            stable_rotation = abs(roll_rate) < 90.0 and gyro_activity < 450.0
            if stable_force and stable_rotation:
                correction_gain = 0.045
            elif force_error < 0.24 and a_up > 0.45 and abs(roll_rate) < 140.0:
                correction_gain = 0.010
            else:
                correction_gain = 0.0

            if correction_gain:
                roll_est += correction_gain * angle_delta_deg(accel_lean, roll_est)

            roll_est = clamp(roll_est, -60.0, 60.0)
            leans.append(roll_est)

        return smooth_series(leans, 5)

    if not gps_indices or not gps_leans:
        return run_filter(rotation[0])

    candidates = [
        rotation[0],
        [-value for value in rotation[0]],
        rotation[1],
        [-value for value in rotation[1]],
        rotation[2],
        [-value for value in rotation[2]],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]
    best_leans = run_filter(rotation[0])
    best_score = -1.0
    for axis in candidates:
        candidate_leans = run_filter(axis)
        sampled = [candidate_leans[idx] for idx in gps_indices if idx < len(candidate_leans)]
        compare = gps_leans[:len(sampled)]
        score = correlation(sampled, compare)
        if len(sampled) >= 10 and score > best_score:
            best_score = score
            best_leans = candidate_leans
    return best_leans


def variation_factor(window_metrics: List[Dict[str, float]]) -> int:
    if len(window_metrics) < 2:
        return 1

    lean_values = [item["lean_deg"] for item in window_metrics]
    lat_values = [item["a_lat"] for item in window_metrics]
    up_values = [item["a_up"] for item in window_metrics]
    long_values = [item["a_long"] for item in window_metrics]

    lean_std = statistics.pstdev(lean_values)
    lat_std = statistics.pstdev(lat_values)
    up_std = statistics.pstdev(up_values)
    long_std = statistics.pstdev(long_values)

    # Heuristic: combine angular variation with transformed accelerometer spread.
    score = (
        0.55 * clamp(lean_std / 6.0, 0.0, 1.0)
        + 0.20 * clamp(lat_std / 0.12, 0.0, 1.0)
        + 0.15 * clamp(up_std / 0.10, 0.0, 1.0)
        + 0.10 * clamp(long_std / 0.08, 0.0, 1.0)
    )
    return int(clamp(round(1 + (score * 9)), 1, 10))


def load_rows(input_path: str) -> Dict[str, object]:
    profile = None
    data_rows: List[Dict[str, object]] = []

    with open(input_path, "r", newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            row_type = (row.get("row_type") or "").strip()
            if row_type == "M" and (row.get("lon") or "").strip() == "IMU_PROFILE":
                raw_profile = row.get("speed") or ""
                if raw_profile and raw_profile != "none":
                    profile = json.loads(raw_profile)
                continue

            if row_type not in {"I", "G"}:
                continue

            try:
                data_rows.append(
                    {
                        "row_type": row_type,
                        "tick_ms": int(row["tick_ms"]),
                        "acc_x": float(row["acc_x"] or 0.0),
                        "acc_y": float(row["acc_y"] or 0.0),
                        "acc_z": float(row["acc_z"] or 0.0),
                        "gyro_x": float(row["gyro_x"] or 0.0),
                        "gyro_y": float(row["gyro_y"] or 0.0),
                        "gyro_z": float(row["gyro_z"] or 0.0),
                        "lat": float(row["lat"]) if row.get("lat") else None,
                        "lon": float(row["lon"]) if row.get("lon") else None,
                        "speed": float(row["speed"]) if row.get("speed") else None,
                    }
                )
            except (TypeError, ValueError):
                continue

    if profile is None:
        raise ValueError("No IMU_PROFILE marker found in input file")

    return {"profile": profile, "data_rows": data_rows}


def compute_gps_leans(input_path: str, gps_rows: List[Dict[str, object]]) -> List[float]:
    if not gps_rows:
        return []
    timestamps = [row["tick_ms"] / 1000.0 for row in gps_rows]
    speeds_ms = [max(0.0, float(row["speed"])) / 3.6 for row in gps_rows]
    ref_lat = gps_rows[0]["lat"]
    ref_lon = gps_rows[0]["lon"]

    meters_per_deg_lat = 111320.0
    meters_per_deg_lon = 111320.0 * math.cos(math.radians(ref_lat))
    xs_raw = [(row["lon"] - ref_lon) * meters_per_deg_lon for row in gps_rows]
    ys_raw = [(row["lat"] - ref_lat) * meters_per_deg_lat for row in gps_rows]
    xs = smooth_series(xs_raw, 9)
    ys = smooth_series(ys_raw, 9)

    gps_lean = [0.0] * len(gps_rows)
    for idx in range(len(gps_rows)):
        left = idx
        while left > 0 and (timestamps[idx] - timestamps[left] < 0.9):
            left -= 1
        right = idx
        while right < len(gps_rows) - 1 and (timestamps[right] - timestamps[idx] < 0.9):
            right += 1
        if left == idx or right == idx or left == right:
            continue

        ax = xs[left]
        ay = ys[left]
        bx = xs[idx]
        by = ys[idx]
        cx = xs[right]
        cy = ys[right]

        ab = math.hypot(bx - ax, by - ay)
        bc = math.hypot(cx - bx, cy - by)
        ac = math.hypot(cx - ax, cy - ay)
        if min(ab, bc, ac) < 3.0 or speeds_ms[idx] < 5.0:
            continue

        cross = ((bx - ax) * (cy - ay)) - ((by - ay) * (cx - ax))
        area2 = abs(cross)
        denom = ab * bc * ac
        if denom <= 1e-6:
            continue

        signed_curvature = (2.0 * cross) / denom
        midpoint_deviation_m = area2 / max(ac, 1e-6)
        if midpoint_deviation_m < 1.25 or abs(signed_curvature) < 0.0035:
            gps_lean[idx] = 0.0
            continue

        lateral_accel = speeds_ms[idx] * speeds_ms[idx] * signed_curvature
        gps_lean[idx] = clamp(math.degrees(math.atan(lateral_accel / G_FORCE)), -60.0, 60.0)

    return smooth_series(gps_lean, 7)


def export_file(input_path: str, output_path: str) -> None:
    payload = load_rows(input_path)
    profile = payload["profile"]
    data_rows = payload["data_rows"]

    rotation = profile.get("rotation_matrix") or [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    accel_bias = list(profile.get("accel_bias") or [0.0, 0.0, 0.0])
    while len(accel_bias) < 3:
        accel_bias.append(0.0)
    gps_indices = [idx for idx, row in enumerate(data_rows) if row["row_type"] == "G"]
    gps_rows = [data_rows[idx] for idx in gps_indices]
    gps_leans = compute_gps_leans(input_path, gps_rows)
    attitude_leans = estimate_attitude_leans(data_rows, profile, gps_indices, gps_leans)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["lat", "lon", "speed", "lean", "gps_lean", "variation_factor"])

        gps_idx = 0
        for idx, row in enumerate(data_rows):
            if row["row_type"] != "G":
                continue

            start = max(0, idx - 2)
            end = min(len(data_rows), idx + 3)
            window = data_rows[start:end]
            metrics = [lean_from_sample(sample, rotation, accel_bias) for sample in window]
            variation = variation_factor(metrics)
            writer.writerow(
                [
                    f"{row['lat']:.7f}",
                    f"{row['lon']:.7f}",
                    f"{row['speed']:.2f}",
                    f"{attitude_leans[idx]:.2f}",
                    f"{gps_leans[gps_idx]:.2f}",
                    variation,
                ]
            )
            gps_idx += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Export one lean-angle sample per GPS fix using a 5-IMU-point window.")
    parser.add_argument("input_csv", help="Telemetry CSV with IMU_PROFILE marker and I/G rows")
    parser.add_argument(
        "-o",
        "--output",
        help="Output CSV path. Defaults to <input>_gps_lean.csv",
    )
    args = parser.parse_args()

    output_path = args.output
    if not output_path:
        stem, ext = os.path.splitext(args.input_csv)
        output_path = f"{stem}_gps_lean{ext or '.csv'}"

    export_file(args.input_csv, output_path)
    print(output_path)


if __name__ == "__main__":
    main()
