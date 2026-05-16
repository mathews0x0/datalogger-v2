# Hermite GPS Enrichment

This note describes the logic used to generate [`temp_data/figure8_hermite_3x.csv`](/Users/mj/Documents/datalogger-v2/temp_data/figure8_hermite_3x.csv:1) from the baseline session [`temp_data/figure8_60pts.csv`](/Users/mj/Documents/datalogger-v2/temp_data/figure8_60pts.csv:1).

The goal is to increase GPS point density by about `3x` without assuming we know the track shape in advance. The only allowed inputs are the CSV rows themselves.

## Inputs

From the session CSV we use:

- `G` rows:
  - `tick_ms`
  - `lat`
  - `lon`
  - `speed`
- `I` rows:
  - retained in the output session so the replay lab still works
- `M` rows:
  - retained in the output session so the IMU profile and session metadata still exist

The Hermite enrichment itself is GPS-driven. It does not require a known track map or figure template.

## High-Level Idea

Straight-line interpolation between two GPS fixes is too crude. It treats each interval independently and tends to create angular or zig-zag motion when the real path is curved.

The Hermite approach fixes that by:

1. Converting GPS lat/lon to local `x,y` meters
2. Estimating a tangent direction at each GPS anchor from neighboring anchors
3. Using cubic Hermite interpolation between each pair of anchors
4. Resampling the path at roughly `3x` the original GPS rate
5. Converting the interpolated `x,y` points back to lat/lon
6. Interpolating speed over the same timestamps
7. Estimating lean from the curvature of the enriched path

This gives a denser path that remains tied to the observed GPS anchors while keeping motion smooth.

## Step 1: Convert Lat/Lon To Local Meters

We first convert the sparse GPS anchors into a local Cartesian frame so interpolation happens in meters rather than degrees.

Using the first GPS point as the origin:

- `x = (lon - origin_lon) * lon_scale`
- `y = (lat - origin_lat) * -lat_scale`

Where:

- `lat_scale = 111320`
- `lon_scale = 111320 * cos(origin_lat)`

This avoids treating latitude and longitude as if they were linear and equally scaled.

## Step 2: Estimate Tangents At GPS Anchors

Hermite interpolation needs a tangent vector at each anchor.

We estimate each tangent from neighboring GPS points:

- first point:
  - tangent from point `0` to point `1`
- last point:
  - tangent from point `n-2` to point `n-1`
- interior point:
  - tangent from point `i-1` to point `i+1`

In code terms:

```text
tangent_i = (p[i+1] - p[i-1]) / (t[i+1] - t[i-1])
```

This is a centered finite-difference estimate. It uses only the observed GPS sequence and gives a local motion direction that is smoother than per-segment headings.

## Step 3: Resample Timestamps At 3x Density

The baseline GPS cadence is about one point every `120 ms`.

To create a `3x` denser GPS stream, we generate new target timestamps every `40 ms`:

- original:
  - `0, 120, 240, ...`
- enriched:
  - `0, 40, 80, 120, 160, ...`

These timestamps define where the new GPS points should exist.

## Step 4: Cubic Hermite Interpolation

For each target timestamp inside a segment `[A, B]`, we compute a normalized time:

```text
u = (t - tA) / (tB - tA)
```

Then we evaluate the cubic Hermite basis:

```text
h00 =  2u^3 - 3u^2 + 1
h10 =  u^3 - 2u^2 + u
h01 = -2u^3 + 3u^2
h11 =  u^3 - u^2
```

And the interpolated position:

```text
P(u) = h00 * A + h10 * dt * mA + h01 * B + h11 * dt * mB
```

Where:

- `A`, `B` are the two GPS anchor positions in local `x,y`
- `mA`, `mB` are the estimated tangents at those anchors
- `dt` is the time span of the segment

This guarantees:

- the enriched path passes through the original anchors
- motion between anchors is smooth
- curvature changes are softer than straight-line interpolation

## Step 5: Convert Back To Lat/Lon

Once we have enriched `x,y` positions, we convert them back into GPS coordinates:

- `lat = origin_lat - y / lat_scale`
- `lon = origin_lon + x / lon_scale`

Those become the enriched `lat` and `lon` values written into the new `G` rows.

## Step 6: Estimate Speed For Enriched Points

We also need speed values on the enriched GPS rows.

For the current implementation, speed is linearly interpolated in time between the two surrounding GPS anchors:

```text
speed(t) = lerp(speedA, speedB, u)
```

This is simple and stable. It does not use track knowledge.

Future versions could improve this by using IMU longitudinal acceleration between anchors.

## Step 7: Estimate Lean For Enriched Points

Lean is not stored directly in the CSV, but we estimated it for the mockups from path curvature and speed.

For each point we estimate local curvature using three consecutive enriched points. From that we estimate lateral acceleration:

```text
a_lat = v^2 * curvature
```

Then convert lateral acceleration into lean:

```text
lean_deg = atan2(a_lat, g)
```

Where:

- `v` is speed in `m/s`
- `g = 9.81`

This is only a path-derived lean estimate. It is not a fused IMU attitude estimate.

## Why This Worked Better Than The Other Mocked Methods

Compared with the tested alternatives:

- better than straight geometric arc forcing:
  - it does not overcommit to a constant-turn assumption for each segment
- cleaner than Catmull-Rom on this baseline:
  - similar shape quality, but slightly calmer derived lean behavior
- smoother than the IMU-guided anchor interpolation mock:
  - less point-to-point noise in the enriched path

The main reason is that Hermite uses local motion direction inferred from neighboring GPS anchors while still passing exactly through the known points.

## Limitations

This method still has real limits:

- noisy GPS anchors will still bend the interpolated curve
- it is geometric, not fully physics-driven
- speed interpolation is simplistic
- it does not yet use IMU yaw rate or acceleration to refine intermediate motion

So this is a strong display-quality baseline, but not necessarily the final best estimator.

## Current Output File

The generated enriched session is:

- [`temp_data/figure8_hermite_3x.csv`](/Users/mj/Documents/datalogger-v2/temp_data/figure8_hermite_3x.csv:1)

It contains:

- original `M` rows
- original `I` rows
- Hermite-enriched `G` rows at about `3x` GPS density

## Recommended Next Improvements

If this becomes the real enrichment path, the next upgrades should be:

1. light GPS denoising in local `x,y` before tangent estimation
2. tangent limiting to reduce overshoot on noisy sessions
3. IMU-informed heading correction between GPS anchors
4. IMU-informed speed refinement instead of pure linear speed interpolation
5. confidence scoring per enriched point

That would keep the current Hermite structure but make it more robust on real telemetry.
