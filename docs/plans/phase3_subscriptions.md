# Phase 3: Subscription Tiers

**Status:** Planned  
**Depends On:** Phase 2 (Complete)  
**Estimated Effort:** 1 week

---

## Objective

Implement tiered access with Free, Pro, and Team subscription levels.

---

## Tier Definitions

| Feature | Free | Pro ($X/mo) | Team ($Y/mo) |
|---------|------|-------------|--------------|
| Session storage | 5 sessions | Unlimited | Unlimited |
| CSV export | ❌ | ✅ | ✅ |
| Advanced analytics | ❌ | ✅ | ✅ |
| Telemetry playback | Basic | Full | Full |
| Multiple riders | ❌ | ❌ | ✅ (up to 10) |
| Shared garage | ❌ | ❌ | ✅ |
| Coach access | ❌ | ❌ | ✅ |
| Priority support | ❌ | ✅ | ✅ |

---

## Requirements

### 1. User Tier Field
- Add `subscription_tier` to User model: 'free' | 'pro' | 'team'
- Add `subscription_expires_at` datetime
- Default: 'free'

### 2. Feature Gating
- Backend middleware checks tier before allowing feature
- Frontend shows upgrade prompts for locked features
- Graceful degradation (don't break, just limit)

### 3. Session Limits (Free Tier)
- Track session count per user
- Block new session processing after limit (5)
- Show warning at 4 sessions
- Allow viewing but not creating new

### 4. Export Gating
- CSV/JSON export only for Pro+
- Show "Upgrade to Pro" modal on export click

### 5. Upgrade Flow (MVP)
- Manual tier assignment (no payment integration yet)
- Admin endpoint to set user tier
- Future: Stripe/Razorpay integration

### 6. UI Changes
- Tier badge on profile
- "Upgrade" button in header/settings
- Feature-locked indicators throughout app

---

## Technical Approach

### Backend

1. **Schema Changes:**
   ```python
   subscription_tier = db.Column(db.String(20), default='free')
   subscription_expires_at = db.Column(db.DateTime, nullable=True)
   ```

2. **Tier Check Decorator:**
   ```python
   @require_tier('pro')
   def export_session():
       ...
   ```

3. **New Endpoints:**
   ```
   GET  /api/auth/subscription     - Get current tier info
   POST /api/admin/set-tier        - Admin: set user tier (protected)
   GET  /api/sessions/limit        - Check session count vs limit
   ```

### Frontend

1. **Tier State:** Store tier in auth context
2. **Feature Gates:** Check tier before showing features
3. **Upgrade Modals:** Reusable component for locked features
4. **Limit Warnings:** Banner when approaching session limit

---

## Milestones

| Milestone | Description | Est. Time |
|-----------|-------------|-----------|
| M1 | Database schema + tier field | 0.5 day |
| M2 | Tier check middleware/decorator | 0.5 day |
| M3 | Session limit enforcement | 1 day |
| M4 | Export gating | 0.5 day |
| M5 | Frontend tier display + gates | 1 day |
| M6 | Upgrade prompts/modals | 1 day |
| M7 | Admin tier management | 0.5 day |

---

## Success Criteria

1. ✅ Users have tier field (free/pro/team)
2. ✅ Free users limited to 5 sessions
3. ✅ Export blocked for free users with upgrade prompt
4. ✅ Tier badge visible on profile
5. ✅ Admin can manually set tier

---

## Future (Phase 3.5)

- Stripe/Razorpay payment integration
- Auto-renewal logic
- Trial periods
- Referral discounts
