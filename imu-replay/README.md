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
cd imu-replay
python3 -m http.server 8090
```

Then open `http://localhost:8090`.

## Algorithm Layer

`processor.js` owns the middle layer between raw CSV rows and replay-ready frames.

Current structure:

- `processors.calibratedV1`
- `processors.calibratedStrictV1`

Each processor receives parsed session data plus a config object and returns:

- `frames`
- `stats`
- `algorithm`
- `config`

That is the file to edit when testing new lean/brake/accel logic.
