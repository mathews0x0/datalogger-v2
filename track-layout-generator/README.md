# Track Layout Generator

Local static web app for aligning telemetry to a track layout and exporting a canonical track definition.

## What It Produces

The main output is a JSON manifest with:

- source layout metadata
- source telemetry metadata
- canonical transform values
- manually placed anchor points
- filtered telemetry bounds in canonical view space

You can also export an SVG preview showing the layout and aligned telemetry.

## Run

From the repo root:

```bash
cd track-layout-generator
python3 -m http.server 8080
```

Then open `http://localhost:8080`.

## Workflow

1. Load a layout image or SVG.
2. Load a telemetry CSV.
3. Click `Auto Align`.
4. Fine tune with translate / scale / rotation.
5. Drag the layout directly on the canvas if needed.
6. Add anchor points by enabling `Anchor Mode` and clicking.
7. Export JSON and optionally SVG preview.

## Generated Layout V2 Workflow

The tool can also synthesize a layout directly from RaceSense CSV telemetry:

1. Upload a primary CSV in `Generated Layout V2`.
2. Click `Generate V1` to isolate the first complete lap. The start/end closure must be within `Closure Max`; keep this strict, usually `2m`, to avoid connecting pit exit/entry into the layout.
3. Visually validate V1. It uses the lap centerline with `V1 Half Width` on each side.
4. Click `Generate V2` to trim the session to the V1 start point, isolate valid laps, infer lateral spread, and build a smoothed layout ribbon.
5. Use `Enhance With More CSVs` to add more sessions from the same track. Extra files are projected into the primary CSV's geo-reference before lap extraction.

`Reject Deviation` is a hard lap-level threshold. If a lap deviates laterally beyond that threshold from the reference line, it is excluded from the V2 envelope. The info table reports the observed min/median/max delta from the original line and the final layout width range.

Generated layouts still support the normal anchor, start/finish, sector generation, JSON export, SVG preview export, and package export paths.

## Export Format

The JSON export is intended to become the canonical track reference for RaceSense admin upload. It includes:

- `layout`
- `telemetry`
- `transform`
- `anchors`
- `telemetryBounds`
- `view`

The layout asset itself should be stored alongside the JSON or uploaded separately, depending on how RaceSense ingests assets.
