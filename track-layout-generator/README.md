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

## Export Format

The JSON export is intended to become the canonical track reference for RaceSense admin upload. It includes:

- `layout`
- `telemetry`
- `transform`
- `anchors`
- `telemetryBounds`
- `view`

The layout asset itself should be stored alongside the JSON or uploaded separately, depending on how RaceSense ingests assets.
