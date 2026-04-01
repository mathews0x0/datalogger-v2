import argparse
import base64
import math
import struct
import zlib
from pathlib import Path

from align_track_overlay import find_transform, read_gps_points, read_track, rotate_points, transform_points


def principal_angle(points):
    mx = sum(x for x, _ in points) / len(points)
    my = sum(y for _, y in points) / len(points)
    sxx = sum((x - mx) * (x - mx) for x, y in points)
    syy = sum((y - my) * (y - my) for x, y in points)
    sxy = sum((x - mx) * (y - my) for x, y in points)
    return 0.5 * math.atan2(2 * sxy, sxx - syy)


def centroid(points):
    return (
        sum(x for x, _ in points) / len(points),
        sum(y for _, y in points) / len(points),
    )


def png_dark_pixels(png_path):
    data = png_path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    offset = 8
    idat = b""
    width = height = bit_depth = color_type = None

    while offset < len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        offset += 4
        chunk_type = data[offset : offset + 4]
        offset += 4
        chunk = data[offset : offset + length]
        offset += length
        offset += 4

        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, _, _, _ = struct.unpack(">IIBBBBB", chunk)
        elif chunk_type == b"IDAT":
            idat += chunk
        elif chunk_type == b"IEND":
            break

    raw = zlib.decompress(idat)
    channels = {2: 3, 6: 4}[color_type]
    bpp = channels * bit_depth // 8
    stride = width * bpp

    rows = []
    i = 0
    prev = bytearray(stride)
    for _ in range(height):
        filt = raw[i]
        i += 1
        cur = bytearray(raw[i : i + stride])
        i += stride
        if filt == 1:
            for x in range(stride):
                cur[x] = (cur[x] + (cur[x - bpp] if x >= bpp else 0)) & 255
        elif filt == 2:
            for x in range(stride):
                cur[x] = (cur[x] + prev[x]) & 255
        elif filt == 3:
            for x in range(stride):
                cur[x] = (cur[x] + (((cur[x - bpp] if x >= bpp else 0) + prev[x]) // 2)) & 255
        elif filt == 4:
            for x in range(stride):
                a = cur[x - bpp] if x >= bpp else 0
                b = prev[x]
                c = prev[x - bpp] if x >= bpp else 0
                p = a + b - c
                pa = abs(p - a)
                pb = abs(p - b)
                pc = abs(p - c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                cur[x] = (cur[x] + pr) & 255
        rows.append(bytes(cur))
        prev = cur

    points = []
    for y, row in enumerate(rows):
        for x in range(width):
            if x < 320 and y < 220:
                continue
            idx = x * bpp
            r, g, b = row[idx : idx + 3]
            a = row[idx + 3] if bpp == 4 else 255
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            if a > 0 and lum < 210:
                points.append((float(x), float(y)))

    return width, height, points


def map_svg_to_png(points, svg_track_points, png_track_points):
    svg_angle = principal_angle(svg_track_points)
    png_angle = principal_angle(png_track_points)
    theta = png_angle - svg_angle

    sx = [x for x, _ in svg_track_points]
    sy = [y for _, y in svg_track_points]
    px = [x for x, _ in png_track_points]
    py = [y for _, y in png_track_points]
    scale_x = (max(px) - min(px)) / (max(sx) - min(sx))
    scale_y = (max(py) - min(py)) / (max(sy) - min(sy))
    scale = (scale_x + scale_y) / 2.0

    svgcx, svgcy = centroid(svg_track_points)
    pngcx, pngcy = centroid(png_track_points)

    ct = math.cos(theta)
    st = math.sin(theta)
    out = []
    for x, y in points:
        dx = x - svgcx
        dy = y - svgcy
        rx = scale * (dx * ct - dy * st)
        ry = scale * (dx * st + dy * ct)
        out.append((pngcx + rx, pngcy + ry))
    return out, math.degrees(theta), scale


def make_polyline(points):
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--gps-rotate-deg", type=float, default=-3.0)
    parser.add_argument("--pivot-x", type=float, default=724.0)
    parser.add_argument("--pivot-y", type=float, default=526.0)
    parser.add_argument("--track-rotate-deg", type=float, default=0.0)
    parser.add_argument("--track-shift-x", type=float, default=0.0)
    parser.add_argument("--track-shift-y", type=float, default=0.0)
    args = parser.parse_args()

    _, _, outer, inner = read_track()
    svg_track = outer + inner
    gps_points = read_gps_points(args.csv)
    transform = find_transform(gps_points, outer, inner)
    gps_svg = transform_points(
        gps_points,
        transform["scale"],
        transform["theta"],
        transform["tx"],
        transform["ty"],
        transform["reflect"],
    )
    gps_svg = rotate_points(gps_svg, args.gps_rotate_deg, args.pivot_x, args.pivot_y)

    width, height, png_track = png_dark_pixels(args.png)
    gps_png, global_rot_deg, global_scale = map_svg_to_png(gps_svg, svg_track, png_track)
    center_x = width / 2.0
    center_y = height / 2.0
    image_transform = ""
    transforms = []
    if args.track_shift_x or args.track_shift_y:
        transforms.append(f"translate({args.track_shift_x:.2f} {args.track_shift_y:.2f})")
    if args.track_rotate_deg:
        transforms.append(f"rotate({args.track_rotate_deg:.4f} {center_x:.2f} {center_y:.2f})")
    if transforms:
        image_transform = f' transform="{" ".join(transforms)}"'

    encoded = base64.b64encode(args.png.read_bytes()).decode("ascii")
    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">
  <image href="data:image/png;base64,{encoded}" x="0" y="0" width="{width}" height="{height}"{image_transform}/>
  <polyline fill="none" stroke="#1565c0" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" stroke-opacity="0.62" points="{make_polyline(gps_png[::3])}"/>
  <g fill="#e53935" fill-opacity="0.18">
    {"".join(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.2"/>' for x, y in gps_png[::8])}
  </g>
</svg>
"""
    args.out.write_text(svg)

    print(f"overlay={args.out}")
    print(f"png_size={width}x{height}")
    print(f"gps_local_rotation_deg={args.gps_rotate_deg:.4f} pivot=({args.pivot_x:.2f},{args.pivot_y:.2f})")
    print(f"svg_to_png_rotation_deg={global_rot_deg:.4f}")
    print(f"svg_to_png_scale={global_scale:.6f}")
    print(f"track_rotation_deg={args.track_rotate_deg:.4f} center=({center_x:.2f},{center_y:.2f})")
    print(f"track_shift=({args.track_shift_x:.2f},{args.track_shift_y:.2f})")


if __name__ == "__main__":
    main()
