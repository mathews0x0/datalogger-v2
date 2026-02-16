# Racesense Behaviour Specification

**Version:** 1.0.0  
**Date:** 2026-02-15  
**Source of Truth for:** Automated Browser Test Suite

## 1. Overview
Racesense is a high-performance motorcycle data logging system. This document defines the expected behavior of the Racesense Companion App (Web/Mobile) and its interaction with the ESP32-based logging hardware.

---

## 2. Authentication & User Profile
### 2.1 User Registration
- **Action:** User enters Name, Email, and Password in the Register form.
- **Expected Behaviour:**
    - On success: Show "Registered! Please login." toast, switch to Login form.
    - On failure (e.g., email already exists): Show specific error message in the modal.
    - Fields are validated: Email format, non-empty password.

### 2.2 User Login
- **Action:** User enters credentials in the Login form.
- **Expected Behaviour:**
    - On success: 
        - Close modal.
        - Show "Logged in successfully" toast.
        - Update Header: Show name, Tier badge, and Logout button.
        - Persistent session via HTTP-only cookie.
    - On failure: Show "Invalid email or password" error in modal.
- **Edge Case:** Empty credentials in DEV mode might bypass login (check `main.py`).

### 2.3 Profile Management
- **Location:** Settings Tab -> User Profile card.
- **Expected Behaviour:**
    - User can update Name, Bike Info, and Home Track.
    - Clicking "Update Profile" shows "Profile updated" toast.
    - Changes persist across page reloads.

---

## 3. Connectivity & Sync
### 3.1 Device Status Monitoring
- **Header Badges:**
    - **Connection Status:** 
        - `online` (green dot) when Nitro 5 backend is reachable.
        - `offline` (red dot) when disconnected.
    - **Storage Indicator:** Shows % of ESP32 flash used (visible only when device IP is known/reachable).
    - **Active Track:** Shows the name of the track currently identified by the device GPS.

### 3.2 Network Scanner (Settings)
- **Action:** Click "Scan" button in Device Connection card.
- **Expected Behaviour:**
    - Trigger multithreaded subnet scan (`/api/device/scan`).
    - Show spinner on button.
    - If device found: Update "Status" text to "Connected", show device IP, update localStorage.
    - If not found: Show "Disconnected" and toast "No device found".

### 3.3 Hybrid Sync Wizard (Mobile/Native)
- **Trigger:** "Sync with Device" button on Dashboard.
- **Workflow Steps:**
    1. **BLE Connection:** App requests BLE device with prefix `Racesense`. Show "Connecting..." overlay.
    2. **AP Start:** App sends `START_AP` via BLE. Device starts WiFi Access Point.
    3. **WiFi Join:** App programmatically joins device AP (e.g., `Datalogger-AP`).
    4. **Download:** App fetches manifest from `192.168.4.1`, downloads CSVs to local filesystem.
    5. **Clean up:** App sends `STOP_AP` via BLE.
- **Edge Cases:**
    - **BLE Timeout:** Show "Timed out waiting for AP" error after 30s.
    - **WiFi Failure:** Show "Failed to connect to network" error.
    - **Incomplete Download:** Log error but allow retry.

---

## 4. Track Management
### 4.1 Track List
- **Expected Behaviour:**
    - Displays all tracks learned or registered by the user.
    - Shows track map (SVG/PNG fallback), session count, and "Set Active" button.
- **Actions:**
    - **Set Active:** Pushes track geometry and sectors to the ESP32 (`/track/set`). Shows "Track set as active" toast.
    - **Rename:** Opens Modal. Input sanitizes name (replaces spaces with underscores). Updates all related session filenames.
    - **Delete:** Prompt for confirmation. Deletes track folder and associated session JSONs from disk/DB. Raw CSVs are NOT deleted.

### 4.2 Track Detail View
- **Expected Behaviour:**
    - Displays high-res SVG map.
    - Shows KPIs: Session count, Sector count, Theoretical Best Lap (TBL).
    - **Mark Pit Lane:** Grabs current GPS coordinates from connected device and saves as pit geofence for auto-pause logic.

---

## 5. Session Analysis
### 5.1 Process View (Ingestion)
- **Expected Behaviour:**
    - Lists raw CSV files in `output/learning/`.
    - **Process All:** Batch processes unprocessed files. Shows progress/success badges.
    - **Lock/Unlock:** Prevents accidental deletion of specific CSVs.
    - **Peek:** Shows raw CSV headers and first 100 lines.
    - **Visualize:** Draws simple SVG path of GPS coordinates without full processing.

### 5.2 Session Details (The "Drill-Down")
- **Layout:** Collapsible sections for hierarchy.
    - **Session Overview:** Grouped stats (Laps, Best, Duration).
    - **Lap Table:** List of all laps with sector times. Highlight "Session Best" in green.
    - **Visual Insights:** (Collapsible) Sector comparison and trend charts.
- **Actions:**
    - **Playback/Replay:** Opens full-screen telemetry dashboard.
    - **Add Note:** Opens Modal to add coaching annotations to specific Lap/Sector.
    - **Delete:** Permanent removal of processed JSON files.
    - **Share:** Generates unique UUID token for public URL (`/shared/<token>`).

### 5.3 Telemetry Replay (Modal)
- **Components:**
    - **Interactive Map:** Track path with dot moving in sync with timeline.
    - **Heatmaps:** Toggle between Speed, G-Force (Accel/Braking), and Line.
    - **Gauges:** Lean Angle, Speedometer, G-Force Vector.
    - **Controls:** Play/Pause, Seek Slider, Lap Selector.

---

## 6. Community & Social
### 6.1 Community Feed
- **Explore:** Displays recent sessions marked as "Public" by any user.
- **Following:** Chronological feed of public sessions from followed riders.
- **Leaderboards:** Top times for a specific track, filterable by Time Period (All, Month, Week).

### 6.2 User Profiles
- **Expected Behaviour:**
    - Shows rider's public stats (Total Laps, Tracks Visited).
    - Lists Personal Bests for each track.
    - **Follow/Unfollow:** Toggle social relationship.

---

## 7. Team Features (Pro/Team Tiers)
### 7.1 Team Dashboard
- **Owner/Coach View:**
    - List all members.
    - View private/public sessions of all team riders.
    - Add coaching annotations to rider sessions.
- **Invite Flow:** Generate unique invite link (`/teams/join/<token>`). 7-day expiry.

### 7.2 Trackday Aggregation
- **Group Sessions:** Manually tag multiple sessions (from same day/track) to a "Trackday" object.
- **Trackday TBL:** Calculate theoretical best lap across ALL sessions in the trackday.
- **Print Report:** Dedicated printable layout for Trackday summary (PDF friendly).

---

## 8. Admin Management
- **Access:** Only visible if `is_admin` is true in User model.
- **User List:** Searchable table of all registered users.
- **Tier Control:** Admin can manually set user tier (Free, Pro, Team).
- **Session Limits:** Free users restricted to 5 processed sessions (enforced in `/api/process`).

---

## 9. Error Handling & Edge Cases
- **Connection Timeout:** All API calls show "Connection error" toast if server is unreachable.
- **Invalid Credentials:** Login form shows inline error, does not close modal.
- **Upgrade Required:** If a Free user tries to access Pro features (Export, Team Create), show "Upgrade to Pro" modal with support email.
- **Flash Storage Full:** ESP32 storage bar in header turns red when > 90% full.
- **GPS Wait State:** UI shows "Waiting for GPS Match" (amber dot) if device is logging but hasn't matched a known track yet.
