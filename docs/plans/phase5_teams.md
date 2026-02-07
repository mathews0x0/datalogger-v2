# Phase 5: Coach & Team Features

**Status:** Planned  
**Depends On:** Phase 4 (Complete)  
**Estimated Effort:** 1.5 weeks

---

## Objective

Enable coaching workflows and team management for professional/semi-pro riders.

---

## Requirements

### 1. Team Model
- Team entity: name, logo, owner_id
- Team members (many-to-many with users)
- Member roles: owner, coach, rider

### 2. Team Dashboard
- Aggregated stats for all team riders
- Quick access to each rider's sessions
- Team-wide leaderboard

### 3. Coach Access
- Coaches can view all team riders' data
- Read-only access to private sessions of team members
- Cannot modify rider data

### 4. Session Annotations
- Coaches can add notes to specific laps/sectors
- Annotations: text + optional timestamp/sector reference
- Riders see annotations overlaid on their session

### 5. Shared Garage (Team Pro Feature)
- Common bike profiles for the team
- Track settings shared across riders
- Baseline setups

### 6. Invite System
- Invite riders to team via email/link
- Accept/decline flow
- Leave team option

---

## Technical Approach

### Backend

1. **New Models:**
   ```python
   class Team(db.Model):
       id, name, logo_url, owner_id, created_at

   class TeamMember(db.Model):
       team_id, user_id, role ('owner'|'coach'|'rider'), joined_at

   class Annotation(db.Model):
       id, session_id, author_id, lap_number, sector_number,
       text, created_at
   ```

2. **Team Endpoints:**
   ```
   POST   /api/teams                    - Create team
   GET    /api/teams                    - List my teams
   GET    /api/teams/<id>               - Team details + members
   PUT    /api/teams/<id>               - Update team info
   DELETE /api/teams/<id>               - Delete team (owner only)
   POST   /api/teams/<id>/invite        - Generate invite link
   POST   /api/teams/join/<token>       - Accept invite
   DELETE /api/teams/<id>/members/<uid> - Remove member / leave
   ```

3. **Annotation Endpoints:**
   ```
   POST   /api/sessions/<id>/annotations  - Add annotation
   GET    /api/sessions/<id>/annotations  - List annotations
   DELETE /api/annotations/<id>           - Delete annotation
   ```

4. **Coach Access Logic:**
   - If user is coach/owner of a team, they can view team members' sessions
   - Add team check to session access logic

### Frontend

1. **Teams Tab**
   - List teams user belongs to
   - Create team button (Team tier only)
   - Team dashboard

2. **Team Dashboard**
   - Member list with roles
   - Aggregate stats
   - Recent sessions from all members

3. **Annotation UI**
   - "Add Note" button on lap/sector
   - Annotation overlay on session view
   - Coach-authored annotations marked differently

4. **Invite Flow**
   - Share invite link modal
   - Accept/decline page for invites

---

## Milestones

| Milestone | Description | Est. Time |
|-----------|-------------|-----------|
| M1 | Team + TeamMember models | 0.5 day |
| M2 | Team CRUD endpoints | 1 day |
| M3 | Teams UI (list, create, dashboard) | 1.5 days |
| M4 | Invite system | 1 day |
| M5 | Coach access logic | 1 day |
| M6 | Annotations model + endpoints | 1 day |
| M7 | Annotation UI | 1 day |
| M8 | Testing + polish | 1 day |

---

## Success Criteria

1. ✅ Users can create and manage teams
2. ✅ Riders can join teams via invite
3. ✅ Coaches can view team riders' sessions
4. ✅ Coaches can add annotations to sessions
5. ✅ Riders see coach annotations on their data
6. ✅ Team dashboard shows aggregate stats

---

## Tier Gating

- **Team Creation:** Team tier only
- **Max Members:** 10 per team (Team tier)
- **Annotations:** Pro+ can add self-annotations; Team tier for coach annotations

---
