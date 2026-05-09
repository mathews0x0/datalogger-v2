# IMU Replay Lab

Local static web app for tuning IMU-derived telemetry against GPS-derived baselines.

## Purpose

Use this tool to:

- load a raw session CSV
- compare IMU lean against GPS curvature lean
- compare IMU longitudinal force against GPS speed-derived acceleration/braking
- tune algorithm-specific parameters without touching production server logic
- save local tuning profiles while comparing different algorithm settings

## Run

From the repo root:

```bash
./imu-replay.sh
```

The script stops any existing IMU Replay server on the configured port, starts a fresh local server, and prints the URL. Default URL: `http://localhost:8090/`.

## Algorithm Layer

`processor.js` owns the middle layer between raw CSV rows and replay-ready frames.

Current visible tuning algorithms:

- `processors.calibratedV2Raw`
- `processors.calibratedV2`

Older accel-only, projection, complementary, and Mahony processors remain in code as hidden references, but they are not shown in the UI because the May 2026 simulation pass showed poor agreement with GPS-derived baselines.

Each processor receives parsed session data plus a config object and returns:

- `frames`
- `stats`
- `algorithm`
- `config`

That is the file to edit when testing new lean/brake/accel logic.

## Calibrated V2

`calibratedV2` is the current replay-lab algorithm for comparing attitude-estimator lean against GPS curvature lean.

Detailed algorithm documentation: `docs/calibratedv2_algorithm.md`.

It was created after May 2026 field sessions showed that accelerometer-only lean was not physically valid during dynamic riding. The accelerometer measures specific force, so braking, cornering, bumps, and vibration contaminate a simple accel-angle calculation.

The algorithm:

- consumes both `I` and `G` rows as IMU samples because GPS rows also contain accel/gyro values
- computes `gpsLeanDeg` from GPS curvature only, using smoothed GPS points and `atan(v^2 * curvature / g)`
- detects the observed BMI323 gyro-scale mismatch and applies the 1/16 repair when the field-data signature matches
- subtracts calibration/stationary gyro bias before integration
- selects the effective gyro axis/sign by comparing candidate integrated attitudes against GPS curvature lean
- integrates the selected gyro rate over time for `leanDeg`
- applies gated accelerometer drift correction only when accel magnitude/up-vector conditions are plausible
- emits replay frames at GPS cadence with both `leanDeg` and `gpsLeanDeg`

When `Calibrated V2 Tuned` is selected in the UI, the default tuning values are:

- `Gyro Scale`: `0.07143` (`~1/14`)
- `Smoothing Samples`: `5`
- `Accel Blend Mode`: `hard`
- `Accel Strong Gain`: `0.045`
- `Accel Weak Gain`: `0.010`
- `Lean Gain`: `1.1`
- `Lean Offset Deg`: `0.0`
- `Longitudinal Gain`: `0.65`
- `GPS Lag Ms`: `250`

The lag is applied only to comparison/graph scoring. It accounts for the expected delay between IMU force and the later GPS speed/path response.

`Lean Offset Deg` is a manual signed bias applied after gyro integration and lean gain. Positive shifts the IMU lean curve one direction; negative shifts it the other. The UI also reports `Profile static lean offset`, computed from the saved gravity vector and rotation matrix. Do not use `mount_tilt.roll_deg` directly as lean offset because the rotation matrix already accounts for mount geometry.

`Accel Blend Mode` can be `hard` or `soft`. `hard` uses the original gated correction. `soft` turns the same force/rotation checks into a continuous trust score so accelerometer drift correction fades in/out instead of switching abruptly.

Useful gyro-scale presets for debugging:

- `1/8 = 0.125`
- `1/10 = 0.100`
- `1/12 = 0.0833`
- `1/14 = 0.0714`
- `1/16 = 0.0625`
- `1/32 = 0.03125`

Important limitation: `calibratedV2` uses GPS lean to choose the best gyro axis/sign for the session. It is suitable for replay analysis and algorithm discovery, but it should not be described as a fully independent production IMU-only lean estimator until firmware calibration/metadata can provide the correct axis/sign without GPS assistance.

The canvas visualization is graph-only:

- lean: attitude estimator versus GPS curvature lean
- longitudinal force: positive acceleration above zero and braking below zero, with IMU and GPS overlaid
- GPS track context: static path with an arrowhead at the current cursor sample
- vertical marker: current timeline cursor; clicking a graph moves the marker and track arrowhead to that point

## Tuning Profiles

Profiles are stored in browser `localStorage`, not written to the repo. Each saved profile contains:

- profile name
- selected algorithm id
- current algorithm-specific tuning values

Use `Saved Profile -> New profile` plus a new name to save a separate variant. Select an existing profile and press `Save Profile` to update it with the current algorithm/tuning values.
