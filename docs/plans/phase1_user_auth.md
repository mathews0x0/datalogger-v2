# Phase 1: User Authentication & Profiles

**Status:** Planned  
**Priority:** Post-March Track Session  
**Estimated Effort:** 2-3 weeks

---

## Objective

Implement user authentication so each rider has their own account with private data isolation.

---

## Requirements

### 1. User Registration
- Email + password signup
- Email verification (optional for MVP)
- OAuth options: Google, Apple (stretch goal)

### 2. User Login
- JWT-based authentication
- Refresh token for persistent sessions
- "Remember me" option

### 3. User Profile
- **Fields:**
  - Name
  - Profile photo (upload or URL)
  - Bike info (make, model, year)
  - Home track (optional)
- **Editable** via Settings page

### 4. Session-to-User Association
- Every session, track, and trackday gets a `user_id` foreign key
- Data is filtered by `user_id` in all API queries
- No cross-user data leakage

### 5. UI Changes
- Login/Register screens
- Profile page in Settings
- "My Sessions" vs "Public Sessions" distinction (Phase 2)

---

## Technical Approach

### Backend (Flask)

1. **Database:** Migrate from JSON files to PostgreSQL (or SQLite for MVP)
   - Tables: `users`, `sessions`, `tracks`, `trackdays`
   - All tables get `user_id` column

2. **Auth Library:** Use `Flask-JWT-Extended`
   - Access token (15 min expiry)
   - Refresh token (7 day expiry)
   - Stored in httpOnly cookies for security

3. **Password Hashing:** `bcrypt` or `argon2`

4. **New Endpoints:**
   ```
   POST /api/auth/register
   POST /api/auth/login
   POST /api/auth/logout
   POST /api/auth/refresh
   GET  /api/auth/me
   PUT  /api/auth/profile
   ```

5. **Middleware:** `@jwt_required()` decorator on all protected routes

### Frontend (Web App)

1. **Auth State:** Store JWT in memory (not localStorage) + refresh via httpOnly cookie
2. **Login/Register Pages:** Modal or dedicated views
3. **Protected Routes:** Redirect to login if no valid token
4. **Profile UI:** Form in Settings tab

### Database Migration

1. Create `users` table
2. Add `user_id` column to existing tables
3. Assign all existing data to a "default" user (for backward compatibility)
4. Future sessions auto-associate with logged-in user

---

## Milestones

| Milestone | Description | Est. Time |
|-----------|-------------|-----------|
| M1 | Database schema + migration scripts | 2 days |
| M2 | Auth endpoints (register, login, logout) | 2 days |
| M3 | JWT middleware + protected routes | 1 day |
| M4 | Frontend login/register UI | 2 days |
| M5 | Profile page + photo upload | 2 days |
| M6 | Data isolation (user_id filtering) | 2 days |
| M7 | Testing + edge cases | 2 days |

**Total:** ~13 days

---

## Security Considerations

- Passwords hashed with salt (never stored plain)
- JWTs signed with strong secret (env variable)
- HTTPS required in production
- Rate limiting on auth endpoints
- No user enumeration (same error for "wrong email" vs "wrong password")

---

## Out of Scope (Phase 1)

- OAuth (Google/Apple login) → Phase 1.5
- Email verification → Phase 1.5
- Password reset flow → Phase 1.5
- Subscription tiers → Phase 3
- Public/private data sharing → Phase 2

---

## Dependencies

- PostgreSQL or SQLite database
- Flask-JWT-Extended library
- bcrypt or argon2 for password hashing
- Frontend form validation

---

## Success Criteria

1. ✅ User can register with email/password
2. ✅ User can log in and receive JWT
3. ✅ Protected routes reject unauthenticated requests
4. ✅ User can view/edit their profile
5. ✅ User only sees their own sessions/tracks/trackdays
6. ✅ Existing data migrated to default user

---

## Next Steps

After Phase 1:
- **Phase 2:** Data isolation & privacy controls (public/private sessions)
- **Phase 3:** Subscription tiers (Free/Pro/Team)
