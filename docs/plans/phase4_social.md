# Phase 4: Social & Leaderboards

**Status:** Planned  
**Depends On:** Phase 3 (Complete)  
**Estimated Effort:** 1.5 weeks

---

## Objective

Add competitive and social features: leaderboards, rider following, and session comparison.

---

## Requirements

### 1. Track Leaderboards
- Best lap time per track (from public sessions only)
- Ranked list: Position, Rider Name, Lap Time, Date, Bike
- Filter by: All Time, This Month, This Week

### 2. Trackday Leaderboards
- Rankings within a specific trackday event
- Compare riders who attended same event
- Auto-generated from trackday sessions

### 3. Follow Riders
- Follow/unfollow other users
- "Following" feed: Recent public sessions from followed riders
- Follower/following counts on profile

### 4. Rider Comparison
- Compare two riders' laps on same track
- Side-by-side telemetry overlay
- Delta visualization (who's faster where)

### 5. Personal Stats
- Total laps, total sessions, total tracks
- Personal bests per track
- Improvement trends

---

## Technical Approach

### Backend

1. **New Tables:**
   ```python
   class Follow(db.Model):
       follower_id = db.Column(db.Integer, ForeignKey('users.id'))
       following_id = db.Column(db.Integer, ForeignKey('users.id'))
       created_at = db.Column(db.DateTime)
   ```

2. **Leaderboard Endpoints:**
   ```
   GET /api/leaderboards/track/<track_id>?period=all|month|week
   GET /api/leaderboards/trackday/<trackday_id>
   GET /api/users/<id>/stats
   ```

3. **Social Endpoints:**
   ```
   POST /api/users/<id>/follow
   DELETE /api/users/<id>/follow
   GET /api/users/<id>/followers
   GET /api/users/<id>/following
   GET /api/feed/following
   ```

4. **Comparison Endpoint:**
   ```
   GET /api/compare?session1=X&lap1=Y&session2=A&lap2=B
   ```

### Frontend

1. **Leaderboards Tab**
   - Track selector
   - Period filter
   - Ranked table with medals (🥇🥈🥉)

2. **Profile Enhancements**
   - Follow/Unfollow button
   - Follower/Following counts
   - Stats card

3. **Following Feed**
   - Timeline of followed riders' public sessions
   - Click to view session

4. **Comparison View**
   - Select two sessions/laps
   - Overlay visualization
   - Delta chart

---

## Milestones

| Milestone | Description | Est. Time |
|-----------|-------------|-----------|
| M1 | Follow system (model + endpoints + UI) | 1.5 days |
| M2 | Track leaderboards | 1 day |
| M3 | Trackday leaderboards | 0.5 day |
| M4 | Following feed | 1 day |
| M5 | Personal stats | 0.5 day |
| M6 | Rider comparison | 2 days |
| M7 | Polish + testing | 1 day |

---

## Success Criteria

1. ✅ Users can follow/unfollow each other
2. ✅ Track leaderboards show top times
3. ✅ Trackday leaderboards rank participants
4. ✅ Following feed shows recent activity
5. ✅ Users can compare laps between riders
6. ✅ Personal stats visible on profile

---
