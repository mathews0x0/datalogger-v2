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
