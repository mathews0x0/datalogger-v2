import argparse
import csv
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path


SVG_PATH = Path("/Users/mj/Downloads/Layout.svg")
OUT_PATH = Path("/Users/mj/Documents/datalogger-v2/track_overlay.svg")
MIN_SPEED = 20.0


def tokenize_path(d):
    return re.findall(r"[A-Za-z]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", d)


def cubic(p0, p1, p2, p3, t):
    mt = 1 - t
    return (
        (mt**3) * p0[0] + 3 * (mt**2) * t * p1[0] + 3 * mt * (t**2) * p2[0] + (t**3) * p3[0],
        (mt**3) * p0[1] + 3 * (mt**2) * t * p1[1] + 3 * mt * (t**2) * p2[1] + (t**3) * p3[1],
    )


def sample_path(d, curve_steps=12):
    tokens = tokenize_path(d)
    i = 0
    cur = (0.0, 0.0)
    start = (0.0, 0.0)
    cmd = None
    polys = []
    poly = []
    last_ctrl = None

    def next_num():
        nonlocal i
        value = float(tokens[i])
        i += 1
        return value

    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]
            i += 1

        if cmd == "M":
            if poly:
                polys.append(poly)
            cur = (next_num(), next_num())
            start = cur
            poly = [cur]
            last_ctrl = None
            while i < len(tokens) and not tokens[i].isalpha():
                cur = (next_num(), next_num())
                poly.append(cur)
            continue

        if cmd == "l":
            while i < len(tokens) and not tokens[i].isalpha():
                cur = (cur[0] + next_num(), cur[1] + next_num())
                poly.append(cur)
                last_ctrl = None
            continue

        if cmd == "c":
            while i < len(tokens) and not tokens[i].isalpha():
                p1 = (cur[0] + next_num(), cur[1] + next_num())
                p2 = (cur[0] + next_num(), cur[1] + next_num())
                p3 = (cur[0] + next_num(), cur[1] + next_num())
                for step in range(1, curve_steps + 1):
                    poly.append(cubic(cur, p1, p2, p3, step / curve_steps))
                cur = p3
                last_ctrl = p2
            continue

        if cmd == "s":
            while i < len(tokens) and not tokens[i].isalpha():
                p1 = cur if last_ctrl is None else (2 * cur[0] - last_ctrl[0], 2 * cur[1] - last_ctrl[1])
                p2 = (cur[0] + next_num(), cur[1] + next_num())
                p3 = (cur[0] + next_num(), cur[1] + next_num())
                for step in range(1, curve_steps + 1):
                    poly.append(cubic(cur, p1, p2, p3, step / curve_steps))
                cur = p3
                last_ctrl = p2
            continue

        if cmd == "Z":
            if poly and poly[0] != poly[-1]:
                poly.append(poly[0])
            polys.append(poly)
            poly = []
            cur = start
            last_ctrl = None
            continue

        raise ValueError(f"Unhandled SVG command: {cmd}")

    if poly:
        polys.append(poly)

    return polys


def poly_area(poly):
    return 0.5 * sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(poly, poly[1:]))


def centroid(points):
    return (
        sum(x for x, _ in points) / len(points),
        sum(y for _, y in points) / len(points),
    )


def principal_angle(points):
    mx, my = centroid(points)
    sxx = sum((x - mx) * (x - mx) for x, y in points)
    syy = sum((y - my) * (y - my) for x, y in points)
    sxy = sum((x - mx) * (y - my) for x, y in points)
    return 0.5 * math.atan2(2 * sxy, sxx - syy)


def point_in_poly(p, poly):
    x, y = p
    inside = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:]):
        if (y1 > y) != (y2 > y):
            xin = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < xin:
                inside = not inside
    return inside


def point_segment_distance(p, a, b):
    px, py = p
    ax, ay = a
    bx, by = b
    dx = bx - ax
    dy = by - ay
    denom = dx * dx + dy * dy
    if denom == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / denom
    t = max(0.0, min(1.0, t))
    qx = ax + t * dx
    qy = ay + t * dy
    return math.hypot(px - qx, py - qy)


def polyline_lengths(poly):
    lengths = [0.0]
    total = 0.0
    for a, b in zip(poly, poly[1:]):
        total += math.hypot(b[0] - a[0], b[1] - a[1])
        lengths.append(total)
    return lengths, total


def resample_closed_polyline(poly, count):
    lengths, total = polyline_lengths(poly)
    result = []
    seg = 0
    for i in range(count):
        target = (i / count) * total
        while seg + 1 < len(lengths) and lengths[seg + 1] < target:
            seg += 1
        a = poly[seg]
        b = poly[seg + 1]
        span = lengths[seg + 1] - lengths[seg]
        t = 0.0 if span == 0 else (target - lengths[seg]) / span
        result.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
    return result


def centerline_from_bounds(outer, inner, count=360):
    outer_r = resample_closed_polyline(outer, count)
    inner_r = resample_closed_polyline(inner, count)
    return [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(outer_r, inner_r)]


def transform_points(points, scale, theta, tx, ty, reflect=False):
    ct = math.cos(theta)
    st = math.sin(theta)
    out = []
    for x, y in points:
        xr = -x if reflect else x
        out.append((scale * (xr * ct - y * st) + tx, scale * (xr * st + y * ct) + ty))
    return out


def rotate_points(points, deg, cx, cy):
    theta = math.radians(deg)
    ct = math.cos(theta)
    st = math.sin(theta)
    return [
        (cx + (x - cx) * ct - (y - cy) * st, cy + (x - cx) * st + (y - cy) * ct)
        for x, y in points
    ]


def fit_count(points, outer, inner):
    inside = 0
    inner_hits = 0
    for p in points:
        in_outer = point_in_poly(p, outer)
        in_inner = point_in_poly(p, inner)
        if in_outer and not in_inner:
            inside += 1
        if in_inner:
            inner_hits += 1
    return inside, inner_hits


def centerline_error(points, centerline):
    total = 0.0
    for p in points:
        total += min(point_segment_distance(p, a, b) for a, b in zip(centerline, centerline[1:] + centerline[:1]))
    return total / len(points)


def read_track():
    root = ET.parse(SVG_PATH).getroot()
    ns = {"svg": "http://www.w3.org/2000/svg"}
    path = root.find(".//svg:path", ns)
    polys = sample_path(path.attrib["d"])
    order = sorted(range(len(polys)), key=lambda idx: abs(poly_area(polys[idx])), reverse=True)
    return root, path.attrib["d"], polys[order[0]], polys[order[1]]


def read_gps_points(csv_path):
    lat_lon = []
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (
                row["row_type"] == "G"
                and row["lat"]
                and row["lon"]
                and float(row["speed"] or 0.0) >= MIN_SPEED
            ):
                lat_lon.append((float(row["lat"]), float(row["lon"])))

    lat0 = sum(lat for lat, _ in lat_lon) / len(lat_lon)
    lon0 = sum(lon for _, lon in lat_lon) / len(lat_lon)
    meters_per_deg_lat = 111320.0
    meters_per_deg_lon = 111320.0 * math.cos(math.radians(lat0))

    return [
        ((lon - lon0) * meters_per_deg_lon, -(lat - lat0) * meters_per_deg_lat)
        for lat, lon in lat_lon
    ]


def find_transform(gps_points, outer, inner):
    track_center = centroid(outer)
    centerline = centerline_from_bounds(outer, inner)
    base_theta = principal_angle(outer) - principal_angle(gps_points)

    outer_x = [x for x, _ in outer]
    outer_y = [y for _, y in outer]
    gps_x = [x for x, _ in gps_points]
    gps_y = [y for _, y in gps_points]
    base_scale = min(
        (max(outer_x) - min(outer_x)) / (max(gps_x) - min(gps_x)),
        (max(outer_y) - min(outer_y)) / (max(gps_y) - min(gps_y)),
    )
    min_scale = base_scale * 0.75
    max_scale = base_scale * 1.35

    search = gps_points[::100]
    best = None

    for reflect in (False, True):
        for dtheta_deg in (-3, 0, 3):
            theta = base_theta + math.radians(dtheta_deg)
            for scale_mul in (0.95, 1.0, 1.05, 1.1):
                scale = base_scale * scale_mul
                base = transform_points(search, scale, theta, 0, 0, reflect)
                cx, cy = centroid(base)
                tx0 = track_center[0] - cx
                ty0 = track_center[1] - cy

                for dx in (-30, 0, 30):
                    for dy in (-30, 0, 30):
                        tx = tx0 + dx
                        ty = ty0 + dy
                        pts = transform_points(search, scale, theta, tx, ty, reflect)
                        inside, inner_hits = fit_count(pts, outer, inner)
                        frac = inside / len(pts)
                        center_err = centerline_error(pts, centerline)
                        score = frac - 0.35 * (inner_hits / len(pts)) - 0.0025 * center_err
                        if best is None or score > best["score"]:
                            best = {
                                "score": score,
                                "reflect": reflect,
                                "theta": theta,
                                "scale": scale,
                                "tx": tx,
                                "ty": ty,
                            }

    for step_theta_deg, step_scale, step_xy in (
        (1.0, 0.02 * base_scale, 10),
        (0.3, 0.008 * base_scale, 4),
    ):
        improved = True
        while improved:
            improved = False
            current_score = best["score"]
            candidates = [
                (best["theta"] + math.radians(step_theta_deg), best["scale"], best["tx"], best["ty"]),
                (best["theta"] - math.radians(step_theta_deg), best["scale"], best["tx"], best["ty"]),
                (best["theta"], best["scale"] + step_scale, best["tx"], best["ty"]),
                (best["theta"], best["scale"] - step_scale, best["tx"], best["ty"]),
                (best["theta"], best["scale"], best["tx"] + step_xy, best["ty"]),
                (best["theta"], best["scale"], best["tx"] - step_xy, best["ty"]),
                (best["theta"], best["scale"], best["tx"], best["ty"] + step_xy),
                (best["theta"], best["scale"], best["tx"], best["ty"] - step_xy),
            ]

            for theta, scale, tx, ty in candidates:
                if scale < min_scale or scale > max_scale:
                    continue
                pts = transform_points(search, scale, theta, tx, ty, best["reflect"])
                inside, inner_hits = fit_count(pts, outer, inner)
                frac = inside / len(pts)
                center_err = centerline_error(pts, centerline)
                score = frac - 0.35 * (inner_hits / len(pts)) - 0.0025 * center_err
                if score > current_score:
                    best.update({"score": score, "theta": theta, "scale": scale, "tx": tx, "ty": ty})
                    current_score = score
                    improved = True

    return best


def make_polyline(points):
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def write_overlay(root, path_d, transformed_points, track_rotate_deg=0.0, pivot_x=None, pivot_y=None):
    view_box = root.attrib["viewBox"]
    transform_attr = ""
    if track_rotate_deg and pivot_x is not None and pivot_y is not None:
        transform_attr = f' transform="rotate({track_rotate_deg:.4f} {pivot_x:.2f} {pivot_y:.2f})"'
    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}">
  <defs>
    <style>
      .track {{
        fill: none;
        stroke: #111111;
        stroke-width: 3px;
        stroke-miterlimit: 10;
      }}
      .telemetry-dots {{
        fill: #e53935;
        fill-opacity: 0.22;
      }}
      .telemetry-line {{
        fill: none;
        stroke: #1565c0;
        stroke-width: 1.2px;
        stroke-linecap: round;
        stroke-linejoin: round;
        stroke-opacity: 0.65;
      }}
    </style>
  </defs>
  <rect width="100%" height="100%" fill="#ffffff"/>
  <path class="track" d="{path_d}"{transform_attr}/>
  <polyline class="telemetry-line" points="{make_polyline(transformed_points[::3])}"/>
  <g class="telemetry-dots">
    {"".join(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.7"/>' for x, y in transformed_points[::6])}
  </g>
</svg>
"""
    OUT_PATH.write_text(svg)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    parser.add_argument("--track-rotate-deg", type=float, default=0.0)
    parser.add_argument("--pivot-x", type=float)
    parser.add_argument("--pivot-y", type=float)
    return parser.parse_args()


def main():
    global OUT_PATH
    args = parse_args()
    OUT_PATH = args.out

    root, path_d, outer, inner = read_track()
    gps_points = read_gps_points(args.csv)
    transform = find_transform(gps_points, outer, inner)
    transformed = transform_points(
        gps_points,
        transform["scale"],
        transform["theta"],
        transform["tx"],
        transform["ty"],
        transform["reflect"],
    )
    scored_outer = outer
    scored_inner = inner
    if args.track_rotate_deg and args.pivot_x is not None and args.pivot_y is not None:
        scored_outer = rotate_points(outer, args.track_rotate_deg, args.pivot_x, args.pivot_y)
        scored_inner = rotate_points(inner, args.track_rotate_deg, args.pivot_x, args.pivot_y)
    inside, inner_hits = fit_count(transformed, scored_outer, scored_inner)
    outside = len(transformed) - inside - inner_hits
    write_overlay(root, path_d, transformed, args.track_rotate_deg, args.pivot_x, args.pivot_y)

    print(f"overlay={OUT_PATH}")
    print(f"speed_filter_gte={MIN_SPEED:.1f}")
    if args.track_rotate_deg and args.pivot_x is not None and args.pivot_y is not None:
        print(
            "track_rotation "
            f"deg={args.track_rotate_deg:.4f} "
            f"pivot=({args.pivot_x:.2f},{args.pivot_y:.2f})"
        )
    print(
        "fit "
        f"inside={inside / len(transformed):.4f} "
        f"inner={inner_hits / len(transformed):.4f} "
        f"outside={outside / len(transformed):.4f}"
    )
    print(
        "transform "
        f"reflect={transform['reflect']} "
        f"theta_deg={math.degrees(transform['theta']):.4f} "
        f"scale={transform['scale']:.6f} "
        f"tx={transform['tx']:.3f} "
        f"ty={transform['ty']:.3f}"
    )


if __name__ == "__main__":
    main()
