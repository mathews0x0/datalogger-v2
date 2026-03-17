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
