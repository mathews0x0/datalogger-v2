# CalibratedV2 Lean Algorithm

**Status:** replay-lab / research algorithm  
**Primary implementation:** `imu-replay/processor.js`  
**Primary UI:** `imu-replay` algorithm selector, `Calibrated V2`

## Purpose

`calibratedV2` estimates motorcycle lean from session telemetry using a gyro-primary attitude estimator and compares it against a GPS-only lean reference.

It was created after field sessions showed that accelerometer-only lean was not physically valid during dynamic riding. During cornering, braking, acceleration, bumps, and vibration, the accelerometer measures specific force, not pure gravity. A simple accelerometer tilt calculation can therefore be smooth and still be wrong.

The algorithm's purpose is to answer two separate questions:

- What does the GPS path imply the bike lean should be?
- Can the IMU gyro attitude estimate produce the same cornering shape?

## Output

The report/replay output is GPS-cadence data:

```text
lat, lon, speed, lean, gps_lean
```

Where:

- `lean` is the calibratedV2 attitude-estimator lean.
- `gps_lean` is calculated from GPS heading/path curvature only.
- Replay frames also expose `leanDeg` and `gpsLeanDeg`.

## Inputs

The estimator expects a session CSV with:

- `I` rows containing IMU accel/gyro samples.
- `G` rows containing GPS fields and also accel/gyro samples.
- `M` marker rows containing `IMU_PROFILE` metadata.

Important input rule:

- `G` rows are also treated as valid IMU samples because they include accel and gyro values.

The algorithm requires the IMU profile rotation matrix. If the profile is missing, calibratedV2 returns no frames and reports a missing-profile error.

## GPS Lean Reference

GPS lean is calculated independently of IMU data.

Processing steps:

1. Convert GPS latitude/longitude into local meter coordinates.
2. Flip the local Y axis to match the replay coordinate convention.
3. Smooth X and Y positions with a 9-point moving average.
4. For each GPS point, choose one neighboring point roughly 0.9 seconds before and one roughly 0.9 seconds after.
5. Estimate signed curvature from the three local points.
6. Suppress weak evidence on straights or noisy GPS sections.
7. Convert lateral acceleration to lean angle.
8. Smooth the final GPS lean series with a 7-point moving average.

The core formula is:

```text
lateral_accel = speed_mps^2 * signed_curvature
gps_lean_deg = atan(lateral_accel / 9.81) in degrees
```

Straight/noise suppression currently rejects points when:

- any segment in the 3-point window is shorter than 3 meters
- speed is below 5 m/s
- midpoint deviation is below 1.25 meters
- absolute curvature is below 0.0035

GPS lean is clamped to +/-60 degrees.

## IMU Attitude Lean

The IMU side is gyro-primary.

Processing steps:

1. Build one ordered telemetry stream from both `I` and `G` rows.
2. Read the calibration profile rotation matrix and gyro bias.
3. Detect whether the field log matches the observed BMI323 gyro-scale problem.
4. Apply gyro scale repair if needed.
5. Subtract gyro bias after scale repair.
6. Test candidate gyro axes/signs.
7. Select the candidate whose integrated attitude best correlates with GPS lean.
8. Run the final gyro integration on the selected axis.
9. Apply gated accelerometer correction only when the accel sample is physically plausible.
10. Smooth final attitude lean with a 5-sample moving average.
11. Sample the attitude lean at each GPS row for report/replay output.

### Gyro Scale Repair

May 2026 field logs showed a likely BMI323 gyro scale/config mismatch of approximately 16x.

calibratedV2 applies an analysis-time repair when both are true:

- detected IMU sample rate is between 45 Hz and 60 Hz
- gyro absolute p99 is above 250

When triggered:

```text
gyro_scale = 1 / 16
```

The same scale is applied to gyro bias before bias subtraction.

This is a replay-lab repair, not a firmware solution. Firmware should eventually emit correctly scaled gyro values.

### Axis Selection

The estimator currently tests these candidate roll-rate axes:

- calibrated forward
- negative calibrated forward
- calibrated lateral
- negative calibrated lateral
- calibrated up
- negative calibrated up
- raw X
- raw Y
- raw Z

For each candidate:

1. Integrate gyro rate into a lean series.
2. Sample that lean series at GPS points.
3. Compute Pearson correlation against GPS lean.
4. Keep the candidate with the highest correlation.

On the reference `jinoop/sess_008.csv` session, the selected axis was `raw_z`, with approximately `0.876` correlation to GPS lean.

This is the most important caveat in the algorithm: GPS is used to choose the IMU axis/sign. After selection, the lean curve is produced by gyro integration, but the axis choice is GPS-assisted.

## Integration and Drift Correction

The estimator initializes lean from accelerometer tilt projected through the profile rotation matrix:

```text
accel_lean = atan2(-lateral_accel_component, max(0.15, up_accel_component))
```

Initial lean is clamped to +/-45 degrees.

Each IMU sample then integrates gyro roll rate:

```text
lean = lean + roll_rate_dps * dt
```

Where:

- `dt` is clamped between 0.005 s and 0.08 s
- `roll_rate_dps` is the selected gyro-axis projection after scale repair and bias subtraction
- final lean is clamped to +/-60 degrees

Accelerometer correction is deliberately gated because accel tilt is unreliable during dynamic riding.

Strong correction gain, `0.045`, is used only when:

- accelerometer magnitude error is below 0.16 g
- up component is above 0.65 g
- longitudinal acceleration is below 0.35 g
- absolute roll rate is below 90 deg/s
- total gyro activity is below 450 deg/s

Weak correction gain, `0.010`, is used only when:

- accelerometer magnitude error is below 0.24 g
- up component is above 0.45 g
- absolute roll rate is below 140 deg/s

Otherwise no accelerometer correction is applied.

The correction uses angle delta, not direct replacement:

```text
lean = lean + correction_gain * angle_delta(accel_lean, lean)
```

This lets the accelerometer slowly control drift during stable periods without dominating cornering dynamics.

## Default UI Settings

When `Calibrated V2` is selected in `imu-replay`, the UI sets:

```text
minSpeed = 0
smoothingMs = 100
leanRateLimit = 90
upMinG = 0.65
leanGain = 1
upFloorG = 0.15
accMagTol = 0.16
```

All optional filters/masks are off by default:

- Hampel filter
- moving average filter
- low-speed mask
- accel-magnitude mask
- pitch mask
- longitudinal-accel mask
- weak-turn-evidence mask
- lateral-vibration mask
- vertical-vibration mask
- hold-masked-lean

The goal is to show the estimator output directly, without extra UI filtering hiding algorithm behavior.

## Validation Result

Reference session:

```text
/Users/mj/Desktop/Trackdays/may3 Cra/jinoop/sess_008.csv
```

Observed replay result:

- GPS frames: 3342
- selected axis: `raw_z`
- axis correlation versus GPS lean: approximately `0.876`
- gyro repair scale: `0.0625`
- detected IMU rate: approximately `50 Hz`
- attitude/GPS median absolute difference: approximately `3.0 deg`
- attitude/GPS mean absolute difference: approximately `5.8 deg`

This was the first IMU-based result that matched the GPS lean curve shape closely enough to use for algorithm development.

## What This Algorithm Is Not

calibratedV2 is not yet a production IMU-only lean estimator.

Reasons:

- It uses GPS lean to choose gyro axis/sign.
- It includes heuristic gyro scale repair for a suspected firmware/config issue.
- It depends on field logs whose sample rates did not consistently match the intended firmware contract.
- It validates shape against GPS, not against a ground-truth lean sensor.

Correct product interpretation:

- Good for replay lab comparison.
- Good for discovering the correct IMU signal path.
- Good for identifying firmware/data-quality problems.
- Not yet sufficient for product claims of independent IMU lean accuracy.

## Production Path

To turn this into a production-grade estimator:

1. Fix firmware/logging so IMU and GPS rates match the intended contract.
2. Fix BMI323 gyro range/scale at the firmware source.
3. Ensure mount profile metadata reliably maps device axes to bike axes.
4. Remove GPS-assisted axis/sign selection.
5. Keep GPS lean only as an external validation/comparison signal.
6. Validate against more sessions and, eventually, a true lean-angle reference.
