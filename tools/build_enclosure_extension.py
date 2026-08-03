#!/usr/bin/env python3
"""Build a conservative STL extension without changing the supplied body mesh.

The original binary STL triangles are copied verbatim.  A single boxy antenna
bay is added on the blank -X end, with two diagonal M3-style pilot bosses.  A
separate fitted lid is written with matching clearance/counterbore holes.
"""
import argparse
import struct
from pathlib import Path

import numpy as np


def load_binary_stl(path):
    data = Path(path).read_bytes()
    count = struct.unpack_from('<I', data, 80)[0]
    if 84 + 50 * count != len(data):
        raise ValueError('Expected a binary STL')
    triangles = np.empty((count, 3, 3), dtype=np.float64)
    for i in range(count):
        triangles[i] = np.array(
            struct.unpack_from('<9f', data, 96 + 50 * i), dtype=np.float64
        ).reshape(3, 3)
    return triangles


def add_tri(out, a, b, c):
    out.append((np.asarray(a, dtype=np.float64),
                np.asarray(b, dtype=np.float64),
                np.asarray(c, dtype=np.float64)))


def add_box(out, x0, x1, y0, y1, z0, z1):
    v = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    faces = [
        (0, 2, 1), (0, 3, 2),  # bottom
        (4, 5, 6), (4, 6, 7),  # top
        (0, 1, 5), (0, 5, 4),  # y0
        (1, 2, 6), (1, 6, 5),  # x1
        (2, 3, 7), (2, 7, 6),  # y1
        (3, 0, 4), (3, 4, 7),  # x0
    ]
    for i, j, k in faces:
        add_tri(out, v[i], v[j], v[k])


def add_annular_cylinder(out, cx, cy, z0, z1, outer_r, inner_r, segments=64):
    angles = np.linspace(0.0, 2.0 * np.pi, segments, endpoint=False)
    co = np.cos(angles)
    si = np.sin(angles)
    for i in range(segments):
        j = (i + 1) % segments
        po0 = (cx + outer_r * co[i], cy + outer_r * si[i])
        po1 = (cx + outer_r * co[j], cy + outer_r * si[j])
        pi0 = (cx + inner_r * co[i], cy + inner_r * si[i])
        pi1 = (cx + inner_r * co[j], cy + inner_r * si[j])
        # Outer wall and inner wall.
        add_tri(out, (*po0, z0), (*po1, z0), (*po1, z1))
        add_tri(out, (*po0, z0), (*po1, z1), (*po0, z1))
        add_tri(out, (*pi0, z0), (*pi1, z1), (*pi1, z0))
        add_tri(out, (*pi0, z0), (*pi0, z1), (*pi1, z1))
        # Annular top and bottom faces.
        add_tri(out, (*po0, z1), (*po1, z1), (*pi1, z1))
        add_tri(out, (*po0, z1), (*pi1, z1), (*pi0, z1))
        add_tri(out, (*po0, z0), (*pi1, z0), (*po1, z0))
        add_tri(out, (*po0, z0), (*pi0, z0), (*pi1, z0))


def add_prism_polygon(out, polygon, z0, z1):
    """Extrude a 2-D polygon; used for octagonal hole corner fill."""
    n = len(polygon)
    bottom = [(*p, z0) for p in polygon]
    top = [(*p, z1) for p in polygon]
    for i in range(1, n - 1):
        add_tri(out, bottom[0], bottom[i + 1], bottom[i])
        add_tri(out, top[0], top[i], top[i + 1])
    for i in range(n):
        j = (i + 1) % n
        add_tri(out, bottom[i], bottom[j], top[j])
        add_tri(out, bottom[i], top[j], top[i])


def add_solid_cylinder(out, cx, cy, z0, z1, radius, segments=64):
    angles = np.linspace(0.0, 2.0 * np.pi, segments, endpoint=False)
    ring0 = [(cx + radius * np.cos(a), cy + radius * np.sin(a), z0) for a in angles]
    ring1 = [(cx + radius * np.cos(a), cy + radius * np.sin(a), z1) for a in angles]
    for i in range(segments):
        j = (i + 1) % segments
        add_tri(out, ring0[i], ring0[j], ring1[j])
        add_tri(out, ring0[i], ring1[j], ring1[i])
        add_tri(out, (cx, cy, z0), ring0[j], ring0[i])
        add_tri(out, (cx, cy, z1), ring1[i], ring1[j])


def clip_polygon(poly, axis, threshold, keep_greater):
    if not poly:
        return []
    result = []
    for i, current in enumerate(poly):
        previous = poly[i - 1]
        current_value = current[axis]
        previous_value = previous[axis]
        current_inside = (current_value >= threshold) if keep_greater else (current_value <= threshold)
        previous_inside = (previous_value >= threshold) if keep_greater else (previous_value <= threshold)
        if current_inside != previous_inside:
            delta = current_value - previous_value
            t = 0.0 if abs(delta) < 1e-12 else (threshold - previous_value) / delta
            result.append((previous[0] + t * (current[0] - previous[0]),
                           previous[1] + t * (current[1] - previous[1])))
        if current_inside:
            result.append(current)
    return result


def polygon_difference_rectangle(poly, y0, y1, z0, z1):
    """Return disjoint polygon pieces of a triangle outside a yz rectangle."""
    pieces = []
    pieces.append(clip_polygon(poly, 0, y0, False))
    pieces.append(clip_polygon(poly, 0, y1, True))
    middle = clip_polygon(poly, 0, y0, True)
    middle = clip_polygon(middle, 0, y1, False)
    pieces.append(clip_polygon(middle, 1, z0, False))
    pieces.append(clip_polygon(middle, 1, z1, True))
    return [p for p in pieces if len(p) >= 3]


def add_clipped_x_plane_triangle(out, triangle, y0, y1, z0, z1):
    """Keep the portion of an approximately x-planar triangle outside a hole."""
    yz = [(float(v[1]), float(v[2])) for v in triangle]
    p0, p1, p2 = triangle
    base = np.array([[p1[1] - p0[1], p1[2] - p0[2]],
                     [p2[1] - p0[1], p2[2] - p0[2]]])
    for poly in polygon_difference_rectangle(yz, y0, y1, z0, z1):
        mapped = []
        for y, z in poly:
            try:
                u, v = np.linalg.solve(base, np.array([y - p0[1], z - p0[2]]))
                x = p0[0] + u * (p1[0] - p0[0]) + v * (p2[0] - p0[0])
            except np.linalg.LinAlgError:
                x = float(triangle[:, 0].mean())
            mapped.append((x, y, z))
        for i in range(1, len(mapped) - 1):
            add_tri(out, mapped[0], mapped[i], mapped[i + 1])


def add_rectangular_tunnel(out, x0, x1, y0, y1, z0, z1):
    """Add the four wall surfaces exposed by a rectangular through-hole."""
    faces = [
        ((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)),
        ((x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)),
        ((x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)),
        ((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)),
    ]
    for a, b, c, d in faces:
        add_tri(out, a, b, c)
        add_tri(out, a, c, d)


def modify_original_for_wiring(original, xmin, ymin, ymax, bottom_shift=0.0):
    """Remove the marked bump area and cut the centered wire opening."""
    # Move only the lower layer/floor datum.  The display seat, upper walls,
    # and top plane remain at their original Z coordinates.
    working = original.copy()
    working[:, :, 2] = np.where(
        working[:, :, 2] <= 2.8 + 1e-6,
        working[:, :, 2] + bottom_shift,
        working[:, :, 2]
    )
    hole_y0 = (ymin + ymax) / 2.0 - 12.5
    hole_y1 = (ymin + ymax) / 2.0 + 12.5
    floor_top = 2.8 + bottom_shift
    # Keep the opening bottom flush with the floor and increase its height to
    # 12 mm (the original request was 25 x 7 mm, then +5 mm in height).
    hole_z0, hole_z1 = floor_top, floor_top + 12.0
    # The original inner support wall is at this measured x plane.  The outer
    # blank end is at xmin; the added bay lies on the xmin side.
    inner_wall_x = xmin + 9.1
    bump_cx, bump_cy = xmin + 14.3, (ymin + ymax) / 2.0
    bump_x0, bump_x1 = bump_cx - 7.0, bump_cx + 7.0
    bump_y0, bump_y1 = bump_cy - 7.0, bump_cy + 7.0

    edges = working[:, [1, 2, 0]] - working[:, [0, 0, 0]]
    normals = np.cross(edges[:, 0], edges[:, 1])
    normals /= np.maximum(np.linalg.norm(normals, axis=1)[:, None], 1e-12)
    tmin = working.min(axis=1)
    tmax = working.max(axis=1)
    kept = []
    removed_bump = 0
    clipped_wall = 0
    for tri, normal, lo, hi in zip(working, normals, tmin, tmax):
        # Remove the conical mounting bump and the tiny floor fragments under
        # it.  No replacement cylindrical pad is added.
        in_bump_box = (lo[0] >= bump_x0 and hi[0] <= bump_x1 and
                       lo[1] >= bump_y0 and hi[1] <= bump_y1 and
                       hi[2] > 2.6)
        if in_bump_box:
            removed_bump += 1
            continue

        # Cut the hole from both planar faces of the original support wall.
        plane_x = float(tri[:, 0].mean())
        planar_x = (hi[0] - lo[0] < 0.01 and abs(normal[0]) > 0.98 and
                    (abs(plane_x - xmin) < 0.2 or abs(plane_x - inner_wall_x) < 0.2))
        if planar_x:
            yz = tri[:, [1, 2]]
            yz_min = yz.min(axis=0)
            yz_max = yz.max(axis=0)
            # If the triangle's yz bounds intersect the requested opening,
            # replace it with the clipped outside pieces.
            intersects = not (yz_max[0] <= hole_y0 or yz_min[0] >= hole_y1 or
                              yz_max[1] <= hole_z0 or yz_min[1] >= hole_z1)
            if intersects:
                add_clipped_x_plane_triangle(kept, tri, hole_y0, hole_y1, hole_z0, hole_z1)
                clipped_wall += 1
                continue
        kept.append(tuple(v.copy() for v in tri))

    # Four exposed cut faces make the wire opening a closed, printable tunnel.
    add_rectangular_tunnel(kept, xmin - 0.05, inner_wall_x + 0.05,
                           hole_y0, hole_y1, hole_z0, hole_z1)
    return np.array(kept, dtype=np.float64), {
        'hole': (hole_y0, hole_y1, hole_z0, hole_z1),
        'inner_wall_x': inner_wall_x,
        'bump_center': (bump_cx, bump_cy),
        'bump_triangles_removed': removed_bump,
        'wall_triangles_clipped': clipped_wall,
    }


def add_plate_with_octagonal_holes(out, x0, x1, y0, y1, z0, z1, holes, half_extent):
    """Create a rectangular plate with regular-octagonal openings.

    The plate is tiled around each hole's square envelope.  Four triangular
    corner prisms turn the square voids into octagonal openings, which are
    robust for slicing and leave room for a counterbore layer above.
    """
    xcuts = [x0, x1]
    ycuts = [y0, y1]
    for cx, cy in holes:
        xcuts.extend([cx - half_extent, cx + half_extent])
        ycuts.extend([cy - half_extent, cy + half_extent])
    xcuts = sorted(set(xcuts))
    ycuts = sorted(set(ycuts))
    for xa, xb in zip(xcuts, xcuts[1:]):
        for ya, yb in zip(ycuts, ycuts[1:]):
            mx = (xa + xb) / 2.0
            my = (ya + yb) / 2.0
            blocked = any(
                abs(mx - cx) < half_extent and abs(my - cy) < half_extent
                for cx, cy in holes
            )
            if not blocked:
                add_box(out, xa, xb, ya, yb, z0, z1)

    b = half_extent * 0.41421356237
    for cx, cy in holes:
        corners = [
            [(cx - half_extent, cy - half_extent),
             (cx - half_extent, cy - b), (cx - b, cy - half_extent)],
            [(cx + half_extent, cy - half_extent),
             (cx + b, cy - half_extent), (cx + half_extent, cy - b)],
            [(cx + half_extent, cy + half_extent),
             (cx + half_extent, cy + b), (cx + b, cy + half_extent)],
            [(cx - half_extent, cy + half_extent),
             (cx - b, cy + half_extent), (cx - half_extent, cy + b)],
        ]
        for corner in corners:
            add_prism_polygon(out, corner, z0, z1)


def add_plate_with_openings(out, x0, x1, y0, y1, z0, z1,
                            circle_holes, circle_half_extent,
                            rect_holes):
    """Create a plate with octagonal circular holes and exact rectangular slots."""
    xcuts = [x0, x1]
    ycuts = [y0, y1]
    for cx, cy in circle_holes:
        xcuts.extend([cx - circle_half_extent, cx + circle_half_extent])
        ycuts.extend([cy - circle_half_extent, cy + circle_half_extent])
    for rx0, rx1, ry0, ry1 in rect_holes:
        xcuts.extend([rx0, rx1])
        ycuts.extend([ry0, ry1])
    xcuts = sorted(set(xcuts))
    ycuts = sorted(set(ycuts))
    for xa, xb in zip(xcuts, xcuts[1:]):
        for ya, yb in zip(ycuts, ycuts[1:]):
            mx = (xa + xb) / 2.0
            my = (ya + yb) / 2.0
            circle_blocked = any(
                abs(mx - cx) < circle_half_extent and abs(my - cy) < circle_half_extent
                for cx, cy in circle_holes
            )
            rect_blocked = any(rx0 < mx < rx1 and ry0 < my < ry1
                               for rx0, rx1, ry0, ry1 in rect_holes)
            if not circle_blocked and not rect_blocked:
                add_box(out, xa, xb, ya, yb, z0, z1)

    b = circle_half_extent * 0.41421356237
    for cx, cy in circle_holes:
        corners = [
            [(cx - circle_half_extent, cy - circle_half_extent),
             (cx - circle_half_extent, cy - b), (cx - b, cy - circle_half_extent)],
            [(cx + circle_half_extent, cy - circle_half_extent),
             (cx + b, cy - circle_half_extent), (cx + circle_half_extent, cy - b)],
            [(cx + circle_half_extent, cy + circle_half_extent),
             (cx + circle_half_extent, cy + b), (cx + b, cy + circle_half_extent)],
            [(cx - circle_half_extent, cy + circle_half_extent),
             (cx - b, cy + circle_half_extent), (cx - circle_half_extent, cy + b)],
        ]
        for corner in corners:
            add_prism_polygon(out, corner, z0, z1)


def write_binary_stl(path, original, additions):
    all_triangles = list(original) + additions
    header = b'Codex enclosure extension; original mesh preserved'[:80].ljust(80, b' ')
    with Path(path).open('wb') as f:
        f.write(header)
        f.write(struct.pack('<I', len(all_triangles)))
        for tri in all_triangles:
            tri = np.asarray(tri, dtype=np.float64)
            a, b, c = tri
            normal = np.cross(b - a, c - a)
            length = float(np.linalg.norm(normal))
            if length:
                normal /= length
            f.write(struct.pack('<3f', *normal.astype(np.float32)))
            f.write(struct.pack('<9f', *(tri.reshape(-1).astype(np.float32))))
            f.write(b'\x00\x00')


def build_extension(original, body_path, lid_path, extension_length=30.0,
                    depth_increase=6.0, lid_slot_size=25.0):
    points = original.reshape(-1, 3)
    xmin, ymin, zmin = points.min(axis=0)
    xmax, ymax, zmax = points.max(axis=0)
    x0 = xmin - extension_length
    # A small overlap guarantees that the new floor/walls meet the original
    # blank end even where the source mesh has chamfered outer edges.
    x1 = xmin + 0.20
    wall = 2.4
    floor_top = 2.8
    old_top = zmax
    top = zmax
    bottom_shift = -depth_increase
    shifted_zmin = zmin + bottom_shift

    modified_original, modification_info = modify_original_for_wiring(
        original, xmin, ymin, ymax, bottom_shift=bottom_shift
    )
    body = []
    # Single boxy tray: original blank end wall remains untouched and forms
    # the inner boundary of this added bay.
    floor_top = 2.8 + bottom_shift
    add_box(body, x0, x1, ymin, ymax, shifted_zmin, floor_top)
    add_box(body, x0, x1, ymin, ymin + wall, shifted_zmin, top)
    add_box(body, x0, x1, ymax - wall, ymax, shifted_zmin, top)
    add_box(body, x0, x0 + wall, ymin + wall, ymax - wall, shifted_zmin, top)

    # Two diagonal M3-style pilot-hole bosses.  The lid uses matching 3.4 mm
    # clearance holes and 6.4 mm counterbores.
    boss_centers = [
        (x0 + 6.5, ymin + 6.5),
        (x1 - 6.5, ymax - 6.5),
    ]
    for cx, cy in boss_centers:
        add_annular_cylinder(body, cx, cy, floor_top, top,
                             outer_r=4.2, inner_r=1.35)

    lid = []
    lid_x0, lid_x1 = x0 + 0.55, x1 - 0.55
    lid_y0, lid_y1 = ymin + 0.55, ymax - 0.55
    lid_bottom = top + 0.15
    counterbore_floor = top + 1.35
    lid_top = top + 2.75
    slot_cx = (lid_x0 + lid_x1) / 2.0
    slot_cy = (lid_y0 + lid_y1) / 2.0
    slot = (
        slot_cx - lid_slot_size / 2.0, slot_cx + lid_slot_size / 2.0,
        slot_cy - lid_slot_size / 2.0, slot_cy + lid_slot_size / 2.0,
    )
    add_plate_with_openings(
        lid, lid_x0, lid_x1, lid_y0, lid_y1,
        lid_bottom, counterbore_floor, boss_centers, circle_half_extent=1.7,
        rect_holes=[slot]
    )
    add_plate_with_openings(
        lid, lid_x0, lid_x1, lid_y0, lid_y1,
        counterbore_floor, lid_top, boss_centers, circle_half_extent=3.2,
        rect_holes=[slot]
    )

    # Locating skirt under the lid.  Keep it inside the tray's actual inner
    # wall faces and leave FDM-friendly clearance on every side.  The skirt
    # extends below the case lip to provide a positive friction/snap fit.
    skirt_t = 1.4
    skirt_clearance = 0.30
    skirt_x0, skirt_x1 = x0 + wall + skirt_clearance, x1 - skirt_clearance
    skirt_y0, skirt_y1 = ymin + wall + skirt_clearance, ymax - wall - skirt_clearance
    skirt_bottom = top - 2.0
    skirt_top = lid_bottom + 0.1
    add_box(lid, skirt_x0, skirt_x1, skirt_y0, skirt_y0 + skirt_t,
            skirt_bottom, skirt_top)
    add_box(lid, skirt_x0, skirt_x1, skirt_y1 - skirt_t, skirt_y1,
            skirt_bottom, skirt_top)
    add_box(lid, skirt_x0, skirt_x0 + skirt_t, skirt_y0 + skirt_t,
            skirt_y1 - skirt_t, skirt_bottom, skirt_top)
    add_box(lid, skirt_x1 - skirt_t, skirt_x1, skirt_y0 + skirt_t,
            skirt_y1 - skirt_t, skirt_bottom, skirt_top)

    write_binary_stl(body_path, modified_original, body)
    write_binary_stl(lid_path, np.empty((0, 3, 3)), lid)
    return {
        'original_size': (xmax - xmin, ymax - ymin, zmax - zmin),
        'body_size': (xmax - x0, ymax - ymin, top - shifted_zmin),
        'lid_size': (lid_x1 - lid_x0, lid_y1 - lid_y0, lid_top - skirt_bottom),
        'usable_depth_nominal': depth_increase + 14.0,
        'lid_slot': slot,
        'boss_centers': boss_centers,
        'body_triangles_added': len(body),
        'lid_triangles': len(lid),
        'modified_original_triangles': len(modified_original),
        'modification_info': modification_info,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input_stl')
    ap.add_argument('--body-out', required=True)
    ap.add_argument('--lid-out', required=True)
    args = ap.parse_args()
    original = load_binary_stl(args.input_stl)
    info = build_extension(original, args.body_out, args.lid_out)
    print('original triangles:', len(original))
    print('modified original triangles:', info['modified_original_triangles'])
    print('added body triangles:', info['body_triangles_added'])
    print('body envelope mm:', tuple(round(x, 3) for x in info['body_size']))
    print('lid envelope approx mm:', tuple(round(x, 3) for x in info['lid_size']))
    print('nominal usable depth mm:', round(info['usable_depth_nominal'], 3))
    print('lid slot bounds:', tuple(round(v, 3) for v in info['lid_slot']))
    print('diagonal boss centers:', [tuple(round(v, 3) for v in p) for p in info['boss_centers']])
    print('wire hole yz/z bounds:', tuple(round(v, 3) for v in info['modification_info']['hole']))
    print('wire hole inner wall x:', round(info['modification_info']['inner_wall_x'], 3))
    print('flattened bump center:', tuple(round(v, 3) for v in info['modification_info']['bump_center']))
    print('bump triangles removed:', info['modification_info']['bump_triangles_removed'])
    print('wall triangles clipped:', info['modification_info']['wall_triangles_clipped'])
    print('body:', args.body_out)
    print('lid:', args.lid_out)


if __name__ == '__main__':
    main()
