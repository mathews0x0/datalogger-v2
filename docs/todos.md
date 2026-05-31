# 🚀 RaceSense Todos & Optimizations

This document tracks high-priority technical tasks and architectural improvements for the platform.

## ⚡ Performance & Scalability
- [ ] **Batch DB Commits for Chunked Uploads**
    - **Current Issue**: Frequent `db.session.commit()` calls from `/api/upload/chunk` still create avoidable database and request-path overhead during active sync, especially when device progress updates are noisy.
    - **Proposed Fix**: Only commit the `DeviceToken` state every 10-20 chunks, or exclusively during the `upload_complete` call.

## 🏗️ Architecture & Database
- [ ] **Remove Stale SQLite / Legacy-Path Assumptions**
    - PostgreSQL is already the active database path, but some docs, comments, and scripts still imply older SQLite-era behavior or directory layouts. Clean up stale assumptions so operational guidance matches the current stack.
- [ ] **Asynchronous File Assembly**
    - Move the chunk concatenation logic from the request handler to the background worker to prevent Gunicorn worker starvation.

- [ ] **Unify Analysis Package Imports**
    - The active analysis code is under `server/core/`, but several modules still import from an old `src.analysis...` namespace that is not present in this repo. Consolidate imports and runtime entrypoints before expanding analysis-dependent tooling.

## 📱 User Experience
- [ ] **Improved Progress Visualization**
    - Ensure the UI handles batched progress updates gracefully without appearing "stuck" between commits.

## 🔋 Power Control
- [ ] **Validate and Tune Single-Switch Shutdown on RS-Core V4.2**
    - **Current State**: RS-Core V4.2 now uses a single physical power button with `IO41` as the hold output and `IO8` as the protected sense input for the same switch. Firmware support for long-press shutdown has been wired in.
    - **Next Step**: Validate real hardware thresholds, debounce, and hold timing across Home, Sync, WiFi-search, and Logging on battery and USB power.
    - **Target Behavior**: One short press turns the device on, firmware claims the latch immediately, and one long press shows `SHUTDOWN`, flushes storage safely, and releases `IO41` without false triggers.

## 🖥️ TFT Variant Support
- [ ] **Validate first-boot TFT preset selection and second-boot touch calibration on a freshly erased device**
    - **Current State**: Firmware now stores per-device TFT panel settings in `/data/metadata/display.json` and runs touch calibration only after a panel preset is selected and saved.
    - **Next Step**: Test the full erase -> preset selection -> reboot -> touch calibration -> reboot -> normal boot flow on both known TFT variants.
    - **Target Behavior**: New devices self-identify a usable panel preset with a single touch, calibrate on the following boot, and then boot normally without needing a custom firmware build.

## 🏁 Future Features
- [~] **Global Race Visualization (Multi-Rider / Race View)**
    - **Current State**: A first public `Race View` module now exists in Community and Trackday flows. It groups overlapping public sessions on the same canonical track and renders labeled rider dots on one shared replay timeline.
    - **Remaining Work**: Persist/export absolute per-row wall-clock time (`time_epoch`) so synchronized playback no longer depends on reconstructing epoch time from `start_time + row.time`.
    - **Next Product Layer**: Add stronger event semantics such as likely overtakes, richer moment cards, and deeper discovery if Race View proves to be a frequent destination.

## 🗺️ Canonical Track System
- [ ] **Persist Session-to-Package Alignment Server-Side**
    - **Current Issue**: Shared canonical layouts now render in lap detail, comparison, and playback, but the final small rotation/translation correction is still computed client-side from sampled GPS points.
    - **Proposed Fix**: Persist a per-session canonical correction artifact during analysis so all views use the same deterministic alignment and the browser does not need to estimate a corrective transform at render time.

- [ ] **Admin Tooling for Shared Track Lifecycle**
    - **Current Issue**: Shared master track upload and guarded delete exist, but there is no richer admin workflow for reviewing package quality, alignment confidence, or replacing an existing package version with explicit migration visibility.
    - **Proposed Fix**: Add package validation diagnostics, alignment confidence previews, and a first-class “replace package version” flow.
