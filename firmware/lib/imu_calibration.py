import math
import os
import time
import ujson


IMU_PROFILES_PATH = "/data/metadata/imu_profiles.json"
IMU_CAL_VERSION = 1
PROFILE_LABELS = ("tank", "tail", "stem", "generic")


def _ensure_metadata_dir():
    try:
        os.mkdir("/data")
    except OSError:
        pass
    try:
        os.mkdir("/data/metadata")
    except OSError:
        pass


def _default_store():
    return {"version": IMU_CAL_VERSION, "selected_profile_id": "", "profiles": []}


def load_store():
    try:
        with open(IMU_PROFILES_PATH, "r") as f:
            data = ujson.load(f)
        if not isinstance(data, dict):
            return _default_store()
        store = _default_store()
        store["selected_profile_id"] = str(data.get("selected_profile_id") or "")
        profiles = data.get("profiles") or []
        if isinstance(profiles, list):
            store["profiles"] = profiles
        return store
    except Exception:
        return _default_store()


def save_store(store):
    try:
        _ensure_metadata_dir()
        tmp_path = IMU_PROFILES_PATH + ".tmp"
        with open(tmp_path, "w") as f:
            ujson.dump(store, f)
        try:
            os.remove(IMU_PROFILES_PATH)
        except OSError:
            pass
        os.rename(tmp_path, IMU_PROFILES_PATH)
        return True
    except Exception as e:
        print("[IMU] Failed to save calibration store:", e)
        return False


def list_profiles():
    return load_store().get("profiles", [])


def get_profile(profile_id):
    if not profile_id:
        return None
    for profile in list_profiles():
        if str(profile.get("id") or "") == str(profile_id):
            return profile
    return None


def get_profile_by_label(label):
    label = str(label or "").lower()
    for profile in list_profiles():
        if str(profile.get("label") or "").lower() == label:
            return profile
    return None


def get_selected_profile():
    store = load_store()
    profile_id = store.get("selected_profile_id") or ""
    if not profile_id:
        return None
    for profile in store.get("profiles", []):
        if str(profile.get("id") or "") == str(profile_id):
            return profile
    return None


def set_selected_profile(profile_id):
    store = load_store()
    profile_id = str(profile_id or "")
    exists = False
    for profile in store.get("profiles", []):
        if str(profile.get("id") or "") == profile_id:
            exists = True
            break
    if not exists:
        return False
    store["selected_profile_id"] = profile_id
    return save_store(store)


def upsert_profile(profile):
    if not isinstance(profile, dict):
        return False
    store = load_store()
    profiles = store.get("profiles", [])
    profile_id = str(profile.get("id") or "")
    if not profile_id:
        return False
    updated = False
    for idx, existing in enumerate(profiles):
        if str(existing.get("id") or "") == profile_id:
            profiles[idx] = profile
            updated = True
            break
    if not updated:
        profiles.append(profile)
    store["profiles"] = profiles
    store["selected_profile_id"] = profile_id
    return save_store(store)


def build_profile_name(label):
    label = str(label or "generic").lower()
    profile = get_profile_by_label(label)
    if profile and profile.get("name"):
        return str(profile.get("name"))
    suffix = int(time.time()) % 1000
    return "%s-%03d" % (label.upper(), suffix)


def _normalize(v, fallback=None):
    mag = math.sqrt(sum(x * x for x in v))
    if mag <= 1e-9:
        return list(fallback or [0.0, 0.0, 1.0])
    return [x / mag for x in v]


def _dot(a, b):
    return (a[0] * b[0]) + (a[1] * b[1]) + (a[2] * b[2])


def _cross(a, b):
    return [
        (a[1] * b[2]) - (a[2] * b[1]),
        (a[2] * b[0]) - (a[0] * b[2]),
        (a[0] * b[1]) - (a[1] * b[0]),
    ]


def _project_plane(v, normal):
    scale = _dot(v, normal)
    return [v[0] - (scale * normal[0]), v[1] - (scale * normal[1]), v[2] - (scale * normal[2])]


def _mean_triplet(samples, key):
    if not samples:
        return [0.0, 0.0, 0.0]
    total = [0.0, 0.0, 0.0]
    count = 0
    for sample in samples:
        values = sample.get(key) or (0.0, 0.0, 0.0)
        total[0] += float(values[0])
        total[1] += float(values[1])
        total[2] += float(values[2])
        count += 1
    if count <= 0:
        return [0.0, 0.0, 0.0]
    return [total[0] / count, total[1] / count, total[2] / count]


def _rms_triplet(samples, key):
    if not samples:
        return [0.0, 0.0, 0.0]
    total = [0.0, 0.0, 0.0]
    count = 0
    for sample in samples:
        values = sample.get(key) or (0.0, 0.0, 0.0)
        total[0] += float(values[0]) * float(values[0])
        total[1] += float(values[1]) * float(values[1])
        total[2] += float(values[2]) * float(values[2])
        count += 1
    return [
        math.sqrt(total[0] / count),
        math.sqrt(total[1] / count),
        math.sqrt(total[2] / count),
    ]


def build_capture_summary(samples):
    acc_mean = _mean_triplet(samples, "acc")
    gyro_mean = _mean_triplet(samples, "gyro")
    return {
        "count": len(samples),
        "acc_mean": [round(v, 5) for v in acc_mean],
        "gyro_mean": [round(v, 5) for v in gyro_mean],
        "acc_rms": [round(v, 5) for v in _rms_triplet(samples, "acc")],
        "gyro_rms": [round(v, 5) for v in _rms_triplet(samples, "gyro")],
    }


def solve_profile(label, static_summary, engine_summary, left_summary, right_summary, push_summary):
    static_acc = list(static_summary.get("acc_mean") or [0.0, 0.0, 1.0])
    push_acc = list(push_summary.get("acc_mean") or [0.0, 0.0, 0.0])
    left_acc = list(left_summary.get("acc_mean") or static_acc)
    right_acc = list(right_summary.get("acc_mean") or static_acc)
    gyro_bias = list(static_summary.get("gyro_mean") or [0.0, 0.0, 0.0])

    up_vector = _normalize(static_acc, [0.0, 0.0, 1.0])

    push_delta = [push_acc[0] - static_acc[0], push_acc[1] - static_acc[1], push_acc[2] - static_acc[2]]
    push_horizontal = _project_plane(push_delta, up_vector)
    forward_vector = _normalize(push_horizontal, [1.0, 0.0, 0.0])

    lean_delta = [left_acc[0] - right_acc[0], left_acc[1] - right_acc[1], left_acc[2] - right_acc[2]]
    lateral_vector = _normalize(_project_plane(lean_delta, up_vector), [0.0, 1.0, 0.0])
    if abs(_dot(lateral_vector, forward_vector)) > 0.75:
        lateral_vector = _normalize(_cross(up_vector, forward_vector), [0.0, 1.0, 0.0])
    forward_vector = _normalize(_cross(lateral_vector, up_vector), [1.0, 0.0, 0.0])

    left_projection = _dot(left_acc, lateral_vector)
    right_projection = _dot(right_acc, lateral_vector)
    if left_projection < right_projection:
        lateral_vector = [-lateral_vector[0], -lateral_vector[1], -lateral_vector[2]]
        forward_vector = _normalize(_cross(lateral_vector, up_vector), [1.0, 0.0, 0.0])

    vibration_idle = engine_summary.get("acc_rms") or [0.0, 0.0, 0.0]
    vibration_static = static_summary.get("acc_rms") or [0.0, 0.0, 0.0]
    vibration_delta = [
        max(0.0, float(vibration_idle[i]) - float(vibration_static[i]))
        for i in range(3)
    ]

    forward_strength = math.sqrt(sum(v * v for v in push_horizontal))
    lateral_strength = math.sqrt(sum(v * v for v in lean_delta))
    vibration_strength = math.sqrt(sum(v * v for v in vibration_delta))
    quality = min(1.0, 0.45 + min(0.25, forward_strength * 4.0) + min(0.20, lateral_strength * 0.8) - min(0.12, vibration_strength * 0.08))

    sensor_x_bike = [forward_vector[0], lateral_vector[0], up_vector[0]]
    sensor_y_bike = [forward_vector[1], lateral_vector[1], up_vector[1]]
    sensor_z_bike = [forward_vector[2], lateral_vector[2], up_vector[2]]
    mount_pitch_deg = math.degrees(math.atan2(sensor_x_bike[2], max(0.1, sensor_x_bike[0])))
    mount_roll_deg = math.degrees(math.atan2(sensor_y_bike[2], max(0.1, sensor_y_bike[1] if abs(sensor_y_bike[1]) > 0.1 else 1.0)))

    profile = {
        "id": str(label or "generic").lower(),
        "label": str(label or "generic").lower(),
        "name": build_profile_name(label),
        "calibration_version": IMU_CAL_VERSION,
        "created_at": int(time.time()),
        "rotation_matrix": [
            [round(v, 6) for v in forward_vector],
            [round(v, 6) for v in lateral_vector],
            [round(v, 6) for v in up_vector],
        ],
        "gyro_bias": [round(v, 6) for v in gyro_bias],
        "accel_bias": [0.0, 0.0, 0.0],
        "gravity_vector": [round(v, 6) for v in static_acc],
        "mount_tilt": {
            "pitch_deg": round(mount_pitch_deg, 2),
            "roll_deg": round(mount_roll_deg, 2),
        },
        "vibration": {
            "static_acc_rms": static_summary.get("acc_rms") or [0.0, 0.0, 0.0],
            "engine_acc_rms": engine_summary.get("acc_rms") or [0.0, 0.0, 0.0],
            "delta_acc_rms": [round(v, 5) for v in vibration_delta],
        },
        "quality_score": round(max(0.0, min(1.0, quality)), 3),
        "captures": {
            "static": static_summary,
            "engine": engine_summary,
            "lean_left": left_summary,
            "lean_right": right_summary,
            "push_forward": push_summary,
        },
    }
    return profile
