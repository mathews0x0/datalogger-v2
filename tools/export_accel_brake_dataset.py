#!/usr/bin/env python3
import argparse
import csv
import json
import math
import os
import statistics
from typing import Dict, List, Optional, Tuple


G_FORCE = 9.80665


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def norm(v: List[float]) -> float:
    return math.sqrt(sum(value * value for value in v))


def normalize(v: List[float]) -> List[float]:
    mag = norm(v)
    if mag <= 1e-9:
        return [1.0, 0.0, 0.0]
    return [value / mag for value in v]


def median(values: List[float]) -> float:
    if not values:
        return 0.0
    return statistics.median(values)


def centered_smooth(values: List[float], window: int) -> List[float]:
    if window <= 1 or not values:
        return list(values)
    radius = window // 2
    out: List[float] = []
    for idx in range(len(values)):
        start = max(0, idx - radius)
        end = min(len(values), idx + radius + 1)
        out.append(sum(values[start:end]) / (end - start))
    return out


def robust_mean(values: List[float]) -> float:
    if not values:
        return 0.0
    if len(values) < 4:
        return sum(values) / len(values)
    center = statistics.median(values)
    deviations = [abs(value - center) for value in values]
    mad = statistics.median(deviations)
    threshold = max(0.08, 2.5 * 1.4826 * mad)
    kept = [value for value in values if abs(value - center) <= threshold]
    return sum(kept or [center]) / len(kept or [center])


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


def load_rows(input_path: str) -> Dict[str, object]:
    profile: Optional[Dict[str, object]] = None
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
                        "acc": [
                            float(row["acc_x"] or 0.0),
                            float(row["acc_y"] or 0.0),
                            float(row["acc_z"] or 0.0),
                        ],
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


def compute_gps_accel_g(gps_rows: List[Dict[str, object]]) -> List[float]:
    if not gps_rows:
        return []

    times = [float(row["tick_ms"]) / 1000.0 for row in gps_rows]
    speed_ms_raw = [max(0.0, float(row["speed"] or 0.0)) / 3.6 for row in gps_rows]
    speed_ms = centered_smooth(speed_ms_raw, 5)
    accel_g = [0.0] * len(gps_rows)

    for idx in range(len(gps_rows)):
        left = idx
        while left > 0 and times[idx] - times[left] < 0.55:
            left -= 1
        right = idx
        while right < len(gps_rows) - 1 and times[right] - times[idx] < 0.55:
            right += 1
        if left == right:
            continue
        dt = times[right] - times[left]
        if dt < 0.20:
            continue
        accel_g[idx] = clamp(((speed_ms[right] - speed_ms[left]) / dt) / G_FORCE, -1.5, 1.2)

    return centered_smooth(accel_g, 5)


def local_window(data_rows: List[Dict[str, object]], center_idx: int, radius: int = 2) -> List[Dict[str, object]]:
    start = max(0, center_idx - radius)
    end = min(len(data_rows), center_idx + radius + 1)
    return data_rows[start:end]


def sample_axis_at_gps(
    data_rows: List[Dict[str, object]],
    gps_indices: List[int],
    axis: List[float],
) -> List[float]:
    sampled: List[float] = []
    for idx in gps_indices:
        values = [dot(row["acc"], axis) for row in local_window(data_rows, idx)]
        sampled.append(robust_mean(values))
    return sampled


def candidate_axes(profile: Dict[str, object]) -> List[Tuple[str, List[float]]]:
    rotation = profile.get("rotation_matrix") or [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    axes = [
        ("calibrated_forward", rotation[0]),
        ("negative_calibrated_forward", [-value for value in rotation[0]]),
        ("calibrated_lateral", rotation[1]),
        ("negative_calibrated_lateral", [-value for value in rotation[1]]),
        ("raw_x", [1.0, 0.0, 0.0]),
        ("negative_raw_x", [-1.0, 0.0, 0.0]),
        ("raw_y", [0.0, 1.0, 0.0]),
        ("negative_raw_y", [0.0, -1.0, 0.0]),
        ("raw_z", [0.0, 0.0, 1.0]),
        ("negative_raw_z", [0.0, 0.0, -1.0]),
    ]
    return [(name, normalize(list(axis))) for name, axis in axes]


def centered_imu_series(samples: List[float], gps_accel_g: List[float], speeds: List[float]) -> Tuple[List[float], float]:
    quiet = [
        value
        for value, gps_g, speed in zip(samples, gps_accel_g, speeds)
        if abs(gps_g) < 0.04 and speed > 15.0
    ]
    baseline = median(quiet if len(quiet) >= 20 else samples)
    centered = [value - baseline for value in samples]
    return centered_smooth(centered, 5), baseline


def select_forward_axis(
    data_rows: List[Dict[str, object]],
    gps_indices: List[int],
    gps_accel_g: List[float],
    profile: Dict[str, object],
) -> Dict[str, object]:
    speeds = [float(data_rows[idx]["speed"] or 0.0) for idx in gps_indices]
    best: Dict[str, object] = {
        "name": "calibrated_forward",
        "axis": normalize(list((profile.get("rotation_matrix") or [[1.0, 0.0, 0.0]])[0])),
        "samples": [],
        "baseline": 0.0,
        "correlation": -1.0,
    }

    mask = [idx for idx, value in enumerate(gps_accel_g) if abs(value) >= 0.035 and speeds[idx] >= 15.0]
    for name, axis in candidate_axes(profile):
        samples = sample_axis_at_gps(data_rows, gps_indices, axis)
        centered, baseline = centered_imu_series(samples, gps_accel_g, speeds)
        if len(mask) >= 10:
            score = correlation([centered[idx] for idx in mask], [gps_accel_g[idx] for idx in mask])
        else:
            score = correlation(centered, gps_accel_g)
        if score > float(best["correlation"]):
            best = {
                "name": name,
                "axis": axis,
                "samples": centered,
                "baseline": baseline,
                "correlation": score,
            }
    return best


def export_file(input_path: str, output_path: str) -> Dict[str, object]:
    payload = load_rows(input_path)
    profile = payload["profile"]
    data_rows = payload["data_rows"]
    gps_indices = [idx for idx, row in enumerate(data_rows) if row["row_type"] == "G"]
    gps_rows = [data_rows[idx] for idx in gps_indices]
    if not gps_rows:
        raise ValueError("No GPS rows found in input file")

    gps_accel_g = compute_gps_accel_g(gps_rows)
    axis_result = select_forward_axis(data_rows, gps_indices, gps_accel_g, profile)
    imu_forward_g = list(axis_result["samples"])

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "lat",
                "long",
                "speed",
                "imu_brake",
                "gps_brake",
                "brake_delta",
                "imu_accel",
                "gps_accel",
                "accel_delta",
            ]
        )
        for idx, row in enumerate(gps_rows):
            imu_signed_g = imu_forward_g[idx]
            gps_signed_g = gps_accel_g[idx]
            imu_brake = abs(min(imu_signed_g, 0.0))
            gps_brake = abs(min(gps_signed_g, 0.0))
            imu_accel = max(imu_signed_g, 0.0)
            gps_accel = max(gps_signed_g, 0.0)
            writer.writerow(
                [
                    f"{float(row['lat']):.7f}",
                    f"{float(row['lon']):.7f}",
                    f"{float(row['speed']):.2f}",
                    f"{imu_brake:.3f}",
                    f"{gps_brake:.3f}",
                    f"{imu_brake - gps_brake:.3f}",
                    f"{imu_accel:.3f}",
                    f"{gps_accel:.3f}",
                    f"{imu_accel - gps_accel:.3f}",
                ]
            )

    return {
        "output_path": output_path,
        "rows": len(gps_rows),
        "axis": axis_result["name"],
        "axis_correlation": round(float(axis_result["correlation"]), 3),
        "axis_baseline_g": round(float(axis_result["baseline"]), 4),
        "max_imu_accel_g": round(max(max(value, 0.0) for value in imu_forward_g), 3),
        "max_gps_accel_g": round(max(max(value, 0.0) for value in gps_accel_g), 3),
        "max_imu_brake_g": round(max(abs(min(value, 0.0)) for value in imu_forward_g), 3),
        "max_gps_brake_g": round(max(abs(min(value, 0.0)) for value in gps_accel_g), 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export GPS-cadence acceleration/braking values from a telemetry CSV.")
    parser.add_argument("input_csv", help="Telemetry CSV with IMU_PROFILE marker and I/G rows")
    parser.add_argument(
        "-o",
        "--output",
        help="Output CSV path. Defaults to <input>_accel_brake.csv",
    )
    args = parser.parse_args()

    output_path = args.output
    if not output_path:
        stem, ext = os.path.splitext(args.input_csv)
        output_path = f"{stem}_accel_brake{ext or '.csv'}"

    stats = export_file(args.input_csv, output_path)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
