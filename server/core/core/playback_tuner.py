import copy
import math
from typing import Any, Dict, List, Optional


DEFAULT_PLAYBACK_TUNE = {
    "gyroScale": 0.04,
    "leanGaussianSigma": 0.0,
    "longGaussianSigma": 0.0,
    "flipLean": False,
    "flipForce": False,
    "autoAlignEnabled": True,
    "gpsLagMs": 0,
    "pathTrimMs": 0,
    "gpsLagAutoEnabled": True,
    "gpsLagMinMs": 1200,
    "gpsLagMaxMs": 2200,
    "gpsLagStepMs": 50,
    "gpsLagMinImprovement": 0.2,
    "gpsLeanRefSign": 1,
    "gpsLongRefSign": -1,
    "graphLeanDisplaySign": -1,
}


_TUNE_RULES = {
    "gyroScale": {"type": "float", "min": 0.0, "max": 0.2},
    "leanGaussianSigma": {"type": "float", "min": 0.0, "max": 20.0},
    "longGaussianSigma": {"type": "float", "min": 0.0, "max": 20.0},
    "flipLean": {"type": "bool"},
    "flipForce": {"type": "bool"},
    "autoAlignEnabled": {"type": "bool"},
    "gpsLagMs": {"type": "int", "min": 0, "max": 5000},
    "pathTrimMs": {"type": "int", "min": -7000, "max": 7000},
}

_LEGACY_COMPAT_KEYS = {
    "smoothingSamples",
    "gaussianSigma",
    "forceSmoothingSamples",
    "forceGaussianSigma",
    "accelBlendMode",
    "accelCorrectionStrong",
    "accelCorrectionWeak",
    "leanOffsetDeg",
    "leanSign",
    "calibratedLeanGain",
    "longitudinalGain",
    "alignmentMode",
    "gpsLeanLagMs",
    "gpsLongLagMs",
    "graphLeanDisplaySign",
    "gpsLeanRefSign",
    "gpsLongRefSign",
}


def get_default_playback_tune() -> Dict[str, Any]:
    return dict(DEFAULT_PLAYBACK_TUNE)


def normalize_playback_tune(raw_tune: Optional[Dict[str, Any]], base_tune: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    tune = dict(get_default_playback_tune())
    if base_tune:
        tune.update(_coerce_legacy_tune(base_tune))
    if raw_tune is None:
        tune = _apply_tune_aliases(tune)
        return tune
    normalized_raw = _coerce_legacy_tune(raw_tune)
    unknown = [key for key in normalized_raw.keys() if key not in tune and key not in _LEGACY_COMPAT_KEYS]
    if unknown:
        raise ValueError(f"Unknown playback tune keys: {', '.join(sorted(unknown))}")
    for key, value in normalized_raw.items():
        if key in _TUNE_RULES:
            tune[key] = _normalize_tune_value(key, value)
        else:
            tune[key] = value
    tune = _apply_tune_aliases(tune)
    return tune


def _coerce_legacy_tune(raw_tune: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(raw_tune, dict):
        return {}
    coerced = dict(raw_tune)
    if "gaussianSigma" in coerced and "leanGaussianSigma" not in coerced:
        coerced["leanGaussianSigma"] = coerced.get("gaussianSigma")
    if "forceGaussianSigma" in coerced and "longGaussianSigma" not in coerced:
        coerced["longGaussianSigma"] = coerced.get("forceGaussianSigma")
    if "gpsLagAutoEnabled" in coerced and "autoAlignEnabled" not in coerced:
        coerced["autoAlignEnabled"] = coerced.get("gpsLagAutoEnabled")
    if "leanSign" in coerced and "flipLean" not in coerced:
        coerced["flipLean"] = int(float(coerced.get("leanSign") or 1)) < 0
    if "graphLeanDisplaySign" in coerced and "flipLean" not in coerced:
        coerced["flipLean"] = int(float(coerced.get("graphLeanDisplaySign") or 1)) < 0
    if "gpsLongRefSign" in coerced and "flipForce" not in coerced:
        coerced["flipForce"] = int(float(coerced.get("gpsLongRefSign") or 1)) < 0
    if "gpsLeanLagMs" in coerced and "gpsLagMs" not in coerced and coerced.get("gpsLeanLagMs") is not None:
        coerced["gpsLagMs"] = coerced.get("gpsLeanLagMs")
    return coerced


def _apply_tune_aliases(tune: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(DEFAULT_PLAYBACK_TUNE)
    out.update(tune)
    out["gpsLagMs"] = int(out.get("gpsLagMs", DEFAULT_PLAYBACK_TUNE["gpsLagMs"]) or 0)
    out["gpsLagAutoEnabled"] = bool(out.get("autoAlignEnabled", out.get("gpsLagAutoEnabled", True)))
    out["gpsLeanLagMs"] = out["gpsLagMs"]
    out["gpsLongLagMs"] = out["gpsLagMs"]
    out["alignmentMode"] = "legacy_split"
    out["smoothingSamples"] = 1
    out["forceSmoothingSamples"] = 1
    out["gaussianSigma"] = float(out.get("leanGaussianSigma", 0.0) or 0.0)
    out["forceGaussianSigma"] = float(out.get("longGaussianSigma", 0.0) or 0.0)
    out["leanSign"] = -1 if bool(out.get("flipLean")) else 1
    out["graphLeanDisplaySign"] = out["leanSign"]
    out["gpsLeanRefSign"] = int(out.get("gpsLeanRefSign", 1) or 1)
    out["gpsLongRefSign"] = int(out.get("gpsLongRefSign", 1) or 1)
    out["calibratedLeanGain"] = 1.0
    out["longitudinalGain"] = 1.0
    out["leanOffsetDeg"] = 0.0
    out["accelBlendMode"] = "soft"
    out["accelCorrectionStrong"] = 0.0
    out["accelCorrectionWeak"] = 0.0
    return out


def resolve_alignment_offsets(tune: Dict[str, Any], gps_lag_ms: int) -> Dict[str, int]:
    lag = int(gps_lag_ms or 0)
    path_trim_ms = int(tune.get("pathTrimMs", 0) or 0)
    path_offset_ms = lag + path_trim_ms
    return {"path_offset_ms": path_offset_ms, "aligned_path_offset_ms": path_offset_ms, "lean_ref_offset_ms": -lag, "long_ref_offset_ms": -lag}


def build_playback_dataset_from_imu(playback_signals: Dict[str, List[float]], gps_references: Optional[Dict[str, List[float]]] = None, tune: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    effective_tune = normalize_playback_tune(tune)
    base_signals = {
        "lean_deg": [float(value or 0.0) for value in list(playback_signals.get("lean_deg", []))],
        "long_g": [float(value or 0.0) for value in list(playback_signals.get("long_g", []))],
        "lat_g": [float(value or 0.0) for value in list(playback_signals.get("lat_g", []))],
    }
    tuned = tune_base_signals(base_signals, effective_tune)
    return {
        "config": effective_tune,
        "base_signals": {
            "lean_deg": list(base_signals["lean_deg"]),
            "long_g": list(base_signals["long_g"]),
            "lat_g": list(base_signals["lat_g"]),
        },
        "signals": {
            "lean_deg": list(tuned["lean_deg"]),
            "long_g": list(tuned["long_g"]),
            "lat_g": list(tuned["lat_g"]),
            "accel_g": list(tuned["accel_g"]),
            "brake_g": list(tuned["brake_g"]),
        },
        "display_signals": {
            "display_lean_deg": list(tuned["display_lean_deg"]),
            "display_long_g": list(tuned["display_long_g"]),
            "display_lat_g": list(tuned["display_lat_g"]),
        },
        "gps_references": {
            "gps_lean_deg": list((gps_references or {}).get("gps_lean_deg", [])),
            "gps_long_g": list((gps_references or {}).get("gps_long_g", [])),
        },
    }


def tune_base_signals(base_signals: Dict[str, List[float]], tune: Dict[str, Any]) -> Dict[str, List[float]]:
    gaussian_sigma = float(tune.get("leanGaussianSigma", tune.get("gaussianSigma", 0.0)) or 0.0)
    force_gaussian_sigma = float(tune.get("longGaussianSigma", tune.get("forceGaussianSigma", 0.0)) or 0.0)
    lean_sign = -1.0 if bool(tune.get("flipLean", False)) else 1.0
    force_sign = -1.0 if bool(tune.get("flipForce", False)) else 1.0
    default_gyro_scale = float(DEFAULT_PLAYBACK_TUNE.get("gyroScale") or 0.04)
    gyro_scale = float(tune.get("gyroScale", default_gyro_scale) or default_gyro_scale)
    gyro_ratio = gyro_scale / default_gyro_scale if default_gyro_scale > 0 else 1.0
    raw_base_lean = [float(value or 0.0) * gyro_ratio for value in base_signals.get("lean_deg", [])]
    raw_lean = [
        float(value or 0.0) * lean_sign
        for value in raw_base_lean
    ]
    lean = _gaussian_smooth(raw_lean, gaussian_sigma)
    long_g = [float(value or 0.0) * force_sign for value in base_signals.get("long_g", [])]
    lat_g = [float(value or 0.0) for value in base_signals.get("lat_g", [])]
    long_g = _gaussian_smooth(long_g, force_gaussian_sigma)
    lat_g = [round(value, 3) for value in lat_g]
    accel_g = [round(max(value, 0.0), 3) for value in long_g]
    brake_g = [round(abs(min(value, 0.0)), 3) for value in long_g]
    lean = [round(value, 1) for value in lean]
    long_g = [round(value, 3) for value in long_g]
    return {
        "lean_deg": lean,
        "long_g": long_g,
        "lat_g": lat_g,
        "accel_g": accel_g,
        "brake_g": brake_g,
        "display_lean_deg": list(lean),
        "display_long_g": list(long_g),
        "display_lat_g": list(lat_g),
    }


def apply_tune_to_playback_payload(payload: Dict[str, Any], tune: Optional[Dict[str, Any]] = None, tune_source: str = "default", feature_enabled: bool = False) -> Dict[str, Any]:
    if not payload:
        return payload
    rows = list(payload.get("rows") or [])
    if not rows:
        return payload
    effective_tune = normalize_playback_tune(tune, payload.get("config") or {})
    retuned_rows = retune_playback_rows(rows, effective_tune)
    output = copy.deepcopy(payload)
    output["rows"] = retuned_rows["rows"]
    output["config"] = dict(effective_tune)
    output.setdefault("meta", {})
    output["meta"]["tune_source"] = tune_source
    output["meta"]["tuner_feature_enabled"] = bool(feature_enabled)
    output["meta"]["active_tune"] = dict(effective_tune)
    output["meta"]["gps_lag_ms_applied"] = retuned_rows["meta"]["gps_lag_ms_applied"]
    output["meta"]["gps_lean_lag_ms_applied"] = retuned_rows["meta"].get("gps_lean_lag_ms_applied", retuned_rows["meta"]["gps_lag_ms_applied"])
    output["meta"]["gps_long_lag_ms_applied"] = retuned_rows["meta"].get("gps_long_lag_ms_applied", retuned_rows["meta"]["gps_lag_ms_applied"])
    output["meta"]["gps_lag_source"] = retuned_rows["meta"]["gps_lag_source"]
    output["meta"]["gps_lean_ref_sign"] = retuned_rows["meta"]["gps_lean_ref_sign"]
    output["meta"]["gps_long_ref_sign"] = retuned_rows["meta"]["gps_long_ref_sign"]
    output["meta"]["gps_lag_score"] = retuned_rows["meta"]["gps_lag_score"]
    output["meta"]["gps_lag_configured_ms"] = effective_tune.get("gpsLagMs", 0)
    output["meta"]["alignment_mode"] = "single_lag"
    output["meta"]["path_trim_ms"] = effective_tune.get("pathTrimMs", 0)
    output["meta"]["graph_lean_display_sign"] = -1 if bool(effective_tune.get("flipLean")) else 1
    return output


def build_tune_preview_patch(
    payload: Dict[str, Any],
    tune: Optional[Dict[str, Any]] = None,
    tune_source: str = "preview",
    feature_enabled: bool = False,
    start_index: Optional[int] = None,
    end_index: Optional[int] = None,
) -> Dict[str, Any]:
    rows = list((payload or {}).get("rows") or [])
    effective_tune = normalize_playback_tune(tune, (payload or {}).get("config") or {})
    row_count = len(rows)
    start = max(0, int(start_index or 0))
    end = min(row_count, int(end_index if end_index is not None else row_count))
    if end <= start:
        start, end = 0, row_count
    if not rows:
        return {
            "kind": "playback_tune_patch",
            "start_index": 0,
            "end_index": 0,
            "meta": {
                "tune_source": tune_source,
                "tuner_feature_enabled": bool(feature_enabled),
                "active_tune": dict(effective_tune),
                "graph_lean_display_sign": -1 if bool(effective_tune.get("flipLean")) else 1,
            },
            "config": dict(effective_tune),
            "columns": {},
        }

    times = [float(row.get("time", 0.0) or 0.0) for row in rows]
    gps_lean_base = [float_or_none(row.get("gps_lean_base_deg", row.get("gps_lean_ref_deg"))) for row in rows]
    gps_long_base = [float_or_none(row.get("gps_long_base_g", row.get("gps_long_ref_g"))) for row in rows]
    max_sigma = max(
        float(effective_tune.get("leanGaussianSigma", 0.0) or 0.0),
        float(effective_tune.get("longGaussianSigma", 0.0) or 0.0),
    )
    smoothing_context = max(2, int(math.ceil(max_sigma * 6.0)))
    context_start = max(0, start - smoothing_context)
    context_end = min(row_count, end + smoothing_context)
    context_base = _extract_base_signals(rows[context_start:context_end])
    context_tuned = tune_base_signals(context_base, effective_tune)
    slice_offset = start - context_start
    slice_count = max(0, end - start)
    tuned_slice = {
        "display_lean_deg": context_tuned["display_lean_deg"][slice_offset:slice_offset + slice_count],
        "display_long_g": context_tuned["display_long_g"][slice_offset:slice_offset + slice_count],
        "display_lat_g": context_tuned["display_lat_g"][slice_offset:slice_offset + slice_count],
    }
    slice_times = times[start:end]
    alignment = estimate_playback_reference_alignment(
        slice_times,
        tuned_slice["display_lean_deg"],
        tuned_slice["display_long_g"],
        gps_lean_base[start:end],
        gps_long_base[start:end],
        effective_tune,
    )
    gps_lag_ms = int(alignment.get("gps_lag_ms_applied", effective_tune.get("gpsLagMs", 0) or 0))
    gps_lean_lag_ms = int(effective_tune.get("gpsLeanLagMs") if effective_tune.get("gpsLeanLagMs") is not None else gps_lag_ms)
    gps_long_lag_ms = int(effective_tune.get("gpsLongLagMs") if effective_tune.get("gpsLongLagMs") is not None else gps_lag_ms)
    offsets = resolve_alignment_offsets(effective_tune, gps_lag_ms)
    aligned_gps = build_aligned_gps_series_for_targets(rows, slice_times, offsets["aligned_path_offset_ms"])
    display_gps = build_display_gps_series_for_targets(rows, slice_times, offsets["path_offset_ms"])
    gps_lean_ref = apply_reference_sign(sample_series_with_time_offset_targets(times, gps_lean_base, slice_times, offsets["lean_ref_offset_ms"]), alignment.get("gps_lean_ref_sign", 1))
    gps_long_ref = apply_reference_sign(sample_series_with_time_offset_targets(times, gps_long_base, slice_times, offsets["long_ref_offset_ms"]), alignment.get("gps_long_ref_sign", 1))
    frame_meta = _alignment_frame_meta(rows, start, end)
    meta = {
        "tune_source": tune_source,
        "tuner_feature_enabled": bool(feature_enabled),
        "active_tune": dict(effective_tune),
        "gps_lag_ms_applied": gps_lag_ms,
        "gps_lean_lag_ms_applied": gps_lean_lag_ms,
        "gps_long_lag_ms_applied": gps_long_lag_ms,
        "gps_lag_source": alignment.get("gps_lag_source", "configured"),
        "gps_lean_ref_sign": alignment.get("gps_lean_ref_sign", 1),
        "gps_long_ref_sign": alignment.get("gps_long_ref_sign", 1),
        "gps_lag_score": alignment.get("gps_lag_score"),
        "gps_lag_configured_ms": effective_tune.get("gpsLagMs", 0),
        "alignment_mode": "single_lag",
        "path_trim_ms": effective_tune.get("pathTrimMs", 0),
        "graph_lean_display_sign": -1 if bool(effective_tune.get("flipLean")) else 1,
        "alignment_confidence": alignment.get("alignment_confidence"),
        "alignment_lean_points": alignment.get("alignment_lean_points"),
        "alignment_long_points": alignment.get("alignment_long_points"),
        "alignment_frame_points": frame_meta["points"],
        "alignment_frame_laps": frame_meta["laps"],
        "alignment_frame_label": frame_meta["label"],
    }
    return {
        "kind": "playback_tune_patch",
        "start_index": start,
        "end_index": end,
        "meta": meta,
        "config": dict(effective_tune),
        "columns": {
            "aligned_lat": [rounded_or_none(value, 6) for value in aligned_gps["lat"]],
            "aligned_lon": [rounded_or_none(value, 6) for value in aligned_gps["lon"]],
            "aligned_speed": [rounded_or_none(value, 1) for value in aligned_gps["speed"]],
            "aligned_heading_deg": [rounded_or_none(value, 1) for value in aligned_gps["heading"]],
            "display_lat": [rounded_or_none(value, 6) for value in display_gps["lat"]],
            "display_lon": [rounded_or_none(value, 6) for value in display_gps["lon"]],
            "display_speed": [rounded_or_none(value, 1) for value in display_gps["speed"]],
            "display_heading_deg": [rounded_or_none(value, 1) for value in display_gps["heading"]],
            "display_lean_deg": [rounded_or_none(value, 1) for value in tuned_slice["display_lean_deg"]],
            "display_long_g": [rounded_or_none(value, 3) for value in tuned_slice["display_long_g"]],
            "display_lat_g": [rounded_or_none(value, 3) for value in tuned_slice["display_lat_g"]],
            "gps_lean_ref_deg": [rounded_or_none(value, 1) for value in gps_lean_ref],
            "gps_long_ref_g": [rounded_or_none(value, 3) for value in gps_long_ref],
        },
    }


def retune_playback_rows(rows: List[Dict[str, Any]], tune: Dict[str, Any]) -> Dict[str, Any]:
    base_signals = _extract_base_signals(rows)
    tuned = tune_base_signals(base_signals, tune)
    times = [float(row.get("time", 0.0) or 0.0) for row in rows]
    raw_gps = _extract_raw_gps(rows)
    alignment = estimate_playback_reference_alignment(
        times,
        tuned["display_lean_deg"],
        tuned["display_long_g"],
        [float_or_none(row.get("gps_lean_base_deg", row.get("gps_lean_ref_deg"))) for row in rows],
        [float_or_none(row.get("gps_long_base_g", row.get("gps_long_ref_g"))) for row in rows],
        tune,
    )
    gps_lag_ms = int(alignment.get("gps_lag_ms_applied", tune.get("gpsLagMs", 0) or 0))
    gps_lean_lag_ms = gps_lag_ms
    gps_long_lag_ms = gps_lag_ms
    offsets = resolve_alignment_offsets(tune, gps_lag_ms)
    aligned_gps = build_aligned_gps_series_from_rows(times, raw_gps, offsets["aligned_path_offset_ms"])
    display_gps = build_display_gps_series_from_rows(times, raw_gps, offsets["path_offset_ms"])
    shifted_lean = apply_reference_sign(
        sample_series_with_time_offset(times, [float_or_none(row.get("gps_lean_base_deg", row.get("gps_lean_ref_deg"))) for row in rows], offsets["lean_ref_offset_ms"]),
        alignment.get("gps_lean_ref_sign", 1),
    )
    shifted_long = apply_reference_sign(
        sample_series_with_time_offset(times, [float_or_none(row.get("gps_long_base_g", row.get("gps_long_ref_g"))) for row in rows], offsets["long_ref_offset_ms"]),
        alignment.get("gps_long_ref_sign", 1),
    )
    frame_meta = _alignment_frame_meta(rows, 0, len(rows))

    out_rows = []
    for index, row in enumerate(rows):
        item = dict(row)
        item["display_lat"] = rounded_or_none(display_gps["lat"][index], 6)
        item["display_lon"] = rounded_or_none(display_gps["lon"][index], 6)
        item["display_speed_kmh"] = rounded_or_none(display_gps["speed"][index], 1)
        item["display_heading_deg"] = rounded_or_none(display_gps["heading"][index], 1)
        item["aligned_lat"] = rounded_or_none(aligned_gps["lat"][index], 6)
        item["aligned_lon"] = rounded_or_none(aligned_gps["lon"][index], 6)
        item["aligned_speed_kmh"] = rounded_or_none(aligned_gps["speed"][index], 1)
        item["aligned_heading_deg"] = rounded_or_none(aligned_gps["heading"][index], 1)
        item["display_lean_deg"] = rounded_or_none(tuned["display_lean_deg"][index], 1)
        item["display_long_g"] = rounded_or_none(tuned["display_long_g"][index], 3)
        item["display_lat_g"] = rounded_or_none(tuned["display_lat_g"][index], 3)
        item["gps_lean_ref_deg"] = rounded_or_none(shifted_lean[index], 1)
        item["gps_long_ref_g"] = rounded_or_none(shifted_long[index], 3)
        item["gps_lag_ms_applied"] = gps_lag_ms
        item["gps_lean_lag_ms_applied"] = gps_lean_lag_ms
        item["gps_long_lag_ms_applied"] = gps_long_lag_ms
        item["gps_lean_ref_sign"] = alignment.get("gps_lean_ref_sign", 1)
        item["gps_long_ref_sign"] = alignment.get("gps_long_ref_sign", 1)
        out_rows.append(item)

    return {
        "rows": out_rows,
        "meta": {
            "gps_lag_ms_applied": gps_lag_ms,
            "gps_lean_lag_ms_applied": gps_lean_lag_ms,
            "gps_long_lag_ms_applied": gps_long_lag_ms,
            "gps_lag_source": alignment.get("gps_lag_source", "configured"),
            "gps_lean_ref_sign": alignment.get("gps_lean_ref_sign", 1),
            "gps_long_ref_sign": alignment.get("gps_long_ref_sign", 1),
            "gps_lag_score": alignment.get("gps_lag_score"),
            "alignment_mode": "single_lag",
            "path_trim_ms": tune.get("pathTrimMs", 0),
            "alignment_confidence": alignment.get("alignment_confidence"),
            "alignment_lean_points": alignment.get("alignment_lean_points"),
            "alignment_long_points": alignment.get("alignment_long_points"),
            "alignment_frame_points": frame_meta["points"],
            "alignment_frame_laps": frame_meta["laps"],
            "alignment_frame_label": frame_meta["label"],
        },
    }


def build_display_gps_series_from_rows(times: List[float], raw_gps: Dict[str, List[Optional[float]]], gps_offset_ms: int) -> Dict[str, List[Optional[float]]]:
    aligned = build_aligned_gps_series_from_rows(times, raw_gps, gps_offset_ms)
    lat, lon = smooth_display_path(aligned["lat"], aligned["lon"])
    speed = rate_limit_series(list(aligned["speed"]), times, 120.0)
    heading = heading_from_series(lat, lon)
    return {"lat": lat, "lon": lon, "speed": speed, "heading": heading}


def build_display_gps_series_for_targets(rows: List[Dict[str, Any]], target_times: List[float], gps_offset_ms: int) -> Dict[str, List[Optional[float]]]:
    aligned = build_aligned_gps_series_for_targets(rows, target_times, gps_offset_ms)
    lat, lon = smooth_display_path(aligned["lat"], aligned["lon"])
    speed = rate_limit_series(list(aligned["speed"]), target_times, 120.0)
    heading = heading_from_series(lat, lon)
    return {"lat": lat, "lon": lon, "speed": speed, "heading": heading}


def build_aligned_gps_series_from_rows(times: List[float], raw_gps: Dict[str, List[Optional[float]]], gps_offset_ms: int) -> Dict[str, List[Optional[float]]]:
    count = len(times)
    empty = [None] * count
    anchors = []
    for index, time_rel in enumerate(times):
        lat = float_or_none(raw_gps["lat"][index])
        lon = float_or_none(raw_gps["lon"][index])
        speed = float_or_none(raw_gps["speed"][index])
        if lat is None or lon is None:
            continue
        anchors.append((time_rel, lat, lon, speed or 0.0))
    if not anchors:
        return {"lat": empty[:], "lon": empty[:], "speed": empty[:], "heading": empty[:]}
    if len(anchors) == 1:
        lat, lon, speed = anchors[0][1], anchors[0][2], anchors[0][3]
        return {
            "lat": [lat] * count,
            "lon": [lon] * count,
            "speed": [speed] * count,
            "heading": [None] * count,
        }
    offset_sec = float(gps_offset_ms or 0) / 1000.0
    targets = [time_rel + offset_sec for time_rel in times]
    lat, lon, speed = linear_aligned_gps(anchors, targets)
    heading = heading_from_series(lat, lon)
    return {"lat": lat, "lon": lon, "speed": speed, "heading": heading}


def build_aligned_gps_series_for_targets(rows: List[Dict[str, Any]], target_times: List[float], gps_offset_ms: int) -> Dict[str, List[Optional[float]]]:
    count = len(target_times)
    empty = [None] * count
    anchors = []
    for row in rows:
        lat = float_or_none(row.get("lat"))
        lon = float_or_none(row.get("lon"))
        speed = float_or_none(row.get("speed_kmh"))
        time_rel = float_or_none(row.get("time"))
        if time_rel is None or lat is None or lon is None:
            continue
        anchors.append((time_rel, lat, lon, speed or 0.0))
    if not anchors:
        return {"lat": empty[:], "lon": empty[:], "speed": empty[:], "heading": empty[:]}
    if len(anchors) == 1:
        lat, lon, speed = anchors[0][1], anchors[0][2], anchors[0][3]
        return {
            "lat": [lat] * count,
            "lon": [lon] * count,
            "speed": [speed] * count,
            "heading": [None] * count,
        }
    offset_sec = float(gps_offset_ms or 0) / 1000.0
    targets = [time_rel + offset_sec for time_rel in target_times]
    lat, lon, speed = linear_aligned_gps(anchors, targets)
    heading = heading_from_series(lat, lon)
    return {"lat": lat, "lon": lon, "speed": speed, "heading": heading}


def linear_aligned_gps(anchors: List[tuple], targets: List[float]) -> tuple:
    lats: List[Optional[float]] = []
    lons: List[Optional[float]] = []
    speeds: List[Optional[float]] = []
    segment_index = 0
    last_segment = len(anchors) - 2
    for target in targets:
        while segment_index < last_segment and target > anchors[segment_index + 1][0]:
            segment_index += 1
        left = anchors[segment_index]
        right = anchors[min(segment_index + 1, len(anchors) - 1)]
        left_time, left_lat, left_lon, left_speed = left
        right_time, right_lat, right_lon, right_speed = right
        dt = max(1e-3, right_time - left_time)
        u = max(0.0, min(1.0, (target - left_time) / dt))
        lats.append(left_lat + ((right_lat - left_lat) * u))
        lons.append(left_lon + ((right_lon - left_lon) * u))
        speeds.append(left_speed + ((right_speed - left_speed) * u))
    return lats, lons, speeds


def estimate_playback_reference_alignment(times: List[float], imu_lean: List[float], imu_long: List[float], gps_lean: List[Optional[float]], gps_long: List[Optional[float]], tune: Dict[str, Any]) -> Dict[str, Any]:
    configured_lag = int(tune.get("gpsLagMs", 0) or 0)
    if not tune.get("gpsLagAutoEnabled", False) or not times or len(times) < 3:
        return _with_configured_sign_overrides({
            "gps_lag_ms_applied": configured_lag,
            "gps_lag_source": "disabled" if not tune.get("gpsLagAutoEnabled", False) else "configured",
            "gps_lean_ref_sign": 1,
            "gps_long_ref_sign": 1,
            "gps_lag_score": None,
            "alignment_confidence": None,
            "alignment_lean_points": 0,
            "alignment_long_points": 0,
        }, tune)

    min_lag = int(tune.get("gpsLagMinMs", 0) or 0)
    max_lag = int(tune.get("gpsLagMaxMs", 3000) or 3000)
    step = max(10, int(tune.get("gpsLagStepMs", 50) or 50))
    best_score = -1.0
    best = {
        "gps_lag_ms_applied": configured_lag,
        "gps_lag_source": "configured",
        "gps_lean_ref_sign": 1,
        "gps_long_ref_sign": 1,
        "gps_lag_score": None,
    }
    configured = None
    for lag_ms in range(min_lag, max_lag + 1, step):
        candidate = score_reference_alignment(times, imu_lean, imu_long, gps_lean, gps_long, lag_ms, tune)
        if candidate is None:
            continue
        if lag_ms == configured_lag:
            configured = candidate
        if candidate["score"] > best_score:
            best_score = candidate["score"]
            best = alignment_result(lag_ms, "auto", candidate)
    if configured is None:
        configured = score_reference_alignment(times, imu_lean, imu_long, gps_lean, gps_long, configured_lag, tune)
    min_improvement = float(tune.get("gpsLagMinImprovement", 0.0) or 0.0)
    if configured is not None and best_score < configured["score"] + min_improvement:
        return _with_configured_sign_overrides(alignment_result(configured_lag, "configured", configured), tune)
    return _with_configured_sign_overrides(best, tune)


def score_reference_alignment(times: List[float], imu_lean: List[float], imu_long: List[float], gps_lean: List[Optional[float]], gps_long: List[Optional[float]], lag_ms: int, tune: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    offsets = resolve_alignment_offsets(tune or get_default_playback_tune(), lag_ms)
    shifted_lean = sample_series_with_time_offset(times, gps_lean, offsets["lean_ref_offset_ms"])
    shifted_long = sample_series_with_time_offset(times, gps_long, offsets["long_ref_offset_ms"])
    lean_stats = series_correlation_stats(imu_lean, shifted_lean, min_abs=3.0)
    long_stats = series_correlation_stats(imu_long, shifted_long, min_abs=0.03)
    lean_corr = None if lean_stats is None else lean_stats["corr"]
    long_corr = None if long_stats is None else long_stats["corr"]
    if long_corr is not None:
        score = abs(long_corr)
        score_basis = "longitudinal_only"
    elif lean_corr is not None:
        # Lean stays available as a low-trust fallback for sparse/weak sessions,
        # but it no longer drives the primary timing solution.
        score = abs(lean_corr) * 0.25
        score_basis = "lean_fallback"
    else:
        return None
    return {
        "score": score,
        "score_basis": score_basis,
        "lean_corr": lean_corr,
        "long_corr": long_corr,
        "lean_points": 0 if lean_stats is None else lean_stats["points"],
        "long_points": 0 if long_stats is None else long_stats["points"],
    }


def alignment_result(lag_ms: int, source: str, candidate: Dict[str, Any]) -> Dict[str, Any]:
    lean_corr = candidate.get("lean_corr")
    long_corr = candidate.get("long_corr")
    return {
        "gps_lag_ms_applied": lag_ms,
        "gps_lag_source": source,
        "gps_lean_ref_sign": -1 if lean_corr is not None and lean_corr < 0 else 1,
        "gps_long_ref_sign": -1 if long_corr is not None and long_corr < 0 else 1,
        "gps_lag_score": round(float(candidate.get("score", 0.0)), 4),
        "alignment_confidence": round(float(candidate.get("score", 0.0)), 4),
        "alignment_lean_points": int(candidate.get("lean_points", 0) or 0),
        "alignment_long_points": int(candidate.get("long_points", 0) or 0),
    }


def sample_series_with_time_offset(times: List[float], values: List[Optional[float]], offset_ms: int) -> List[Optional[float]]:
    if not values or len(values) != len(times):
        return []
    offset_sec = float(offset_ms) / 1000.0
    shifted = []
    source_index = 0
    for current_time in times:
        target = current_time + offset_sec
        while source_index + 1 < len(times) and times[source_index + 1] <= target:
            source_index += 1
        if source_index + 1 < len(times):
            left_distance = abs(times[source_index] - target)
            right_distance = abs(times[source_index + 1] - target)
            closest = source_index if left_distance <= right_distance else source_index + 1
        else:
            closest = source_index
        shifted.append(values[closest])
    return shifted


def sample_series_with_time_offset_targets(times: List[float], values: List[Optional[float]], target_times: List[float], offset_ms: int) -> List[Optional[float]]:
    if not values or len(values) != len(times):
        return []
    offset_sec = float(offset_ms) / 1000.0
    shifted = []
    source_index = 0
    for current_time in target_times:
        target = current_time + offset_sec
        while source_index + 1 < len(times) and times[source_index + 1] <= target:
            source_index += 1
        if source_index + 1 < len(times):
            left_distance = abs(times[source_index] - target)
            right_distance = abs(times[source_index + 1] - target)
            closest = source_index if left_distance <= right_distance else source_index + 1
        else:
            closest = source_index
        shifted.append(values[closest])
    return shifted


def shift_series_by_lag(times: List[float], values: List[Optional[float]], lag_ms: int) -> List[Optional[float]]:
    # Backward-compatible wrapper for older callers that interpret positive lag
    # as sampling an earlier GPS value.
    return sample_series_with_time_offset(times, values, -int(lag_ms or 0))


def shift_series_by_lag_targets(times: List[float], values: List[Optional[float]], target_times: List[float], lag_ms: int) -> List[Optional[float]]:
    # Backward-compatible wrapper for older callers that interpret positive lag
    # as sampling an earlier GPS value.
    return sample_series_with_time_offset_targets(times, values, target_times, -int(lag_ms or 0))


def apply_reference_sign(values: List[Optional[float]], sign: int) -> List[Optional[float]]:
    multiplier = -1.0 if sign == -1 else 1.0
    return [None if value is None else float(value) * multiplier for value in values]


def series_correlation(a_values: List[float], b_values: List[Optional[float]], min_abs: float = 0.0) -> Optional[float]:
    stats = series_correlation_stats(a_values, b_values, min_abs=min_abs)
    return None if stats is None else stats["corr"]


def series_correlation_stats(a_values: List[float], b_values: List[Optional[float]], min_abs: float = 0.0) -> Optional[Dict[str, Any]]:
    pairs = []
    for a_raw, b_raw in zip(a_values, b_values):
        a = float_or_none(a_raw)
        b = float_or_none(b_raw)
        if a is None or b is None:
            continue
        if max(abs(a), abs(b)) < min_abs:
            continue
        pairs.append((a, b))
    if len(pairs) < 20:
        return None
    mean_a = sum(a for a, _ in pairs) / len(pairs)
    mean_b = sum(b for _, b in pairs) / len(pairs)
    num = sum((a - mean_a) * (b - mean_b) for a, b in pairs)
    den_a = math.sqrt(sum((a - mean_a) ** 2 for a, _ in pairs))
    den_b = math.sqrt(sum((b - mean_b) ** 2 for _, b in pairs))
    if den_a <= 1e-9 or den_b <= 1e-9:
        return None
    return {
        "corr": num / (den_a * den_b),
        "points": len(pairs),
    }


def _alignment_frame_meta(rows: List[Dict[str, Any]], start: int, end: int) -> Dict[str, Any]:
    subset = list(rows[start:end])
    laps = []
    for row in subset:
        lap_number = row.get("lap_number")
        if lap_number is None:
            continue
        if lap_number not in laps:
            laps.append(lap_number)
    lap_count = len(laps)
    if lap_count <= 0:
        label = "session_window"
    elif lap_count == 1:
        label = "1_lap_span"
    else:
        label = f"{lap_count}_lap_spans"
    return {
        "points": max(0, end - start),
        "laps": lap_count,
        "label": label,
    }


def hermite_display_gps(anchors: List[tuple], targets: List[float]) -> tuple:
    origin_lat = anchors[0][1]
    origin_lon = anchors[0][2]
    lat_scale = 111320.0
    lon_scale = 111320.0 * math.cos(math.radians(origin_lat))
    lon_scale = lon_scale if abs(lon_scale) > 1e-9 else 1.0
    points = []
    for time_rel, lat, lon, speed in anchors:
        points.append({"time": float(time_rel), "x": (lon - origin_lon) * lon_scale, "y": (origin_lat - lat) * lat_scale, "speed": float(speed)})
    tangents = []
    for index, point in enumerate(points):
        if index == 0:
            other = points[1]
            dt = max(1e-3, other["time"] - point["time"])
            tangents.append({"dx": (other["x"] - point["x"]) / dt, "dy": (other["y"] - point["y"]) / dt})
        elif index == len(points) - 1:
            other = points[index - 1]
            dt = max(1e-3, point["time"] - other["time"])
            tangents.append({"dx": (point["x"] - other["x"]) / dt, "dy": (point["y"] - other["y"]) / dt})
        else:
            prev = points[index - 1]
            nxt = points[index + 1]
            dt = max(1e-3, nxt["time"] - prev["time"])
            tangents.append({"dx": (nxt["x"] - prev["x"]) / dt, "dy": (nxt["y"] - prev["y"]) / dt})
    lats = []
    lons = []
    speeds = []
    segment_index = 0
    last_segment = len(points) - 2
    for target in targets:
        while segment_index < last_segment and target > points[segment_index + 1]["time"]:
            segment_index += 1
        a = points[segment_index]
        b = points[min(segment_index + 1, len(points) - 1)]
        dt = max(1e-3, b["time"] - a["time"])
        u = max(0.0, min(1.0, (target - a["time"]) / dt))
        h00 = (2 * u * u * u) - (3 * u * u) + 1
        h10 = (u * u * u) - (2 * u * u) + u
        h01 = (-2 * u * u * u) + (3 * u * u)
        h11 = (u * u * u) - (u * u)
        tangent_a = tangents[segment_index]
        tangent_b = tangents[min(segment_index + 1, len(tangents) - 1)]
        x = (h00 * a["x"]) + (h10 * dt * tangent_a["dx"]) + (h01 * b["x"]) + (h11 * dt * tangent_b["dx"])
        y = (h00 * a["y"]) + (h10 * dt * tangent_a["dy"]) + (h01 * b["y"]) + (h11 * dt * tangent_b["dy"])
        speed = a["speed"] + ((b["speed"] - a["speed"]) * u)
        lats.append(origin_lat - (y / lat_scale))
        lons.append(origin_lon + (x / lon_scale))
        speeds.append(speed)
    return lats, lons, speeds


def smooth_display_path(lats: List[Optional[float]], lons: List[Optional[float]]) -> tuple:
    if len(lats) < 3:
        return lats, lons
    out_lat = []
    out_lon = []
    for index in range(len(lats)):
        lo = max(0, index - 1)
        hi = min(len(lats), index + 2)
        lat_values = [lats[i] for i in range(lo, hi) if float_or_none(lats[i]) is not None]
        lon_values = [lons[i] for i in range(lo, hi) if float_or_none(lons[i]) is not None]
        out_lat.append(sum(lat_values) / len(lat_values) if lat_values else lats[index])
        out_lon.append(sum(lon_values) / len(lon_values) if lon_values else lons[index])
    return out_lat, out_lon


def rate_limit_series(values: List[Optional[float]], times: List[float], max_delta_per_sec: float) -> List[Optional[float]]:
    if not values:
        return []
    out = [float(values[0]) if values[0] is not None else None]
    for index in range(1, len(values)):
        value = float_or_none(values[index])
        if value is None:
            out.append(out[-1])
            continue
        if out[-1] is None:
            out.append(value)
            continue
        dt = max(0.001, float(times[index] - times[index - 1])) if index < len(times) else 0.01
        limit = float(max_delta_per_sec) * dt
        delta = value - out[-1]
        if delta > limit:
            out.append(out[-1] + limit)
        elif delta < -limit:
            out.append(out[-1] - limit)
        else:
            out.append(value)
    return out


def heading_from_series(lats: List[Optional[float]], lons: List[Optional[float]]) -> List[Optional[float]]:
    headings: List[Optional[float]] = [None] * len(lats)
    for index in range(len(lats)):
        prev_index = max(0, index - 1)
        next_index = min(len(lats) - 1, index + 1)
        if prev_index == next_index:
            continue
        lat1 = float_or_none(lats[prev_index])
        lon1 = float_or_none(lons[prev_index])
        lat2 = float_or_none(lats[next_index])
        lon2 = float_or_none(lons[next_index])
        if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
            continue
        headings[index] = bearing_deg(lat1, lon1, lat2, lon2)
    return headings


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(lat2_r)
    y = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def float_or_none(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def rounded_or_none(value: Any, precision: int):
    number = float_or_none(value)
    return None if number is None else round(number, precision)


def _moving_average(values: List[float], window: int) -> List[float]:
    if window <= 1 or not values:
        return [float(value or 0.0) for value in values]
    out = []
    total = 0.0
    queue = []
    for value in values:
        queue.append(float(value or 0.0))
        total += float(value or 0.0)
        if len(queue) > window:
            total -= queue.pop(0)
        out.append(total / len(queue))
    return out


def _gaussian_smooth(values: List[float], sigma: float) -> List[float]:
    if sigma <= 0.0 or not values:
        return [float(value or 0.0) for value in values]
    radius = max(1, int(math.ceil(sigma * 3.0)))
    kernel = []
    for offset in range(-radius, radius + 1):
        kernel.append(math.exp(-((offset * offset) / max(1e-9, 2.0 * sigma * sigma))))
    kernel_sum = sum(kernel) or 1.0
    kernel = [value / kernel_sum for value in kernel]
    out = []
    count = len(values)
    for index in range(count):
        total = 0.0
        for kernel_index, weight in enumerate(kernel):
            offset = kernel_index - radius
            source = min(count - 1, max(0, index + offset))
            total += float(values[source] or 0.0) * weight
        out.append(total)
    return out


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _angle_delta_deg(target: float, current: float) -> float:
    delta = (target - current + 180.0) % 360.0 - 180.0
    return delta


def _soft_trust(value: float, good: float, bad: float) -> float:
    if good == bad:
        return 1.0 if value <= good else 0.0
    if good < bad:
        return _clamp((bad - value) / (bad - good), 0.0, 1.0)
    return _clamp((value - bad) / (good - bad), 0.0, 1.0)


def _normalize_tune_value(key: str, value: Any):
    rule = _TUNE_RULES[key]
    if rule["type"] == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off"}:
                return False
        if isinstance(value, (int, float)):
            return bool(value)
        raise ValueError(f"{key} must be a boolean")
    if rule["type"] == "nullable_int":
        if value is None or value == "":
            return None
        number = int(float(value))
        if number < rule["min"] or number > rule["max"]:
            raise ValueError(f"{key} must be between {rule['min']} and {rule['max']}")
        return number
    if rule["type"] == "enum":
        string_value = str(value)
        if string_value not in rule["values"]:
            raise ValueError(f"{key} must be one of {', '.join(sorted(rule['values']))}")
        return string_value
    if rule["type"] == "sign":
        number = int(float(value))
        if number not in (-1, 1):
            raise ValueError(f"{key} must be -1 or 1")
        return number
    if rule["type"] == "int":
        number = int(float(value))
        if number < rule["min"] or number > rule["max"]:
            raise ValueError(f"{key} must be between {rule['min']} and {rule['max']}")
        return number
    number = float(value)
    if number < rule["min"] or number > rule["max"]:
        raise ValueError(f"{key} must be between {rule['min']} and {rule['max']}")
    return number


def _extract_base_signals(rows: List[Dict[str, Any]]) -> Dict[str, List[float]]:
    lean_key = "imu_lean_base_deg" if any("imu_lean_base_deg" in row for row in rows) else "lean_deg"
    long_key = "imu_long_base_g" if any("imu_long_base_g" in row for row in rows) else "long_g"
    lat_key = "imu_lat_base_g" if any("imu_lat_base_g" in row for row in rows) else "lat_g"
    return {
        "lean_deg": [float(row.get(lean_key, 0.0) or 0.0) for row in rows],
        "long_g": [float(row.get(long_key, 0.0) or 0.0) for row in rows],
        "lat_g": [float(row.get(lat_key, 0.0) or 0.0) for row in rows],
    }


def _extract_raw_gps(rows: List[Dict[str, Any]]) -> Dict[str, List[Optional[float]]]:
    return {
        "lat": [float_or_none(row.get("lat")) for row in rows],
        "lon": [float_or_none(row.get("lon")) for row in rows],
        "speed": [float_or_none(row.get("speed_kmh")) for row in rows],
    }


def _with_configured_sign_overrides(alignment: Dict[str, Any], tune: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(alignment)
    if "gpsLeanRefSign" in tune:
        out["gps_lean_ref_sign"] = -1 if int(tune.get("gpsLeanRefSign") or 1) < 0 else 1
    if "gpsLongRefSign" in tune:
        out["gps_long_ref_sign"] = -1 if int(tune.get("gpsLongRefSign") or 1) < 0 else 1
    return out
