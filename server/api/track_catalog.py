import base64
import json
import math
import re
from pathlib import Path

import api.config as config
from api.models import db, GlobalTrack, TrackMeta
from src.config import GLOBAL_TRACK_ID_MIN
from src.analysis.processing.geo import haversine_distance
GLOBAL_TRACK_TBL_PREFIX = "global_track_"


class TrackPackageError(ValueError):
    pass


def sanitize_track_slug(name):
    slug = re.sub(r"[^a-z0-9_]+", "_", (name or "").strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "track"


def next_global_track_id():
    current_max = db.session.query(db.func.max(GlobalTrack.track_id)).scalar()
    if current_max is None or current_max < GLOBAL_TRACK_ID_MIN:
        return GLOBAL_TRACK_ID_MIN
    return current_max + 1


def decode_embedded_svg(data_url):
    if not data_url or not isinstance(data_url, str):
        raise TrackPackageError("layout.embeddedDataUrl is required")
    prefix = "data:image/svg+xml;base64,"
    if not data_url.startswith(prefix):
        raise TrackPackageError("layout.embeddedDataUrl must be a base64 SVG data URL")
    try:
        return base64.b64decode(data_url[len(prefix):]).decode("utf-8")
    except Exception as exc:
        raise TrackPackageError("layout.embeddedDataUrl is not valid base64 SVG data") from exc


def _package_required(package, path, kinds=None):
    node = package
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise TrackPackageError(f"{path} is required")
        node = node[part]
    if kinds and not isinstance(node, kinds):
        raise TrackPackageError(f"{path} has invalid type")
    return node


def validate_package_payload(package):
    if not isinstance(package, dict):
        raise TrackPackageError("Package payload must be a JSON object")
    _package_required(package, "layout", dict)
    _package_required(package, "layout.embeddedDataUrl")
    _package_required(package, "layout.width", (int, float))
    _package_required(package, "layout.height", (int, float))
    _package_required(package, "telemetry", dict)
    _package_required(package, "telemetry.geoReference", dict)
    _package_required(package, "telemetry.geoReference.lat0", (int, float))
    _package_required(package, "telemetry.geoReference.lon0", (int, float))
    _package_required(package, "telemetry.geoReference.metersPerDegLat", (int, float))
    _package_required(package, "telemetry.geoReference.metersPerDegLon", (int, float))
    _package_required(package, "telemetry.autoAlign", dict)
    _package_required(package, "telemetry.autoAlign.scale", (int, float))
    _package_required(package, "telemetry.autoAlign.rotationDeg", (int, float))
    _package_required(package, "telemetry.autoAlign.translateX", (int, float))
    _package_required(package, "telemetry.autoAlign.translateY", (int, float))
    sampled = package.get("telemetry", {}).get("sampledGpsPoints")
    if not isinstance(sampled, list) or len(sampled) < 4:
        raise TrackPackageError("telemetry.sampledGpsPoints must contain at least 4 anchor samples")
    return package


def build_package_metadata(package):
    geo_reference = package["telemetry"]["geoReference"]
    sampled_points = []
    for point in package["telemetry"]["sampledGpsPoints"]:
        if not isinstance(point, dict):
            continue
        lat = point.get("lat")
        lon = point.get("lon")
        gps = point.get("gps") or {}
        if lat is None:
            lat = gps.get("lat")
        if lon is None:
            lon = gps.get("lon")
        canonical = point.get("canonical", {}) or {}
        local_meters = point.get("localMeters")
        if local_meters is None and lat is not None and lon is not None:
            local_meters = {
                "x": (float(lon) - float(geo_reference["lon0"])) * float(geo_reference["metersPerDegLon"]),
                "y": (float(geo_reference["lat0"]) - float(lat)) * float(geo_reference["metersPerDegLat"]),
            }
        sampled_points.append({
            **point,
            "lat": float(lat) if lat is not None else None,
            "lon": float(lon) if lon is not None else None,
            "canonical": canonical,
            "localMeters": local_meters,
        })
    canonical_points = [p.get("canonical", {}) for p in sampled_points if isinstance(p, dict)]
    xs = [float(p["x"]) for p in canonical_points if "x" in p]
    ys = [float(p["y"]) for p in canonical_points if "y" in p]
    if not xs or not ys:
        raise TrackPackageError("telemetry.sampledGpsPoints must contain canonical x/y points")

    bounds = package.get("telemetryBounds") or {
        "minX": min(xs),
        "maxX": max(xs),
        "minY": min(ys),
        "maxY": max(ys),
    }
    width = max(float(bounds["maxX"]) - float(bounds["minX"]), 1.0)
    height = max(float(bounds["maxY"]) - float(bounds["minY"]), 1.0)
    center = {
        "x": float(bounds["minX"]) + width / 2.0,
        "y": float(bounds["minY"]) + height / 2.0,
    }
    return {
        "version": package.get("version"),
        "layout": {
            "width": int(package["layout"]["width"]),
            "height": int(package["layout"]["height"]),
            "fileName": package["layout"].get("fileName"),
        },
        "geo_reference": geo_reference,
        "auto_align": package["telemetry"]["autoAlign"],
        "sampled_points": sampled_points,
        "telemetry_bounds": bounds,
        "bounds_width": width,
        "bounds_height": height,
        "bounds_center": center,
    }


def _solve_3x3(matrix, values):
    a = [row[:] + [values[idx]] for idx, row in enumerate(matrix)]
    n = 3
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(a[row][col]))
        if abs(a[pivot][col]) < 1e-9:
            return None
        if pivot != col:
            a[col], a[pivot] = a[pivot], a[col]
        pivot_val = a[col][col]
        for j in range(col, n + 1):
            a[col][j] /= pivot_val
        for row in range(n):
            if row == col:
                continue
            factor = a[row][col]
            for j in range(col, n + 1):
                a[row][j] -= factor * a[col][j]
    return [a[idx][n] for idx in range(n)]


def compute_anchor_affine_fit(sampled_points):
    anchors = []
    for point in sampled_points or []:
        local = point.get("localMeters") or {}
        canonical = point.get("canonical") or {}
        if "x" not in local or "y" not in local or "x" not in canonical or "y" not in canonical:
            continue
        anchors.append((
            float(local["x"]),
            float(local["y"]),
            float(canonical["x"]),
            float(canonical["y"]),
        ))
    if len(anchors) < 3:
        return None

    sum_xx = sum(x * x for x, _, _, _ in anchors)
    sum_xy = sum(x * y for x, y, _, _ in anchors)
    sum_yy = sum(y * y for _, y, _, _ in anchors)
    sum_x = sum(x for x, _, _, _ in anchors)
    sum_y = sum(y for _, y, _, _ in anchors)
    count = float(len(anchors))
    matrix = [
        [sum_xx, sum_xy, sum_x],
        [sum_xy, sum_yy, sum_y],
        [sum_x, sum_y, count],
    ]
    x_values = [
        sum(x * cx for x, _, cx, _ in anchors),
        sum(y * cx for _, y, cx, _ in anchors),
        sum(cx for _, _, cx, _ in anchors),
    ]
    y_values = [
        sum(x * cy for x, _, _, cy in anchors),
        sum(y * cy for _, y, _, cy in anchors),
        sum(cy for _, _, _, cy in anchors),
    ]
    x_coeffs = _solve_3x3(matrix, x_values)
    y_coeffs = _solve_3x3(matrix, y_values)
    if not x_coeffs or not y_coeffs:
        return None

    errors = []
    for local_x, local_y, canonical_x, canonical_y in anchors:
        fit_x = x_coeffs[0] * local_x + x_coeffs[1] * local_y + x_coeffs[2]
        fit_y = y_coeffs[0] * local_x + y_coeffs[1] * local_y + y_coeffs[2]
        errors.append(math.hypot(fit_x - canonical_x, fit_y - canonical_y))

    return {
        "x_coeffs": x_coeffs,
        "y_coeffs": y_coeffs,
        "anchor_count": len(anchors),
        "mean_error_px": (sum(errors) / len(errors)) if errors else 0.0,
        "max_error_px": max(errors) if errors else 0.0,
    }


def _orange_preview_svg(svg_text):
    preview = svg_text
    preview = re.sub(r'stroke="#?000000"', 'stroke="#c85b12"', preview, flags=re.IGNORECASE)
    preview = re.sub(r'stroke="#?111111"', 'stroke="#c85b12"', preview, flags=re.IGNORECASE)
    preview = re.sub(r'stroke="#?222222"', 'stroke="#c85b12"', preview, flags=re.IGNORECASE)
    preview = re.sub(r'stroke:\s*#(?:000000|111111|222222)', 'stroke:#c85b12', preview, flags=re.IGNORECASE)
    return preview


def _anchor_geo(anchor, geo_reference, auto_align):
    x = anchor.get("x")
    y = anchor.get("y")
    if x is None or y is None:
        return None

    scale = float(auto_align["scale"])
    theta = math.radians(float(auto_align["rotationDeg"]))
    tx = float(auto_align["translateX"])
    ty = float(auto_align["translateY"])

    x_scaled = (float(x) - tx) / scale
    y_scaled = (float(y) - ty) / scale

    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    local_x = x_scaled * cos_t + y_scaled * sin_t
    local_y = -x_scaled * sin_t + y_scaled * cos_t

    return {
        "lat": float(geo_reference["lat0"]) - (local_y / float(geo_reference["metersPerDegLat"])),
        "lon": float(geo_reference["lon0"]) + (local_x / float(geo_reference["metersPerDegLon"])),
    }


def _extract_start_finish_line(package):
    anchors = package.get("anchors") or []
    sf = [a for a in anchors if "start finish" in (a.get("name") or "").lower()]
    if len(sf) < 2:
        return None
    p1, p2 = sf[:2]
    geo_ref = package["telemetry"]["geoReference"]
    auto_align = package["telemetry"]["autoAlign"]
    g1 = _anchor_geo(p1, geo_ref, auto_align)
    g2 = _anchor_geo(p2, geo_ref, auto_align)
    if not g1 or not g2:
        return None
    return {
        "edge_a": g1,
        "edge_b": g2,
        "center": {
            "lat": (g1["lat"] + g2["lat"]) / 2.0,
            "lon": (g1["lon"] + g2["lon"]) / 2.0,
        },
        "radius_m": 20.0,
    }


def _normalize_start_line(start_line):
    if not start_line:
        return start_line
    center = start_line.get("center") if isinstance(start_line, dict) else None
    if center and "lat" in center and "lon" in center:
        start_line["lat"] = center["lat"]
        start_line["lon"] = center["lon"]
    elif "lat" in start_line and "lon" in start_line:
        start_line["center"] = {"lat": start_line["lat"], "lon": start_line["lon"]}
    return start_line


def _load_existing_centerline(track_dir, existing_track_json):
    centerline = existing_track_json.get("centerline")
    if isinstance(centerline, list) and centerline:
        return centerline
    for filename in ("geometry.json", "auto_fit_geometry.json"):
        path = track_dir / filename
        if not path.exists():
            continue
        data = load_json_file(path)
        centerline = data.get("centerline")
        if isinstance(centerline, list) and centerline:
            return centerline
        coordinates = data.get("coordinates")
        if isinstance(coordinates, list) and coordinates:
            return [{"lat": float(lat), "lon": float(lon)} for lat, lon in coordinates]
    return []


def _centerline_from_package(package):
    sampled_points = package.get("telemetry", {}).get("sampledGpsPoints") or []
    centerline = []
    for point in sampled_points:
        if not isinstance(point, dict):
            continue
        lat = point.get("lat")
        lon = point.get("lon")
        if lat is None or lon is None:
            gps = point.get("gps") or {}
            lat = gps.get("lat")
            lon = gps.get("lon")
        if lat is None or lon is None:
            continue
        centerline.append({"lat": float(lat), "lon": float(lon)})
    return centerline


def _project_line_distance(lat, lon, line):
    return math.hypot(float(lat) - float(line["center"]["lat"]), float(lon) - float(line["center"]["lon"]))


def _interpolate_point(start, end, ratio):
    return {
        "lat": float(start["lat"]) + (float(end["lat"]) - float(start["lat"])) * ratio,
        "lon": float(start["lon"]) + (float(end["lon"]) - float(start["lon"])) * ratio,
    }


def _generate_sectors_from_centerline(centerline, start_line, sector_count):
    if not centerline or len(centerline) < 2:
        return []

    closest_idx = min(
        range(len(centerline)),
        key=lambda idx: _project_line_distance(centerline[idx]["lat"], centerline[idx]["lon"], start_line)
    )
    ordered = centerline[closest_idx:] + centerline[:closest_idx] + [centerline[closest_idx]]

    dists = [0.0]
    total = 0.0
    for idx in range(1, len(ordered)):
        prev = ordered[idx - 1]
        curr = ordered[idx]
        d = haversine_distance(prev["lat"], prev["lon"], curr["lat"], curr["lon"]) * 1000.0
        total += d
        dists.append(total)

    if total <= 0:
        return []

    step = total / sector_count
    dynamic_radius = max(5.0, min(30.0, step * 0.4))
    sectors = []
    for sector_idx in range(1, sector_count + 1):
        target_dist = step * sector_idx
        if sector_idx == sector_count:
            point = ordered[0]
        else:
            segment_idx = next(
                (idx for idx in range(1, len(dists)) if dists[idx] >= target_dist),
                len(dists) - 1,
            )
            prev_dist = dists[segment_idx - 1]
            next_dist = dists[segment_idx]
            if next_dist <= prev_dist:
                point = ordered[segment_idx]
            else:
                ratio = (target_dist - prev_dist) / (next_dist - prev_dist)
                point = _interpolate_point(ordered[segment_idx - 1], ordered[segment_idx], ratio)
        sectors.append({
            "id": f"S{sector_idx}",
            "end_lat": point["lat"],
            "end_lon": point["lon"],
            "radius_m": round(dynamic_radius, 1),
        })
    return sectors


def local_meters_to_canonical(local_x, local_y, auto_align):
    theta = math.radians(float(auto_align["rotationDeg"]))
    scale = float(auto_align["scale"])
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    x_rot = local_x * cos_t - local_y * sin_t
    y_rot = local_x * sin_t + local_y * cos_t
    return {
        "x": x_rot * scale + float(auto_align["translateX"]),
        "y": y_rot * scale + float(auto_align["translateY"]),
    }


def latlon_to_canonical(lat, lon, geo_reference, auto_align):
    local_x = (float(lon) - float(geo_reference["lon0"])) * float(geo_reference["metersPerDegLon"])
    local_y = (float(geo_reference["lat0"]) - float(lat)) * float(geo_reference["metersPerDegLat"])
    return local_meters_to_canonical(local_x, local_y, auto_align)


def get_user_track_stats_dir(user_id, track_id, track_name=None):
    from src.analysis.core.registry_manager import RegistryManager

    folder_name = f"{GLOBAL_TRACK_TBL_PREFIX}{track_id}"
    tracks_dir = config.get_user_tracks_dir(user_id)
    registry = RegistryManager(registry_path=str(tracks_dir))
    registry.register_track(track_id, track_name or f"Track {track_id}", folder_name=folder_name)
    track_dir = tracks_dir / folder_name
    track_dir.mkdir(parents=True, exist_ok=True)
    return track_dir


def load_json_file(path):
    with open(path, "r") as handle:
        return json.load(handle)


def get_track_display_name(track_id, user_id=None):
    if user_id:
        user_track = TrackMeta.query.filter_by(track_id=track_id, user_id=user_id).first()
        if user_track:
            return user_track.track_name
    global_track = GlobalTrack.query.filter_by(track_id=track_id).first()
    if global_track:
        return global_track.track_name
    any_user_track = TrackMeta.query.filter_by(track_id=track_id).first()
    return any_user_track.track_name if any_user_track else "Unknown"


def resolve_track(track_id, user_id=None):
    if user_id:
        user_track = TrackMeta.query.filter_by(track_id=track_id, user_id=user_id).first()
        if user_track:
            return {
                "track_id": track_id,
                "track_scope": "user_fallback",
                "track_source": "session_generated",
                "folder_name": user_track.folder_name,
                "track_name": user_track.track_name,
                "base_dir": config.get_user_tracks_dir(user_id),
                "db_track": user_track,
                "package_version": None,
                "has_canonical_layout": False,
            }
    global_track = GlobalTrack.query.filter_by(track_id=track_id).first()
    if global_track:
        return {
            "track_id": track_id,
            "track_scope": "global",
            "track_source": "global_package",
            "folder_name": global_track.folder_name,
            "track_name": global_track.track_name,
            "base_dir": config.get_global_tracks_dir(),
            "db_track": global_track,
            "package_version": global_track.package_version,
            "has_canonical_layout": bool(global_track.has_canonical_layout),
        }
    return None


def track_file_path(resolved_track, filename):
    return Path(resolved_track["base_dir"]) / resolved_track["folder_name"] / filename


def load_track_json(resolved_track):
    path = track_file_path(resolved_track, "track.json")
    if not path.exists():
        return None
    data = load_json_file(path)
    data["track_scope"] = resolved_track["track_scope"]
    data["track_source"] = resolved_track["track_source"]
    data["package_version"] = resolved_track["package_version"]
    data["has_canonical_layout"] = resolved_track["has_canonical_layout"]
    return data


def load_track_layout(resolved_track):
    path = track_file_path(resolved_track, "layout_metadata.json")
    if not path.exists():
        return None
    payload = load_json_file(path)
    if not payload.get("affine_fit") and payload.get("sampled_points"):
        payload["affine_fit"] = compute_anchor_affine_fit(payload.get("sampled_points"))
    payload["track_id"] = resolved_track["track_id"]
    payload["track_scope"] = resolved_track["track_scope"]
    payload["track_source"] = resolved_track["track_source"]
    payload["package_version"] = resolved_track["package_version"]
    return payload


def upsert_global_track_package(track_name, package, slug=None, track_id=None):
    package = validate_package_payload(package)
    svg_text = decode_embedded_svg(package["layout"]["embeddedDataUrl"])
    preview_svg_text = _orange_preview_svg(svg_text)
    slug = sanitize_track_slug(slug or track_name or package["layout"].get("fileName", "track"))

    global_track = None
    if track_id is not None:
        global_track = GlobalTrack.query.filter_by(track_id=int(track_id)).first()
    if global_track is None:
        global_track = GlobalTrack.query.filter_by(slug=slug).first()

    if global_track is None:
        global_track = GlobalTrack(
            track_id=int(track_id) if track_id is not None else next_global_track_id(),
            slug=slug,
            folder_name=slug,
        )
        db.session.add(global_track)

    metadata = build_package_metadata(package)
    affine_fit = compute_anchor_affine_fit(metadata["sampled_points"])
    global_track.track_name = track_name or package["layout"].get("fileName") or slug.replace("_", " ").title()
    global_track.folder_name = slug
    global_track.package_version = package.get("version")
    global_track.layout_width = metadata["layout"]["width"]
    global_track.layout_height = metadata["layout"]["height"]
    global_track.has_canonical_layout = True
    global_track.match_metadata = json.dumps(metadata)

    track_dir = config.get_global_track_dir(slug)
    track_json_path = track_dir / "track.json"
    existing_track_json = load_json_file(track_json_path) if track_json_path.exists() else {}

    start_line = _extract_start_finish_line(package) or existing_track_json.get("start_line")
    if not start_line:
        start_anchor = package["telemetry"]["sampledGpsPoints"][0]
        start_line = {
            "lat": float(start_anchor["lat"]),
            "lon": float(start_anchor["lon"]),
            "radius_m": 30.0,
        }
    start_line = _normalize_start_line(start_line)

    centerline = _load_existing_centerline(track_dir, existing_track_json)
    if not centerline:
        centerline = _centerline_from_package(package)
    sectors = _generate_sectors_from_centerline(centerline, start_line, config.SECTOR_COUNT)
    if not sectors:
        sectors = existing_track_json.get("sectors", [])

    normalized_track = {
        "track_id": global_track.track_id,
        "track_name": global_track.track_name,
        "name": global_track.track_name,
        "folder_name": global_track.folder_name,
        "track_scope": "global",
        "track_source": "global_package",
        "package_version": global_track.package_version,
        "has_canonical_layout": True,
        "start_line": start_line,
        "centerline": centerline,
        "sectors": sectors,
        "canonical_layout": {
            "width": metadata["layout"]["width"],
            "height": metadata["layout"]["height"],
            "svg_file": "layout.svg",
            "metadata_file": "layout_metadata.json",
        },
    }

    with open(track_dir / "package.json", "w") as handle:
        json.dump(package, handle, indent=2)
    with open(track_dir / "layout.svg", "w") as handle:
        handle.write(svg_text)
    with open(track_dir / "layout_preview.svg", "w") as handle:
        handle.write(preview_svg_text)
    with open(track_dir / "layout_metadata.json", "w") as handle:
        json.dump({
            "svg_path": "layout.svg",
            "preview_svg_path": "layout_preview.svg",
            "svg_data_url": package["layout"]["embeddedDataUrl"],
            "preview_svg_data_url": f"data:image/svg+xml;base64,{base64.b64encode(preview_svg_text.encode('utf-8')).decode('ascii')}",
            "layout_width": metadata["layout"]["width"],
            "layout_height": metadata["layout"]["height"],
            "geo_reference": metadata["geo_reference"],
            "auto_align": metadata["auto_align"],
            "sampled_points": metadata["sampled_points"],
            "affine_fit": affine_fit,
            "telemetry_bounds": metadata["telemetry_bounds"],
            "layout_file_name": metadata["layout"].get("fileName"),
        }, handle, indent=2)
    with open(track_dir / "track.json", "w") as handle:
        json.dump(normalized_track, handle, indent=2)

    db.session.commit()
    return global_track
