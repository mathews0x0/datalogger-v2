# IMU Replay Lab

Local static web app for replaying a session CSV with a pluggable IMU processing layer.

## Purpose

Use this tool to:

- load a raw session CSV
- replay the run over its GPS path
- visualize derived lean, acceleration, and braking
- iterate on IMU algorithms without touching production server logic

## Run

From the repo root:

```bash
./imu-replay.sh
```

The script stops any existing IMU Replay server on the configured port, starts a fresh local server, and prints the URL. Default URL: `http://localhost:8090/`.

## Algorithm Layer

`processor.js` owns the middle layer between raw CSV rows and replay-ready frames.

Current structure:

- `processors.rawAccelLeanV1`
- `processors.accelOnlyV1`
- `processors.accelOnlySmoothedV1`
- `processors.calibratedV1`
- `processors.calibratedV2`
- `processors.complementaryV1`
- `processors.mahonyV1`

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

When `Calibrated V2` is selected in the UI, optional filters are off by default and the parameters match the settings used during the successful `jinoop/sess_008.csv` analysis.

Important limitation: `calibratedV2` uses GPS lean to choose the best gyro axis/sign for the session. It is suitable for replay analysis and algorithm discovery, but it should not be described as a fully independent production IMU-only lean estimator until firmware calibration/metadata can provide the correct axis/sign without GPS assistance.

The canvas visualization includes a lean comparison graph:

- red line: attitude-estimator lean
- blue line: GPS curvature lean
- vertical marker: current playback frame
