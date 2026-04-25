# 🚀 RaceSense Todos & Optimizations

This document tracks high-priority technical tasks and architectural improvements for the platform.

## ⚡ Performance & Scalability
- [ ] **Batch DB Commits for Chunked Uploads**
    - **Current Issue**: Every 64KB chunk received via `/api/upload/chunk` triggers a `db.session.commit()` to update the sync progress. At 100Hz log speeds, this results in ~32 commits/second, causing severe SQLite write contention and "Database is locked" errors for other users/heartbeats.
    - **Proposed Fix**: Only commit the `DeviceToken` state every 10-20 chunks, or exclusively during the `upload_complete` call.

## 🏗️ Architecture & Database
- [ ] **PostgreSQL Migration**
    - Move away from SQLite to support native row-level local and concurrent writes.
- [ ] **Asynchronous File Assembly**
    - Move the chunk concatenation logic from the request handler to the background worker to prevent Gunicorn worker starvation.

## 📱 User Experience
- [ ] **Improved Progress Visualization**
    - Ensure the UI handles batched progress updates gracefully without appearing "stuck" between commits.

## 🔋 Power Control
- [ ] **Add Button Sense for Long-Press Soft Shutdown on RS-Core V4.2**
    - **Current State**: RS-Core V4.2 now supports soft-power latching in hardware, and the firmware already asserts `IO41` early in boot to sustain power after the momentary button is released.
    - **Next Step**: Add a sensed copy of the physical power button to a free GPIO/ADC input so the firmware can distinguish user press intent from `PWR_HOLD`.
    - **Target Behavior**: Detect a long press, flush and sync pending storage safely, then release the `IO41` power hold for a clean soft shutdown.

## 🖥️ TFT Variant Support
- [ ] **Validate first-boot TFT preset selection and second-boot touch calibration on a freshly erased device**
    - **Current State**: Firmware now stores per-device TFT panel settings in `/data/metadata/display.json` and runs touch calibration only after a panel preset is selected and saved.
    - **Next Step**: Test the full erase -> preset selection -> reboot -> touch calibration -> reboot -> normal boot flow on both known TFT variants.
    - **Target Behavior**: New devices self-identify a usable panel preset with a single touch, calibrate on the following boot, and then boot normally without needing a custom firmware build.

## 🏁 Future Features
- [ ] **Global Race Visualization (Multi-Rider)**
    - **Concept**: Calculate and render precise movement for all concurrent riders on a track using the synchronized absolute `gps_epoch` timestamps.
    - **Execution**: If users are running RaceSense simultaneously and share their sessions publicly, display a live/replay "Race View" where users are accurately shown chasing each other corner-by-corner.

## 🗺️ Canonical Track System
- [ ] **Persist Session-to-Package Alignment Server-Side**
    - **Current Issue**: Shared canonical layouts now render in lap detail, comparison, and playback, but the final small rotation/translation correction is still computed client-side from sampled GPS points.
    - **Proposed Fix**: Persist a per-session canonical correction artifact during analysis so all views use the same deterministic alignment and the browser does not need to estimate a corrective transform at render time.

- [ ] **Admin Tooling for Shared Track Lifecycle**
    - **Current Issue**: Shared master track upload and guarded delete exist, but there is no richer admin workflow for reviewing package quality, alignment confidence, or replacing an existing package version with explicit migration visibility.
    - **Proposed Fix**: Add package validation diagnostics, alignment confidence previews, and a first-class “replace package version” flow.
