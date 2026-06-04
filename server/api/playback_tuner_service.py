import json
from pathlib import Path
from typing import Any, Dict, Optional

from api.models import AppSetting, db
from src.analysis.core.playback_tuner import apply_tune_to_playback_payload, build_tune_preview_patch, get_default_playback_tune, normalize_playback_tune


PLAYBACK_TUNER_ENABLED_KEY = "playback_tuner_enabled"
PLAYBACK_TUNER_ACTIVE_TUNE_KEY = "playback_tuner_active_tune"
EXPOSED_PLAYBACK_TUNE_KEYS = (
    "gyroScale",
    "leanGaussianSigma",
    "longGaussianSigma",
    "pathTrimMs",
    "flipLean",
    "flipForce",
    "autoAlignEnabled",
)

_TUNE_STORAGE_KEYS = {
    "gyroScale": "gs",
    "leanGaussianSigma": "lgs",
    "longGaussianSigma": "xgs",
    "pathTrimMs": "ptm",
    "flipLean": "fln",
    "flipForce": "ffo",
    "autoAlignEnabled": "aae",
}
_TUNE_STORAGE_KEYS_REVERSE = {value: key for key, value in _TUNE_STORAGE_KEYS.items()}


def _sanitize_tune_payload(tune: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(tune, dict):
        return {}
    allowed = set(get_default_playback_tune().keys())
    return {key: value for key, value in tune.items() if key in allowed}


def _deserialize_tune_setting(raw: str) -> Dict[str, Any]:
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        return {}
    if any(key in get_default_playback_tune() for key in parsed.keys()):
        return _sanitize_tune_payload(parsed)
    expanded = {}
    for key, value in parsed.items():
        full_key = _TUNE_STORAGE_KEYS_REVERSE.get(key)
        if full_key:
            expanded[full_key] = value
    return _sanitize_tune_payload(expanded)


def _serialize_tune_setting(tune: Dict[str, Any]) -> str:
    compact = {}
    for key, value in tune.items():
        compact_key = _TUNE_STORAGE_KEYS.get(key)
        if compact_key:
            compact[compact_key] = value
    return json.dumps(compact, separators=(",", ":"))


def _get_setting(key: str) -> Optional[AppSetting]:
    return AppSetting.query.filter_by(key=key).first()


def _get_or_create_setting(key: str, value: str) -> AppSetting:
    setting = _get_setting(key)
    if setting:
        return setting
    setting = AppSetting(key=key, value=value)
    db.session.add(setting)
    db.session.flush()
    return setting


def get_playback_tuner_state() -> Dict[str, Any]:
    default_tune = _public_tune(get_default_playback_tune())
    enabled_setting = _get_setting(PLAYBACK_TUNER_ENABLED_KEY)
    tune_setting = _get_setting(PLAYBACK_TUNER_ACTIVE_TUNE_KEY)
    enabled = (enabled_setting.value.lower() == "true") if enabled_setting and enabled_setting.value else False
    active_tune = default_tune
    source = "default"
    if tune_setting and tune_setting.value:
        try:
            active_tune = _public_tune(normalize_playback_tune(_deserialize_tune_setting(tune_setting.value), get_default_playback_tune()))
            source = "saved"
        except Exception:
            active_tune = default_tune
            source = "default"
    return {
        "enabled": enabled,
        "active_tune": active_tune,
        "default_tune": default_tune,
        "tune_source": source,
    }


def save_playback_tuner_state(enabled: bool, tune: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    default_tune = _public_tune(get_default_playback_tune())
    normalized = _public_tune(normalize_playback_tune(_sanitize_tune_payload(tune), get_default_playback_tune()))
    enabled_setting = _get_or_create_setting(PLAYBACK_TUNER_ENABLED_KEY, "false")
    enabled_setting.value = "true" if enabled else "false"
    tune_setting = _get_or_create_setting(PLAYBACK_TUNER_ACTIVE_TUNE_KEY, _serialize_tune_setting(default_tune))
    tune_setting.value = _serialize_tune_setting(normalized)
    db.session.commit()
    return {
        "enabled": enabled,
        "active_tune": normalized,
        "default_tune": default_tune,
        "tune_source": "saved",
    }


def load_playback_payload(playback_path: Path) -> Optional[Dict[str, Any]]:
    if not playback_path.exists():
        return None
    with open(playback_path, "r") as handle:
        return json.load(handle)


def build_effective_playback_payload(playback_path: Path) -> Optional[Dict[str, Any]]:
    payload = load_playback_payload(playback_path)
    if payload is None:
        return None
    state = get_playback_tuner_state()
    if not state["enabled"]:
        return payload
    return apply_tune_to_playback_payload(
        payload,
        tune=state["active_tune"],
        tune_source=state["tune_source"],
        feature_enabled=state["enabled"],
    )


def preview_playback_payload(playback_path: Path, tune: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    payload = load_playback_payload(playback_path)
    if payload is None:
        return None
    state = get_playback_tuner_state()
    normalized = normalize_playback_tune(_sanitize_tune_payload(tune), state["active_tune"])
    return apply_tune_to_playback_payload(
        payload,
        tune=normalized,
        tune_source="preview",
        feature_enabled=state["enabled"],
    )


def preview_playback_patch(playback_path: Path, tune: Dict[str, Any], start_index: Optional[int] = None, end_index: Optional[int] = None) -> Optional[Dict[str, Any]]:
    payload = load_playback_payload(playback_path)
    if payload is None:
        return None
    state = get_playback_tuner_state()
    normalized = normalize_playback_tune(_sanitize_tune_payload(tune), state["active_tune"])
    return build_tune_preview_patch(
        payload,
        tune=normalized,
        tune_source="preview",
        feature_enabled=state["enabled"],
        start_index=start_index,
        end_index=end_index,
    )


def compact_playback_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    rows = list((payload or {}).get("rows") or [])
    return compact_playback_rows(rows, payload)


def compact_playback_rows(rows, payload: Dict[str, Any], start_index: int = 0, end_index: Optional[int] = None) -> Dict[str, Any]:
    rows = list(rows or [])
    fields = [
        ("time", "time"),
        ("lat", "lat"),
        ("lon", "lon"),
        ("speed", "speed_kmh"),
        ("heading_deg", "heading_deg"),
        ("lean_deg", "lean_deg"),
        ("long_g", "long_g"),
        ("lat_g", "lat_g"),
        ("accel_g", "accel_g"),
        ("brake_g", "brake_g"),
        ("aligned_lat", "aligned_lat"),
        ("aligned_lon", "aligned_lon"),
        ("aligned_speed", "aligned_speed_kmh"),
        ("aligned_heading_deg", "aligned_heading_deg"),
        ("display_lat", "display_lat"),
        ("display_lon", "display_lon"),
        ("display_speed", "display_speed_kmh"),
        ("display_heading_deg", "display_heading_deg"),
        ("race_lat", "race_lat"),
        ("race_lon", "race_lon"),
        ("display_lean_deg", "display_lean_deg"),
        ("display_long_g", "display_long_g"),
        ("display_lat_g", "display_lat_g"),
        ("lap_number", "lap_number"),
        ("lap_start", "lap_start"),
        ("lap_end", "lap_end"),
        ("sector_index", "sector_index"),
        ("sector_start", "sector_start"),
        ("sector_end", "sector_end"),
        ("gps_is_fix", "gps_is_fix"),
        ("gps_is_valid", "gps_is_valid"),
        ("gps_lean_ref_deg", "gps_lean_ref_deg"),
        ("gps_long_ref_g", "gps_long_ref_g"),
    ]
    columns = {out_key: [row.get(row_key) for row in rows] for out_key, row_key in fields}
    columns["row_index"] = [row.get("row_index", int(start_index or 0) + index) for index, row in enumerate(rows)]
    return {
        "kind": "playback_columns",
        "meta": (payload or {}).get("meta") or {},
        "config": (payload or {}).get("config") or {},
        "laps": (payload or {}).get("laps") or [],
        "start_index": int(start_index or 0),
        "end_index": int(end_index if end_index is not None else (start_index or 0) + len(rows)),
        "row_count": len(rows),
        "columns": columns,
    }


def build_playback_manifest(payload: Dict[str, Any], max_points: int = 2500) -> Dict[str, Any]:
    rows = list((payload or {}).get("rows") or [])
    row_count = len(rows)
    step = max(1, (row_count + max_points - 1) // max_points)
    overview_rows = []
    for index in range(0, row_count, step):
        item = dict(rows[index])
        item["row_index"] = index
        overview_rows.append(item)
    if rows and (not overview_rows or overview_rows[-1].get("row_index") != row_count - 1):
        item = dict(rows[-1])
        item["row_index"] = row_count - 1
        overview_rows.append(item)
    laps = (payload or {}).get("laps") or []
    lap_ranges = []
    for lap in laps:
        start_time = lap.get("start_time")
        end_time = lap.get("end_time")
        if start_time is None:
            continue
        if end_time is None:
            end_time = float(start_time) + float(lap.get("lap_time") or 0.0)
        start_index = _index_for_time(rows, float(start_time))
        end_index = min(row_count, max(start_index + 1, _index_for_time(rows, float(end_time)) + 1))
        lap_ranges.append({
            "lap_number": lap.get("lap_number"),
            "start_time": start_time,
            "end_time": end_time,
            "start_index": start_index,
            "end_index": end_index,
            "row_count": max(0, end_index - start_index),
        })
    overview = compact_playback_rows(overview_rows, payload, start_index=0, end_index=row_count)
    overview["kind"] = "playback_manifest"
    overview["row_count"] = row_count
    overview["overview_step"] = step
    overview["lap_ranges"] = lap_ranges
    return overview


def build_playback_lap_chunk(payload: Dict[str, Any], lap_number: int) -> Optional[Dict[str, Any]]:
    rows = list((payload or {}).get("rows") or [])
    laps = (payload or {}).get("laps") or []
    lap = next((item for item in laps if int(item.get("lap_number") or -1) == int(lap_number)), None)
    if not lap:
        return None
    start_time = float(lap.get("start_time") or 0.0)
    end_time = lap.get("end_time")
    if end_time is None:
        end_time = start_time + float(lap.get("lap_time") or 0.0)
    start_index = _index_for_time(rows, start_time)
    end_index = min(len(rows), max(start_index + 1, _index_for_time(rows, float(end_time)) + 1))
    chunk = compact_playback_rows(rows[start_index:end_index], payload, start_index=start_index, end_index=end_index)
    chunk["kind"] = "playback_lap_chunk"
    chunk["lap_number"] = int(lap_number)
    chunk["laps"] = [lap]
    return chunk


def build_effective_playback_lap_chunk(payload: Dict[str, Any], lap_number: int) -> Optional[Dict[str, Any]]:
    chunk = build_playback_lap_chunk(payload, lap_number)
    if chunk is None:
        return None
    state = get_playback_tuner_state()
    if not state["enabled"]:
        return chunk
    patch = build_tune_preview_patch(
        payload,
        tune=state["active_tune"],
        tune_source=state["tune_source"],
        feature_enabled=state["enabled"],
        start_index=chunk["start_index"],
        end_index=chunk["end_index"],
    )
    patch_start = int(patch.get("start_index") or 0)
    chunk_start = int(chunk.get("start_index") or 0)
    offset = max(0, patch_start - chunk_start)
    for key, values in (patch.get("columns") or {}).items():
        if key not in chunk["columns"] or not isinstance(values, list):
            continue
        for index, value in enumerate(values):
            target = offset + index
            if 0 <= target < len(chunk["columns"][key]):
                chunk["columns"][key][target] = value
    chunk["meta"].update(patch.get("meta") or {})
    chunk["config"] = patch.get("config") or chunk.get("config") or {}
    return chunk


def _index_for_time(rows, target_time: float) -> int:
    if not rows:
        return 0
    lo, hi = 0, len(rows) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if float(rows[mid].get("time") or 0.0) < target_time:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _public_tune(tune: Dict[str, Any]) -> Dict[str, Any]:
    return {key: tune[key] for key in EXPOSED_PLAYBACK_TUNE_KEYS if key in tune}
