# RaceSense ESP32-P4 Production Gap Analysis

Use this document as the implementation and release checklist for the P4 port.

Status markers:

- `[ ]` Not complete
- `[-]` Partially complete or requires verification
- `[x]` Complete and verified

Current conclusion: the P4 image is still not production-ready. The P4 build
selects the real BMI323 driver on the dedicated I²C1 bus. The supplied BMI323,
Neo-M8N GPS, battery ADC, SD card, ST7701 display, and GT911 touch controller
have now passed live bench validation together. GPS obtains a clean satellite
lock, both accelerometer and gyro channels respond correctly in the IMU view,
touch calibration is accurate, and SD capacity/read/write operation is proven.
SD uses a verified 1-bit/20 MHz fallback because 4-bit SSR reads fail on the
current board/card path. The image still selects `network_stub.c`.

## 0. Release-blocking summary

- [x] Add a BMI323 four-pin module to the P4 expansion wiring; supplied production wiring uses GPIO21/22.
- [ ] Bring up ESP32-C6 Wi-Fi through esp-hosted/SDIO.
- [ ] Resolve ESP-hosted versus SDMMC resource/pin conflicts.
- [-] Connect the sensor queue to the storage queue; the sensor-owned queue
  and storage drain barrier are implemented, but live-session validation remains.
- [x] Freeze and verify the supplied GPS, BMI323, battery-monitor, and SD pin map in firmware; SD 1-bit/20 MHz is the accepted working baseline.
- [ ] Wire the application state machine to real track, calibration, feedback, storage, and network operations.
- [x] Correct the firmware/backend upload endpoint contract in the dormant client; live P4 transport validation remains open.
- [ ] Make generated CSV markers parse correctly on the server.
- [ ] Add hardware-in-the-loop, fault-injection, and long-duration testing.

## 1. Hardware and board-support package

### 1.1 IMU hardware

- [x] Production P4 includes a BMI323 four-pin module, per supplied wiring.
- [x] Document BMI323 power and four-pin wiring: 3.3 V/GND, SDA=`GPIO21`, SCL=`GPIO22`.
- [x] Define a separate BMI323 I²C bus; do not share the display touch bus.
- [x] Production mapping: BMI323 I²C1 SDA=`GPIO21`, SCL=`GPIO22`.
- [ ] Add/verify external 3.3 V I²C pull-ups and bus capacitance on the sensor wiring.
- [x] Four-pin BMI323 module has no exposed interrupt; use timer-driven polling for bring-up and production.
- [ ] Verify that polling/FIFO servicing at 100 Hz does not miss samples under display, SD, and Wi-Fi load.
- [ ] Do not allocate GPIO34 to BMI323 unless another future hardware function requires it.
- [x] Replace the P4 BMI323 stub with the real driver; clean P4 build verified.
- [x] Verify chip ID and error register on real hardware; chip ID `0x43` initializes cleanly.
- [-] Verify accelerometer range and sensitivity (`8192 LSB/g`); configured ±4 g values and live lean response pass, precision fixture validation remains.
- [-] Verify gyro range and sensitivity (`16.4 LSB/dps`); configured ±2000 dps values and live lean response pass, precision rate-table validation remains.
- [ ] Verify FIFO configuration and sensor timestamp behavior.

### 1.2 I²C bus separation

- [x] Keep GT911 on the board's existing I²C0 bus (`GPIO7/8`).
- [x] Move BMI323 to a separate I²C controller/bus (`GPIO21/22`).
- [x] Add the BMI323 device to the separate bus rather than calling bus creation twice for one bus.
- [x] Test GT911 and BMI323 simultaneously with independent bus traffic; calibrated touch and live accel/gyro diagnostics operate together.
- [ ] Test bus recovery after a stuck device or cable disconnect.
- [ ] Validate pull-ups and bus speed on the assembled board.

### 1.3 GPS hardware

- [x] Freeze the supplied production GPS UART mapping: GPIO3/TX → GPS RX and GPIO4/RX ← GPS TX.
- [x] Remove the disagreement between `bsp.h` and `gps.h`; both now use GPIO3/4.
- [x] Treat the board's explicitly labeled RX/TX debug port as the ESP32-C6 USB/UART path, not P4 GPIO3/4.
- [x] Production mapping: MCU `UART1_TX=GPIO3` → GPS RX; MCU `UART1_RX=GPIO4` ← GPS TX.
- [x] GPS wiring is defined for the P4 GPIO3/GPIO4 expansion pins, not the C6 RX/TX debug port.
- [ ] Reserve a GPS 1PPS input for precise time alignment; candidate=`GPIO32`.
- [ ] Define GPS module power, ground, reset/enable, backup supply, antenna connector, and antenna current.
- [ ] Verify 3.3 V UART levels, cable length, ESD protection, and connector keying.
- [x] Verify UART TX/RX routing with a real module.
- [x] Verify module boot baud and configured baud; retained 38400-baud startup is handled.
- [x] Verify UBX CFG-PRT command acceptance.
- [x] Verify 10 Hz measurement configuration; runtime diagnostics measure approximately 10 Hz.
- [-] Verify antenna, cold-start, warm-start, and weak-signal behavior; clean satellite lock is confirmed, controlled acquisition and weak-signal tests remain.

### 1.4 Display and touch

- [-] Verify ST7701 MIPI-DSI initialization on production panel batches; the supplied panel passes, batch coverage remains.
- [x] Verify 800×480 landscape orientation.
- [-] Verify RGB565 color order and outdoor contrast; rendering/color pass on the bench, outdoor contrast remains.
- [ ] Verify frame rate and tearing over a 60-minute soak.
- [-] Verify GT911 detection at both supported addresses; the fitted controller/address passes, alternate-address coverage remains.
- [x] Verify touch coordinates across all corners and edges.
- [x] Verify touch calibration persistence across reboot.
- [ ] Verify touch calibration recovery if the calibration file is corrupt.
- [ ] Implement and test brightness control through the backlight PWM.
- [ ] Add display failure reporting instead of silently continuing.

### 1.5 SD card and storage hardware

- [x] SD card uses P4 SDMMC slot 0, GPIO39–44, LDO_VO4 I/O power, and the active-low GPIO45 card switch; mount, capacity, create/write/readback/remove, and runtime persistence pass in 1-bit/20 MHz fallback mode.
- [ ] Test multiple SD card vendors and capacities.
- [-] Test FAT32 formatting and long filenames; FAT mount and LFN configuration pass, explicit multi-name test coverage remains.
- [-] Test high-volume sequential writes; verified 4 MiB benchmark passes at 0.65 MiB/s write and 0.73 MiB/s read, long-duration volume testing remains.
- [ ] Test SD card removal during idle.
- [ ] Test SD card removal during logging.
- [ ] Test SD card reinsertion and remount behavior.
- [ ] Test brownout or reset while writing.
- [x] Guard optional SD power GPIO operations against `GPIO_NUM_NC` / `-1`.

### 1.6 RGB LED output

- [ ] Confirm whether the output is one-wire addressable RGB (WS2812/SK6812) or three discrete PWM channels.
- [ ] For one-wire addressable RGB, use one dedicated data GPIO; recommended candidate=`GPIO28`.
- [ ] Avoid GPIO34–GPIO38 for LED/PPS signals because they are ESP32-P4 strapping pins.
- [ ] Reserve a 3.3 V-compatible level path, common ground, series data resistor, bulk capacitor, and current budget.
- [ ] Define LED power switching or brightness/current limits so the LED cannot cause brownouts during Wi-Fi or SD writes.
- [ ] Test signal integrity at the final cable length and maximum LED count.
- [ ] Test LED behavior during boot, reset, watchdog recovery, low battery, and SD/GPS/IMU faults.

### 1.7 Battery, charger, and power-path hardware

- [ ] Confirm the installed board revision and trace the battery connector's `BAT` net with a multimeter.
- [ ] Treat the stock ETA6098 charger as a 1-cell Li-ion/LiPo charger with a fixed approximately 4.2 V termination; do not claim 2S support.
- [ ] Verify that the battery pack includes protection/BMS, correct polarity, and a compatible connector.
- [x] Official schematic shows the battery divider: `BAT` → `R12=200 kΩ` → `BAT_ADC` → `R15=100 kΩ` → `GND`.
- [x] Official schematic connects `BAT_ADC` to ESP32-P4 `GPIO20`.
- [x] Change firmware from the stale `GPIO5` definition to `GPIO20 / ADC1_CHANNEL_4`.
- [x] Change the battery-divider scale from `2.1` to `3.0`.
- [ ] Verify the GPIO20 route and resistor values on the assembled board revision with continuity/resistance checks.
- [ ] Calibrate battery voltage against a DMM at empty, nominal, charging, and full conditions.
- [ ] Verify ADC input protection, RC filtering, leakage, and maximum battery voltage.
- [ ] Determine whether charger `STAT` is routed to a P4 GPIO. ETA6098 `STAT` is active-low/open-drain while charging and high-impedance when charge completes.
- [ ] If `STAT` is not routed, wire it through a pull-up to a spare GPIO; use it for charge-state indication rather than inferring charge from voltage slope.
- [ ] Distinguish `charging`, `full/not charging`, `USB absent`, `battery absent`, and `charger fault` in the hardware/firmware contract.
- [ ] Decide whether USB/VBUS-present detection is required in addition to `STAT`.
- [ ] Test charging while the device is running, high backlight, Wi-Fi upload, SD logging, unplug/replug, full battery, low battery, and battery removal.
- [ ] Test brownout thresholds and controlled shutdown under the worst-case display/LED/Wi-Fi load.

### 1.8 Other hardware items not yet frozen

- [ ] Freeze the power-on/reset/boot-button behavior and document which GPIOs are reserved by the Waveshare board.
- [ ] Freeze USB programming/debug connector and factory-test access.
- [ ] Verify C6 Wi-Fi module power, SDIO/esp-hosted wiring, antenna placement, and RF clearance in the enclosure.
- [ ] Define test points for 5 V/VBUS, battery, 3.3 V, ground, `BAT_ADC`, GPS TX/RX/PPS, BMI323 SDA/SCL/INT, and LED data.
- [ ] Define connector pinout, cable strain relief, ESD, reverse-polarity, and accidental-short protection for every external module.
- [ ] Define thermal limits for the charger, regulator, backlight boost, SD card, and enclosure during charging plus logging plus upload.
- [ ] Decide whether RTC/backup time, buzzer/audio, card-detect, and user buttons are product requirements or explicitly out of scope.

## 2. Build and configuration

- [ ] Add a clean P4 build to CI.
- [x] Add a production hardware configuration that does not select `bmi323_stub.c`.
- [ ] Add a production hardware configuration that does not select `network_stub.c`.
- [ ] Build with warnings treated as errors.
- [ ] Build from a clean directory, not only an existing incremental build directory.
- [ ] Verify all P4-only source files compile in the production configuration.
- [x] Verify the real BMI323 driver compiles for P4 on I²C1.
- [x] Verify the dormant network implementation compiles for P4 toolchain flags; the image still selects `network_stub.c`.
- [x] Add reproducible firmware release metadata; the shared `server/VERSION` number is embedded as the Mark identity and advances with every commit.
- [-] Add manufacturing/release identifiers; Mark 199 is present, while per-unit manufacturing identity remains open.
- [ ] Freeze ESP-IDF and managed-component versions.
- [ ] Document the exact toolchain and build command.

## 3. Sensor acquisition pipeline

### 3.1 Queue architecture

- [-] Remove the duplicate sensor/storage queue ownership; one sensor-owned queue
  is now consumed by storage.
- [-] Choose one queue owner and one producer/consumer contract; the sensor
  component owns production and storage consumes through `sensors_wait_dequeue_row()`.
- [-] Make storage drain the sensor-owned queue; the implementation builds, but
  live-session row delivery remains to be verified on hardware.
- [ ] Verify rows are actually written during a live session.
- [-] Track queue depth, maximum depth, and dropped rows; runtime counters and
  health logging are implemented, while measured hardware results remain open.
- [-] Define backpressure behavior when storage cannot keep up; non-blocking
  enqueue with explicit drop counters is implemented, but performance tuning remains.
- [-] Ensure stopping logging drains all queued rows before closing the file; a
  producer-quiescence and flush acknowledgement barrier is implemented and awaits hardware validation.

### 3.2 IMU acquisition

- [ ] Use the BMI323 FIFO for production acquisition where appropriate.
- [ ] Preserve hardware sensor timestamps.
- [ ] Map sensor time to host monotonic time.
- [ ] Detect missed, duplicated, or stale samples.
- [ ] Recover from I²C errors without rebooting the entire device.
- [ ] Reinitialize the IMU after a persistent communication failure.
- [ ] Verify actual 100 Hz rate on hardware.
- [ ] Verify jitter and maximum sample gap.

### 3.3 GPS acquisition

- [ ] Parse valid and invalid RMC fixes correctly.
- [ ] Parse GGA altitude and satellite count correctly.
- [ ] Only emit GPS rows for fresh valid fixes.
- [ ] Preserve the last fix separately from fix freshness.
- [ ] Add GPS stale/fix timeout logic.
- [ ] Convert GPS date/time to epoch time.
- [x] Verify actual 10 Hz fix rate where supported by the receiver.
- [x] Track parser health counters in runtime diagnostics.

### 3.4 Thread safety

- [ ] Replace unsafe multiword lock-free struct copies with a mutex or sequence-lock design.
- [ ] Make sensor state visibility explicit across cores.
- [ ] Verify no LVGL calls occur from the sensor task.
- [ ] Verify no filesystem calls occur from the sensor task.
- [ ] Verify sensor task timing under display and network load.
- [ ] Fix task/timer cleanup so `sensors_task_stop()` is restart-safe.

## 4. Logging and CSV compatibility

### 4.1 Session lifecycle

- [-] Check and handle `storage_session_start()` failure; the UI now refuses
  to enter logging when session creation fails, while a dedicated error screen remains open.
- [-] Refuse logging when no usable storage exists; session open/write/flush
  failures now block logging and surface the storage fault screen.
- [ ] Define whether logging is allowed without GPS.
- [ ] Define whether logging is allowed without IMU.
- [ ] Use session-relative elapsed time.
- [-] Close sessions only after producer shutdown and queue drain; the
  quiescence/drain barrier is implemented and awaits hardware validation.
- [ ] Add incomplete-session recovery after reset.
- [-] Add explicit storage-write fault state; the fault is latched in storage,
  propagated to the app state machine, and cleared only after acknowledgement.

### 4.2 CSV schema

- [ ] Freeze the final CSV header and document it as a versioned contract.
- [ ] Decide whether P4 must emit `gps_epoch` and `imu_sensor_us` for S3 parity.
- [ ] Emit valid `I` rows at the intended rate.
- [ ] Emit valid `G` rows only for fresh GPS fixes.
- [ ] Ensure all rows have the expected number of columns.
- [ ] Make marker rows compatible with `server/core/ingestion/csv_loader.py`.
- [ ] Verify `LOG_OPEN` is parsed.
- [ ] Verify `LOG_STOP` is parsed.
- [ ] Verify `IMU_PROFILE` is parsed as JSON.
- [ ] Verify `IMU_VALIDATION` is parsed as JSON.
- [ ] Verify `CHECKPOINT` rows are parsed or intentionally ignored.
- [ ] Escape marker payloads safely.
- [ ] Check all `fwrite`, `fflush`, `fclose`, `rename`, and copy results.
- [ ] Replace approximate byte counters with measured byte counts.
- [ ] Add file integrity/length validation before upload.

### 4.3 Storage capacity and safety

- [ ] Add flash usage reporting, not only SD usage reporting.
- [ ] Enforce critical and hard-stop thresholds on both media.
- [-] Display storage state to the rider with a dedicated fault screen; visual
  and fault-injection validation remain.
- [-] Stop logging cleanly at the hard limit by disabling producers, draining
  queued rows, and closing the file; hardware validation remains.
- [ ] Avoid automatic formatting of internal flash in production.
- [ ] Use temporary files plus atomic rename for configuration and copies.
- [ ] Verify source and destination content, not only file size.
- [ ] Feed the watchdog during long flash-to-SD copies.
- [ ] Test filename collision and archive behavior.
- [ ] Increase or reassess the 1 MB internal storage partition.

## 5. IMU calibration and orientation

- [ ] Initialize the calibration subsystem at boot.
- [ ] Load the selected profile at boot.
- [ ] Apply the saved rotation matrix to telemetry calculations.
- [ ] Apply gyro bias correction.
- [ ] Implement all calibration capture stages.
- [ ] Collect real samples while the user is in each stage.
- [ ] Display live sample count and stability status.
- [ ] Reject stages with too few samples.
- [ ] Reject unstable or degenerate captures.
- [ ] Compute profile only after all required stages pass.
- [ ] Save profiles atomically.
- [ ] Validate profile JSON before loading.
- [ ] Support profile version migration.
- [ ] Implement cancel/reset semantics.
- [ ] Emit the active profile as a session marker.
- [ ] Emit an IMU validation result marker after the logging validation window.
- [ ] Test calibration with known artificial orientations.

## 6. Track, lap, and sector timing

- [-] Initialize `track_engine` at boot; local initialization and cached metadata loading are wired, while live metadata provisioning remains open.
- [-] Fetch active track metadata from the backend; the dormant client now uses the device route, preserves the normalized display layout, and atomically caches validated payloads. The Home preview and full-screen Track/Info viewer consume the cache, while P4 network provisioning remains deferred.
- [-] Validate track JSON before activation; host validation rejects malformed gates/TBL data, with live-device activation still open.
- [x] Support track name and TBL data from the cached track payload.
- [-] Call `track_engine_update_gps()` for fresh GPS fixes; the sensor-to-engine path is wired, with hardware GPS validation still open.
- [x] Register a track event callback.
- [x] Route track-found events to the application/UI path.
- [x] Route sector events to the feedback subsystem.
- [x] Route lap events to the live timing UI.
- [ ] Implement pit-area behavior or remove the unused pit fields.
- [x] Add gate-crossing debounce/hysteresis.
- [x] Add optional direction/crossing validation to prevent false triggers.
- [x] Handle GPS jitter near gates.
- [x] Test first track identification with the host replay harness.
- [x] Test sector transitions with synthetic GPS points.
- [x] Test lap completion and reset.
- [x] Test missing TBL behavior through neutral classification.
- [-] Test missing track metadata; no-track startup is handled, while a full device metadata-provisioning test remains open.
- [ ] Replay recorded GPS traces through the engine.

## 7. Rider feedback and UI

### 7.1 Live logging screen

- [x] Replace hardcoded track name with active-track data.
- [x] Replace hardcoded lap count with track-engine data.
- [x] Display actual lap time.
- [x] Display actual delta versus TBL.
- [ ] Display actual GPS status and freshness.
- [ ] Display actual storage health.
- [ ] Display calibrated lean estimate.
- [ ] Use gyro/fusion-based lean estimation rather than accelerometer-only tilt.
- [ ] Add the five-second IMU validation screen.
- [-] Add the sector crossing overlay; rendering and expiry are implemented, with hardware visual validation still open.
- [ ] Implement the specified hold-to-stop interaction.
- [ ] Add error screens and recovery actions.

### 7.2 Home and settings

- [ ] Periodically refresh battery state.
- [x] Display real storage free space rather than `18.5 GB FREE`; nominal 8 GB card reports 7.49 GiB total and approximately 7.42 GiB free.
- [ ] Display the real active mount profile.
- [ ] Implement auto-log setting and persistence.
- [ ] Implement track selection.
- [ ] Implement Wi-Fi setup action.
- [ ] Implement brightness/display settings.
- [x] Implement device diagnostics; Hardware Debug exposes live GPS and BMI323 status/data.
- [-] Implement Mark release information; Mark 199 is logged at boot and embedded in the binary, while a rider-facing Settings display remains open.
- [ ] Implement safe navigation while background tasks are active.
- [x] Verify repeated screen transitions do not leak LVGL objects during current bench navigation testing.
- [ ] Verify touch targets in outdoor conditions.

### 7.3 Feedback subsystem

- [x] Initialize `feedback` at boot.
- [x] Call `feedback_tick()` periodically.
- [-] Implement actual sector/lap overlay rendering; sector flash rendering is implemented, while lap completion currently updates the live timing card rather than opening a separate full-screen lap overlay.
- [x] Implement overlay expiry and return to logging.
- [ ] Apply brightness to the backlight PWM.
- [ ] Define behavior for overlapping sector/lap events.
- [ ] Test overlays at speed and under continuous UI updates.

## 8. Wi-Fi, sync, and captive portal

### 8.1 ESP32-C6 transport

- [x] Enable esp-hosted/remote Wi-Fi configuration.
- [x] Validate P4-to-C6 reset and handshake.
- [x] Validate SDIO pins and host ownership.
- [x] Validate coexistence with the SD card.
- [-] Add transport failure recovery; restart-on-failure is configured, but fault injection is still open.
- [ ] Add transport watchdog and timeout handling.

Live P4 evidence (2026-08-04): SDIO transport reached `TRANSPORT_TX_ACTIVE`,
identified the slave as `esp32c6`, and a credential-free hosted Wi-Fi scan
returned 9 access points. The application then remained in `HOME_IDLE` with
stable health, SD, GPS, and IMU telemetry. The C6 still reports coprocessor
version `0.0.0` against host `2.12.0`; association, DHCP, DNS/HTTPS, and
server heartbeat remain to be validated with a real provisioned network.

### 8.2 Backend contract

- [x] Change heartbeat to the actual server route: `POST /api/device/ping`.
- [x] Send available heartbeat telemetry fields expected by the server, with explicit telemetry injection for battery/flash values.
- [x] Change active-track fetch to `GET /api/device/active_track`.
- [x] Confirm `api_url` semantics: server-root URLs and legacy `/api/upload` values normalize to the same endpoint base.
- [x] Validate `/api/upload/status` response handling.
- [x] Validate `/api/upload/batch` request headers and server-side sequential offsets.
- [x] Validate `/api/upload/complete` response/body contract.
- [x] Add URL encoding for filenames.
- [x] Validate resume offsets against local file size.
- [-] Preserve resumability after reset or Wi-Fi loss; client/server logic is hardened, but live transport testing remains open.
- [ ] Add cancellation tokens and close the active connection on cancel.
- [ ] Prevent completed background tasks from mutating a different UI screen.
- [ ] Add real upload speed and ETA reporting.
- [ ] Test authentication failure and revoked tokens.
- [ ] Test TLS certificate and SNTP failure paths.

### 8.3 Provisioning portal

- [x] Implement the P4 captive portal using the active network backend.
- [x] Validate request `Content-Length` and read complete POST bodies.
- [x] Handle fragmented TCP requests.
- [x] Bound all form-field lengths.
- [x] Validate SSID, password, token, and API URL.
- [x] Save configuration atomically.
- [x] Never log passwords or full tokens.
- [ ] Test Android, Apple, and Windows captive-detection probes.
- [ ] Test portal timeout and explicit exit.
- [ ] Stop DNS and HTTP tasks cleanly.
- [ ] Define whether the open AP is acceptable for production.

## 9. Power, watchdog, and recovery

- [ ] Define the P4 power-hold and shutdown hardware behavior.
- [ ] Implement controlled shutdown if supported by the P4 carrier.
- [ ] Flush and close the active session before power release/reset.
- [ ] Add brownout handling.
- [ ] Add watchdog monitoring for sensor, storage, UI, and network tasks.
- [ ] Add task stack high-water monitoring.
- [ ] Add heap and PSRAM low-water monitoring.
- [ ] Add reset-cause tracking.
- [ ] Add persistent crash/boot diagnostics.
- [ ] Add automatic recovery for stuck SD, GPS, IMU, and Wi-Fi states.
- [ ] Test watchdog recovery during blocked filesystem/network operations.

## 10. OTA and security

- [ ] Add OTA partition layout (`ota_0`, `ota_1`, and `otadata`).
- [ ] Implement firmware update transport for the P4.
- [ ] Implement image version and compatibility checks.
- [ ] Implement rollback after failed boot.
- [ ] Add signed firmware verification.
- [ ] Evaluate secure boot.
- [ ] Evaluate flash encryption.
- [ ] Protect device credentials and tokens at rest.
- [ ] Prevent credentials from appearing in logs or rendered HTML.
- [ ] Add factory reset with deliberate user confirmation.
- [ ] Add anti-downgrade policy.

## 11. Automated test checklist

### 11.1 Driver and parser tests

- [ ] NMEA checksum validation.
- [ ] GPRMC parsing.
- [ ] GPGGA parsing.
- [ ] Invalid and truncated NMEA lines.
- [ ] Southern and western hemisphere coordinates.
- [ ] UBX checksum generation.
- [ ] UBX baud/rate command generation.
- [ ] BMI323 chip-ID failure.
- [ ] BMI323 configuration failure.
- [ ] BMI323 FIFO parsing.
- [ ] BMI323 timestamp rollover.
- [ ] Duplicate-frame filtering.
- [ ] Battery curve and filtering.
- [ ] Charging-state detection.

### 11.2 Algorithm tests

- [ ] Track identification.
- [ ] Sector ordering.
- [ ] Lap completion.
- [ ] TBL delta classification.
- [ ] Gate jitter and false positives.
- [ ] Missing/invalid track JSON.
- [ ] Calibration valid profile.
- [ ] Calibration empty-stage rejection.
- [ ] Calibration degenerate-vector rejection.
- [ ] Calibration save/load/upsert.
- [ ] Calibration schema migration.

### 11.3 Storage tests

- [ ] CSV header and row schema.
- [ ] Marker round-trip through the server CSV loader.
- [ ] Queue overflow and drop accounting.
- [ ] Stop/drain ordering.
- [ ] Storage write failure.
- [ ] Filesystem full behavior.
- [ ] Flash-to-SD copy verification.
- [ ] Copy interruption and retry.
- [ ] Filename collision handling.
- [ ] Incomplete-session recovery.

### 11.4 Network tests

- [ ] Endpoint URL construction against the Flask server.
- [ ] Wi-Fi connect success.
- [ ] Wrong credentials.
- [ ] No access point.
- [ ] No internet route.
- [ ] SNTP timeout.
- [ ] TLS certificate failure.
- [ ] Heartbeat success/failure.
- [ ] Active-track fetch.
- [ ] Upload success.
- [ ] Upload resume.
- [ ] Upload retry.
- [ ] Upload cancellation.
- [ ] Duplicate filename.
- [ ] Mid-batch reset.
- [ ] Server 4xx/5xx responses.
- [ ] Revoked token.

## 12. Hardware-in-the-loop and soak testing

- [ ] Cold boot with no SD card.
- [ ] Cold boot with no IMU.
- [ ] Cold boot with no GPS fix.
- [ ] Cold boot with no Wi-Fi configuration.
- [ ] Start/stop logging repeatedly.
- [ ] Verify measured 100 Hz IMU rate.
- [x] Verify measured 10 Hz GPS rate and obtain a clean satellite lock.
- [ ] Verify server CSV ingestion.
- [ ] Reboot during logging.
- [ ] Brownout during logging.
- [ ] Remove SD during logging.
- [ ] Lose Wi-Fi during upload.
- [ ] Recover from watchdog reset.
- [ ] Run 24-hour logging soak.
- [ ] Run 72-hour logging soak.
- [ ] Run repeated boot/reset cycles.
- [ ] Run memory-fragmentation test.
- [ ] Run high-temperature test.
- [ ] Run low-battery test.
- [ ] Run full-screen UI and touch stress test.

## 13. Release gates

- [ ] Production P4 hardware BOM and pinout are frozen.
- [x] Real IMU is operational; live accelerometer and gyro lean response is confirmed.
- [ ] Real Wi-Fi transport is operational.
- [ ] Sensor-to-storage path is proven end-to-end.
- [ ] CSV round-trip is proven through the production server.
- [ ] Track timing is proven with replayed and live GPS traces.
- [ ] Calibration is proven with real sensor captures.
- [ ] Sync, cancellation, retry, and resume are proven.
- [ ] Shutdown, watchdog, brownout, and recovery behavior are proven.
- [ ] OTA and rollback are proven.
- [ ] Security review is complete.
- [ ] Hardware-in-the-loop and soak tests pass.
- [-] Release binary carries the shared Mark identity; full clean-build reproducibility and release qualification remain open.
- [ ] Manufacturing test procedure is documented.

## Key source references

- [Application state machine](/Users/mj/Documents/datalogger-v2/firmware/main/main.c)
- [Sensor pipeline](/Users/mj/Documents/datalogger-v2/firmware/components/sensors/sensors.c)
- [Storage engine](/Users/mj/Documents/datalogger-v2/firmware/components/storage/storage.c)
- [Network build selection](/Users/mj/Documents/datalogger-v2/firmware/components/network/CMakeLists.txt)
- [Network implementation](/Users/mj/Documents/datalogger-v2/firmware/components/network/network.c)
- [UI implementation](/Users/mj/Documents/datalogger-v2/firmware/components/ui)
- [Track engine](/Users/mj/Documents/datalogger-v2/firmware/components/track_engine/track_engine.c)
- [Backend upload routes](/Users/mj/Documents/datalogger-v2/server/api/blueprints/core.py)
- [Backend device routes](/Users/mj/Documents/datalogger-v2/server/api/blueprints/devices.py)
- [Backend CSV loader](/Users/mj/Documents/datalogger-v2/server/core/ingestion/csv_loader.py)
