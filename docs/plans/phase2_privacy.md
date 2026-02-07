# Phase 2: Data Isolation & Privacy Controls

**Status:** In Progress  
**Depends On:** Phase 1 (Complete)  
**Estimated Effort:** 1 week

---

## Objective

Give users control over what data is private vs public, and enable sharing sessions.

---

## Requirements

### 1. Session Visibility
- Default: **Private** (only owner can see)
- Toggle to make **Public** (visible to all users)
- Public sessions appear in global feeds/leaderboards

### 2. Share Session
- Generate a **public link** for any session
- Link format: `/shared/<unique_token>`
- Anyone with link can view (read-only), even without account
- Optional: Set expiry on shared links

### 3. Privacy Settings
- Global default: "Make new sessions private/public"
- Per-session override

### 4. Public Session Feed
- New view: "Community" or "Public Sessions"
- Shows recent public sessions from all users
- Filter by track

### 5. UI Changes
- Privacy toggle on session detail page
- "Share" button generates link
- "Community" nav tab

---

## Technical Approach

### Backend

1. **Database Changes:**
   - Add `is_public` boolean to sessions table (default: False)
   - Add `share_token` string to sessions table (nullable)
   - Add `share_expires_at` datetime (nullable)

2. **New Endpoints:**
   ```
   PUT  /api/sessions/<id>/privacy   - Toggle public/private
   POST /api/sessions/<id>/share     - Generate share link
   GET  /api/shared/<token>          - View shared session (no auth)
   GET  /api/public/sessions         - List all public sessions
   ```

3. **Query Changes:**
   - `/api/sessions` - Only user's sessions (existing)
   - `/api/public/sessions` - All public sessions

### Frontend

1. **Session Detail:**
   - Privacy toggle switch
   - "Share" button → modal with copyable link
   
2. **New Tab: Community**
   - Grid/list of public sessions
   - Track filter
   - Click to view (read-only)

3. **Shared View:**
   - `/shared/<token>` route
   - Read-only session viewer
   - "Sign up to track your own laps" CTA

---

## Milestones

| Milestone | Description | Est. Time |
|-----------|-------------|-----------|
| M1 | Database schema update (is_public, share_token) | 1 day |
| M2 | Privacy toggle endpoint + UI | 1 day |
| M3 | Share link generation + public view | 1 day |
| M4 | Community feed (public sessions) | 1 day |
| M5 | Testing + polish | 1 day |

---

## Success Criteria

1. ✅ User can toggle session privacy
2. ✅ User can generate shareable link
3. ✅ Anyone with link can view session (no login)
4. ✅ Community feed shows public sessions
5. ✅ Private sessions remain hidden from others

---
