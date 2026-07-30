# Track Layout Generator

Local static web app for aligning telemetry to a track layout, generating layouts from RaceSense CSV telemetry, and exporting a canonical track definition.

## What It Produces

The main output is a JSON manifest with:

- source layout metadata
- source telemetry metadata
- canonical transform values
- manually placed anchor points
- filtered telemetry bounds in canonical view space

You can also export an SVG preview showing the layout and aligned telemetry, plus a package preview SVG showing the layout asset that will be embedded in the canonical package.

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
7. Export JSON, package, and preview artifacts.

On desktop, the settings sidebar scrolls independently while the main layout canvas stays fixed. This keeps the track visible while tuning generated-layout settings or export options.

## Generated Layout V2 Workflow

The tool can also synthesize a layout directly from RaceSense CSV telemetry:

1. Upload a primary CSV in `Generated Layout V2`.
2. Click `Generate V1` to isolate the first complete lap. The start/end closure must be within `Closure Max`; keep this strict, usually `2m`, to avoid connecting pit exit/entry into the layout.
3. Visually validate V1. It uses the lap centerline with `V1 Half Width` as the nominal half-width, then applies smoothing and corner apex bias.
4. Click `Generate V2` to trim the session to the V1 start point, isolate valid laps, infer lateral spread, and build a smoothed layout ribbon.
5. Use `Enhance With More CSVs` to add more sessions from the same track. Extra files are projected into the primary CSV's geo-reference before lap extraction.

`Reject Deviation` is a hard lap-level threshold. If a lap deviates laterally beyond that threshold from the reference line, it is excluded from the V2 envelope. The info table reports the observed min/median/max delta from the original line and the final layout width range.

`Smoothing` controls closed-loop smoothing of the generated centerline and width offsets. Higher values reduce GPS jitter but can soften tight chicanes.

`Corner Apex Bias` compensates for the fact that rider GPS traces usually represent racing lines rather than geometric track centers. On corner sections, higher values allocate more generated width to the outside of the turn and less to the likely apex side. Straight sections stay close to centered.

Generated layouts still support the normal anchor, start/finish, sector generation, JSON export, SVG preview export, and package export paths.

For generated layouts, the inferred centerline and GPS anchors are fixed authoring overlays. Translate/rotate/scale move the generated track ribbon relative to those overlays so the boundary can be adjusted without dragging the GPS basis. `Export Package Preview` reflects the current adjusted ribbon. Package export and preview use the clean package layout only; the centerline is intentionally removed from the package SVG.

## Export Format

The JSON export is intended to become the canonical track reference for RaceSense admin upload. It includes:

- `layout`
- `telemetry`
- `transform`
- `anchors`
- `telemetryBounds`
- `view`

Package export embeds the layout asset in the package payload. `Export Package Preview` downloads the final package layout SVG so it can be inspected before admin upload.
