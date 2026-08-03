#!/usr/bin/env python3
"""Small dependency-light STL preview renderer for inspection."""
import argparse
import struct
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def load_stl(path):
    data = Path(path).read_bytes()
    n = struct.unpack_from('<I', data, 80)[0]
    if 84 + 50 * n != len(data):
        raise ValueError('Only binary STL is supported')
    tri = np.empty((n, 3, 3), dtype=np.float32)
    for i in range(n):
        tri[i] = np.array(struct.unpack_from('<9f', data, 96 + 50 * i), dtype=np.float32).reshape(3, 3)
    edges = tri[:, [1, 2, 0]] - tri[:, [0, 0, 0]]
    normals = np.cross(edges[:, 0], edges[:, 1])
    lens = np.linalg.norm(normals, axis=1)
    normals /= np.maximum(lens[:, None], 1e-9)
    return tri, normals


def render(tri, normals, view, width, height, bg=(235, 238, 242)):
    view = np.asarray(view, dtype=float)
    view /= np.linalg.norm(view)
    world_up = np.array([0., 0., 1.])
    right = np.cross(world_up, view)
    right /= np.linalg.norm(right)
    up = np.cross(view, right)
    center = tri.reshape(-1, 3).mean(axis=0)
    points = tri.reshape(-1, 3) - center
    sx = points @ right
    sy = points @ up
    depth = points @ view
    pad = 55
    scale = min((width - 2 * pad) / max(sx.max() - sx.min(), 1e-9),
                (height - 2 * pad) / max(sy.max() - sy.min(), 1e-9))
    px = (width / 2 + sx * scale).reshape(-1, 3)
    py = (height / 2 - sy * scale).reshape(-1, 3)
    d = depth.reshape(-1, 3).mean(axis=1)
    # Painter's order: farther faces first.
    order = np.argsort(d)
    img = Image.new('RGB', (width, height), bg)
    draw = ImageDraw.Draw(img)
    # fixed light direction for a readable solid preview
    light = np.array([-0.55, -0.75, 1.0])
    light /= np.linalg.norm(light)
    for i in order:
        # Use a two-sided diffuse term because imported STL winding can vary.
        shade = 0.28 + 0.72 * abs(float(normals[i] @ light))
        col = tuple(int(c * shade) for c in (74, 118, 154))
        poly = [(int(px[i, j]), int(py[i, j])) for j in range(3)]
        draw.polygon(poly, fill=col)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stl')
    ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--width', type=int, default=1200)
    ap.add_argument('--height', type=int, default=760)
    args = ap.parse_args()
    tri, normals = load_stl(args.stl)
    views = [
        (np.array([1.3, -1.8, 1.15]), 'camera +X'),
        (np.array([-1.3, -1.8, 1.15]), 'camera -X'),
        (np.array([0.0, -2.2, 0.65]), 'camera -Y'),
    ]
    tiles = []
    for v, label in views:
        tile = render(tri, normals, v, args.width // 2, args.height // 2)
        ImageDraw.Draw(tile).text((18, 18), label, fill=(25, 35, 45))
        tiles.append(tile)
    out = Image.new('RGB', (args.width, args.height), (220, 224, 229))
    out.paste(tiles[0], (0, 0))
    out.paste(tiles[1], (args.width // 2, 0))
    out.paste(tiles[2], (args.width // 4, args.height // 2))
    out.save(args.out)
    print(args.out)


if __name__ == '__main__':
    main()
