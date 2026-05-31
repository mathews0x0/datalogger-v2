# Multi-Rider Race View Plan

## Working Name

Primary product name:

- `Race View`

Good internal flags / engineering names:

- `multi_rider_race_view`
- `community_race_view`
- `trackday_race_view`

Recommended split:

- Rider-facing name: `Race View`
- Backend/frontend feature flag: `multi_rider_race_view`

## Product Intent

Let users see multiple public RaceSense sessions from the same track and same time window in one common playback view, with each rider shown as a separate moving dot on the same layout.

This is not a leaderboard replacement. It is a social replay mode that answers:

- Who was on track together?
- Where did overtakes likely happen?
- How close were riders through each section?
- What did the session traffic actually look like?

## Why This Fits The Current Product

The current product already has the core building blocks:

- public session sharing via `SessionMeta.is_public`
- a community feed via `/api/public/sessions`
- trackday grouping via `/api/leaderboards/trackday/<trackday_id>`
- playback artifacts per session via `<session>_playback.json`
- canonical/shared track layouts for rendering multiple riders on the same map

This means the feature can be built as a composition of existing assets instead of a brand-new telemetry pipeline.

## MVP Definition

Show a `Race View` entry point in Community or Trackday views when:

- 2 or more public sessions exist
- all sessions are on the same track
- their real-world time windows overlap enough to be considered concurrent
- playback data exists for each session

The view should:

- render all eligible riders on the same track map
- animate them using shared wall-clock time, not lap-relative time
- allow play/pause/seek
- show rider names/colors
- allow selecting which riders are visible
- default to the overlapping time window where at least 2 riders are active

MVP should not try to prove exact wheel-to-wheel truth beyond available GPS precision. It should be framed as a synchronized replay.

## Eligibility Rules

The key product requirement is: "we can say for sure there are multiple riders on a track at the same time."

Use a strict MVP rule set:

1. Same `track_id`
2. Public session only
3. Same calendar date in local display timezone
4. Session playback file exists
5. Absolute session overlap exceeds a minimum threshold

Recommended overlap threshold:

- `min_overlap_sec = 120`

Why 120 seconds:

- avoids accidental grouping of riders who were at the venue on the same day but not truly on track together
- still captures riders who joined/exited the session at different times

## Concurrency Detection

Each session already has:

- absolute sample timestamps in the server-side `Session` model
- user-facing `start_time` in `SessionMeta`
- playback rows with relative `time`

For MVP, concurrency should be decided from session-level absolute bounds:

- `session_start_epoch`
- `session_end_epoch`

Overlap formula:

- `overlap = min(end_a, end_b) - max(start_a, start_b)`

Treat sessions as concurrent only if overlap is positive and above threshold.

For groups of more than 2 riders:

- build connected components where any rider overlaps another above threshold

This prevents one giant day-level bucket.

## Required Data Improvement

Current playback rows are relative to session start:

- row field: `time`

For multi-rider playback, each row should also carry absolute wall-clock time:

- proposed field: `time_epoch`

Recommended exporter change:

- add `time_epoch = sample.timestamp`
- keep current relative `time` for existing single-session playback UI

This is the critical enabler for accurate synchronized playback across sessions.

## Playback Alignment Model

Use one shared global clock for all riders:

- global start = minimum `time_epoch` among selected sessions
- global end = maximum `time_epoch` among selected sessions

At seek time `T`:

- for each rider, find the playback row nearest to `T`
- if rider has no sample near `T`, mark rider inactive/off-track for that moment

Recommended tolerance:

- nearest sample within `250 ms`

This avoids visual jumping when one session has slightly different sample cadence.

## Rendering Model

Each rider should render as:

- unique color
- moving dot
- optional short trail
- rider label

Prefer canonical/shared track layout coordinates when available. That keeps all riders on the same stable map and avoids session-to-session shape drift.

If a canonical layout is unavailable:

- either disable Race View for that group in MVP
- or allow fallback rendering with a lower-confidence label

Recommended MVP choice:

- require canonical/shared layout

That keeps the first version defensible.

## UI Entry Points

Recommended order:

1. Trackday page
2. Community page
3. Session page deep link

### Trackday

Best first home for the feature.

Why:

- trackday already implies same venue/day grouping
- users already expect to see multiple riders there
- the current trackday leaderboard endpoint is already collecting public same-track same-day sessions

Add:

- `Open Race View` button when eligible concurrent riders exist

### Community

Add a card or rail such as:

- `Live Trackday Replays`
- `Race View Available`

This can surface grouped sessions without forcing users to discover the feature through leaderboards.

## API Plan

### New endpoint

- `GET /api/race-view/groups`

Purpose:

- return candidate concurrent public-session groups

Suggested filters:

- `track_id`
- `date`
- `trackday_id`

Response should include:

- group id
- track id / track name
- time window
- rider count
- participant list
- whether canonical layout is available

### Group detail endpoint

- `GET /api/race-view/groups/<group_id>`

Returns:

- group metadata
- rider/session metadata
- playback payloads or merged minimal row payload

MVP implementation note:

- simplest server design is to fetch individual playback payloads and merge them server-side into a compact group response
- avoid making the browser independently fetch many large session payloads if 3-6 riders are selected

## Server-Side Shape

Recommended group detail response:

- `group`
- `track`
- `participants`
- `timeline`
- `rows_by_session`

Example:

```json
{
  "group": {
    "id": "kari_2026-05-30_a",
    "start_epoch": 1748572200.0,
    "end_epoch": 1748573400.0
  },
  "track": {
    "track_id": 12,
    "track_name": "Kari Motor Speedway",
    "has_canonical_layout": true
  },
  "participants": [
    {
      "session_id": "may30Session1",
      "user_id": 4,
      "user_name": "Akhil",
      "color": "#ff6b35"
    }
  ],
  "rows_by_session": {
    "may30Session1": [
      { "time": 0.0, "time_epoch": 1748572201.22, "aligned_lat": 11.0, "aligned_lon": 77.0 }
    ]
  }
}
```

## Frontend Plan

Build this as a new playback mode, not a separate app.

Recommended path:

- reuse existing playback modal/view concepts in `server/ui/app.js`
- add a dedicated `Race View` modal or page with:
  - track canvas
  - shared time scrubber
  - rider chips/toggles
  - playback speed
  - event markers for lap start/end

Useful secondary overlays after MVP:

- ghosted trail for previous 2-3 seconds
- gap-to-nearest-rider
- lap counter per rider
- overtake event markers

## Overtake Detection

Do not make "overtake detection" a hard MVP requirement.

GPS noise can make naive pass detection look wrong.

Phase 2 approach:

- project riders onto canonical track progress
- detect ordering swaps when:
  - riders are spatially close
  - projected progress crosses
  - ordering remains swapped for a stability window

Then label those as:

- `possible overtake`

Not:

- `confirmed overtake`

## Privacy Rules

The feature should only include sessions that are already public.

Important rule:

- if a rider later unshares a session, it must disappear from Race View groups

Do not introduce any extra exposure beyond current public sharing.

Recommended copy:

- `Race View includes only riders who shared their sessions publicly.`

## Naming Options

Best options:

- `Race View`
- `Track Replay`
- `Trackday View`
- `Pack View`

Recommendation:

- use `Race View`

Reason:

- short
- easy to understand
- fits both live and replay framing
- already appears in `docs/todos.md`

## Rollout Phases

### Phase 1: Synchronized Replay

- add absolute `time_epoch` to playback rows
- detect concurrent public sessions
- build group API
- render multiple riders on one canonical map

### Phase 2: Discovery

- surface Race View groups in Community
- add Trackday call-to-action
- allow filtering by friends/following

### Phase 3: Rich Analysis

- possible overtake markers
- nearest-rider gap
- replay clips for key moments
- shareable Race View deep links

## Main Risks

### 1. Timestamp quality

This feature depends on session samples preserving trustworthy absolute GPS time.

Need verification:

- confirm exporter/session pipeline always keeps true epoch timestamps
- confirm no timezone/string conversion is being reused for playback math

### 2. Track alignment quality

If two sessions render on slightly different geometry, the replay will look fake.

Mitigation:

- require canonical/shared layout in MVP

### 3. Payload size

Three to six rider playback datasets can get heavy.

Mitigation:

- merge and trim server-side
- downsample for Race View if needed

### 4. Privacy expectations

Users may not realize "public session" implies appearance in group playback.

Mitigation:

- add explicit copy near the share toggle or Race View UI

## Recommended First Build

The most pragmatic first slice is:

1. Add `time_epoch` to playback export rows.
2. Build a backend endpoint that groups concurrent public sessions on the same track/date.
3. Only include sessions with canonical/shared layout support.
4. Add `Open Race View` to the trackday screen.
5. Reuse the existing playback rendering stack to animate multiple rider dots on one shared timeline.

That delivers the core magic without overcommitting to pass detection, live streaming, or heavy social UX.
