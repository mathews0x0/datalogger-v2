# Admin User Management & Manual Pro Activation Plan

**Status:** Planned  
**Created:** 2025-02-09  
**Depends On:** Phase 3 (Subscriptions) - Complete  
**Estimated Effort:** 2-3 days

---

## Executive Summary

This plan adds a formal admin system to Racesense with:
1. **Database schema updates** to track admin privileges
2. **Protected admin API endpoints** for user management
3. **Admin UI tab** for viewing/searching users and toggling tiers
4. **Updated upgrade messaging** directing users to contact admin (no payment integration yet)

---

## 1. Schema Update: `is_admin` Flag

### Current State
The `User` model in `server/api/models.py` has no `is_admin` field. Admin detection currently uses a hacky check:
```python
is_admin = (current_user_id == 1 or (current_user.email and current_user.email.endswith('@racesense.v2')))
```

### Target State
Add explicit `is_admin` boolean column:

```python
# server/api/models.py - User model

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    name = db.Column(db.String(100))
    profile_photo = db.Column(db.String(255))
    bike_info = db.Column(db.String(255))
    home_track = db.Column(db.String(255))
    subscription_tier = db.Column(db.String(20), default='free')
    subscription_expires_at = db.Column(db.DateTime, nullable=True)
    is_admin = db.Column(db.Boolean, default=False)  # <-- NEW
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

### Migration Strategy
```python
# Run once to add column to existing DB
# server/api/migrate_admin.py

from models import db, User
from main import app

with app.app_context():
    # Add column if not exists (SQLite compatible)
    try:
        db.engine.execute('ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0')
        print("Added is_admin column")
    except Exception as e:
        print(f"Column may already exist: {e}")
    
    # Set first user (ID=1) as admin
    user1 = User.query.get(1)
    if user1:
        user1.is_admin = True
        db.session.commit()
        print(f"User {user1.email} is now admin")
```

### to_dict() Update
```python
def to_dict(self):
    return {
        "id": self.id,
        "email": self.email,
        "name": self.name,
        "profile_photo": self.profile_photo,
        "bike_info": self.bike_info,
        "home_track": self.home_track,
        "subscription_tier": self.subscription_tier,
        "subscription_expires_at": self.subscription_expires_at.isoformat() if self.subscription_expires_at else None,
        "is_admin": self.is_admin,  # <-- NEW
        "created_at": self.created_at.isoformat() if self.created_at else None
    }
```

---

## 2. Admin API Endpoints

### 2.1 Admin Required Decorator

Create a reusable decorator for admin-only routes:

```python
# server/api/main.py - Add near other decorators

def admin_required(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user:
            return jsonify({"error": "User not found"}), 404
        if not user.is_admin:
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated_function
```

### 2.2 List All Users

```python
@app.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_list_users():
    """
    List all users with tier, session count, and stats.
    Query params: 
      - q: search query (email/name)
      - tier: filter by tier (free/pro/team)
      - page: pagination (default 1)
      - per_page: items per page (default 50)
    """
    q = request.args.get('q', '').strip()
    tier_filter = request.args.get('tier', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    query = User.query
    
    # Search filter
    if q:
        search = f"%{q}%"
        query = query.filter(
            db.or_(
                User.email.ilike(search),
                User.name.ilike(search)
            )
        )
    
    # Tier filter
    if tier_filter and tier_filter in ['free', 'pro', 'team']:
        query = query.filter(User.subscription_tier == tier_filter)
    
    # Order by created_at desc
    query = query.order_by(User.created_at.desc())
    
    # Pagination
    total = query.count()
    users = query.offset((page - 1) * per_page).limit(per_page).all()
    
    # Enrich with session counts
    result = []
    for user in users:
        session_count = SessionMeta.query.filter_by(user_id=user.id).count()
        user_dict = user.to_dict()
        user_dict['session_count'] = session_count
        result.append(user_dict)
    
    return jsonify({
        "users": result,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page
    })
```

### 2.3 Update User Tier

Replace the existing `/api/admin/set-tier` with a RESTful endpoint:

```python
@app.route('/api/admin/users/<int:user_id>/tier', methods=['PUT'])
@admin_required
def admin_update_user_tier(user_id):
    """
    Update a user's subscription tier.
    Body: { "tier": "free" | "pro" | "team" }
    """
    target_user = User.query.get(user_id)
    if not target_user:
        return jsonify({"error": "User not found"}), 404
    
    data = request.get_json()
    new_tier = data.get('tier')
    
    if new_tier not in ['free', 'pro', 'team']:
        return jsonify({"error": "Invalid tier. Must be 'free', 'pro', or 'team'"}), 400
    
    old_tier = target_user.subscription_tier
    target_user.subscription_tier = new_tier
    
    # Clear expiry for manual upgrades (no auto-expiry)
    target_user.subscription_expires_at = None
    
    db.session.commit()
    
    return jsonify({
        "success": True,
        "user_id": user_id,
        "old_tier": old_tier,
        "new_tier": new_tier,
        "user": target_user.to_dict()
    })
```

### 2.4 Get Single User Details (Admin)

```python
@app.route('/api/admin/users/<int:user_id>', methods=['GET'])
@admin_required
def admin_get_user(user_id):
    """Get detailed user info for admin view"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    # Get stats
    session_count = SessionMeta.query.filter_by(user_id=user_id).count()
    track_count = TrackMeta.query.filter_by(user_id=user_id).count()
    
    # Team memberships
    memberships = TeamMember.query.filter_by(user_id=user_id).all()
    teams = []
    for m in memberships:
        team = Team.query.get(m.team_id)
        if team:
            teams.append({
                "team_id": team.id,
                "team_name": team.name,
                "role": m.role
            })
    
    user_dict = user.to_dict()
    user_dict['stats'] = {
        "session_count": session_count,
        "track_count": track_count,
        "team_count": len(teams)
    }
    user_dict['teams'] = teams
    
    return jsonify(user_dict)
```

### 2.5 Toggle Admin Status (Super Admin Only)

```python
@app.route('/api/admin/users/<int:user_id>/admin', methods=['PUT'])
@admin_required
def admin_toggle_admin(user_id):
    """
    Toggle admin status for a user.
    Only user_id=1 (super admin) can do this.
    Body: { "is_admin": true | false }
    """
    current_user_id = int(get_jwt_identity())
    
    # Only super admin (id=1) can grant/revoke admin
    if current_user_id != 1:
        return jsonify({"error": "Only the super admin can modify admin privileges"}), 403
    
    # Cannot demote yourself
    if user_id == 1:
        return jsonify({"error": "Cannot modify super admin privileges"}), 403
    
    target_user = User.query.get(user_id)
    if not target_user:
        return jsonify({"error": "User not found"}), 404
    
    data = request.get_json()
    is_admin = data.get('is_admin', False)
    
    target_user.is_admin = bool(is_admin)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "user_id": user_id,
        "is_admin": target_user.is_admin
    })
```

### 2.6 Deprecate Old Endpoint

Keep `/api/admin/set-tier` for backward compatibility but mark deprecated:

```python
@app.route('/api/admin/set-tier', methods=['POST'])
@admin_required
def admin_set_tier_deprecated():
    """DEPRECATED: Use PUT /api/admin/users/<id>/tier instead"""
    data = request.get_json()
    target_user_id = data.get('user_id')
    new_tier = data.get('tier')
    
    # Delegate to new endpoint logic
    if not target_user_id or not new_tier:
        return jsonify({"error": "user_id and tier required"}), 400
    
    target_user = User.query.get(target_user_id)
    if not target_user:
        return jsonify({"error": "Target user not found"}), 404
    
    if new_tier not in ['free', 'pro', 'team']:
        return jsonify({"error": "Invalid tier"}), 400
    
    target_user.subscription_tier = new_tier
    db.session.commit()
    
    return jsonify({
        "success": True, 
        "user_id": target_user_id, 
        "tier": new_tier,
        "_deprecated": "Use PUT /api/admin/users/<id>/tier instead"
    })
```

---

## 3. Admin UI Tab

### 3.1 Navigation Update

Add "Admin" tab to navigation (visible only to admins):

```html
<!-- index.html - Add to nav -->
<button class="nav-btn" data-view="admin" id="adminNavBtn" style="display: none;">
    <span class="nav-icon">⚙️</span>
    <span class="nav-label">Admin</span>
</button>
```

### 3.2 Admin View HTML

```html
<!-- index.html - Add new view section -->
<section id="adminView" class="view">
    <div class="view-header">
        <h2>User Management</h2>
        <div class="admin-stats" id="adminStats">
            <!-- Populated by JS -->
        </div>
    </div>
    
    <!-- Search & Filter Bar -->
    <div class="admin-toolbar">
        <div class="search-box">
            <input type="text" id="adminSearchInput" placeholder="Search by email or name..." />
            <button onclick="searchAdminUsers()" class="btn-icon">🔍</button>
        </div>
        <div class="filter-group">
            <select id="adminTierFilter" onchange="filterAdminUsers()">
                <option value="">All Tiers</option>
                <option value="free">Free</option>
                <option value="pro">Pro</option>
                <option value="team">Team</option>
            </select>
        </div>
    </div>
    
    <!-- Users Table -->
    <div class="admin-table-container">
        <table class="admin-table" id="adminUsersTable">
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Name / Email</th>
                    <th>Tier</th>
                    <th>Sessions</th>
                    <th>Joined</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody id="adminUsersBody">
                <!-- Populated by JS -->
            </tbody>
        </table>
    </div>
    
    <!-- Pagination -->
    <div class="admin-pagination" id="adminPagination">
        <!-- Populated by JS -->
    </div>
</section>
```

### 3.3 Admin CSS

```css
/* styles.css - Add admin styles */

/* Admin Tab Icon */
.nav-btn[data-view="admin"] .nav-icon {
    filter: hue-rotate(45deg);
}

/* Admin Toolbar */
.admin-toolbar {
    display: flex;
    gap: 1rem;
    margin-bottom: 1.5rem;
    flex-wrap: wrap;
}

.admin-toolbar .search-box {
    flex: 1;
    display: flex;
    gap: 0.5rem;
    min-width: 200px;
}

.admin-toolbar .search-box input {
    flex: 1;
    padding: 0.75rem 1rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface);
    color: var(--text);
}

.admin-toolbar .filter-group select {
    padding: 0.75rem 1rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface);
    color: var(--text);
}

/* Admin Stats Bar */
.admin-stats {
    display: flex;
    gap: 2rem;
    font-size: 0.875rem;
    color: var(--text-muted);
}

.admin-stats .stat {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.admin-stats .stat-value {
    font-weight: 600;
    color: var(--text);
}

/* Admin Table */
.admin-table-container {
    overflow-x: auto;
    border-radius: 12px;
    border: 1px solid var(--border);
}

.admin-table {
    width: 100%;
    border-collapse: collapse;
}

.admin-table th,
.admin-table td {
    padding: 1rem;
    text-align: left;
    border-bottom: 1px solid var(--border);
}

.admin-table th {
    background: var(--surface);
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    font-size: 0.75rem;
    letter-spacing: 0.05em;
}

.admin-table tbody tr:hover {
    background: var(--surface);
}

.admin-table .user-cell {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
}

.admin-table .user-name {
    font-weight: 500;
}

.admin-table .user-email {
    font-size: 0.875rem;
    color: var(--text-muted);
}

/* Tier Badge in Table */
.admin-table .tier-badge {
    display: inline-block;
    padding: 0.25rem 0.75rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
}

.tier-badge.free {
    background: var(--surface);
    color: var(--text-muted);
}

.tier-badge.pro {
    background: linear-gradient(135deg, #667eea, #764ba2);
    color: white;
}

.tier-badge.team {
    background: linear-gradient(135deg, #f093fb, #f5576c);
    color: white;
}

/* Action Buttons */
.admin-actions {
    display: flex;
    gap: 0.5rem;
}

.admin-actions .btn-upgrade {
    background: var(--primary);
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.875rem;
    transition: opacity 0.2s;
}

.admin-actions .btn-upgrade:hover {
    opacity: 0.9;
}

.admin-actions .btn-revoke {
    background: var(--error);
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.875rem;
}

/* Pagination */
.admin-pagination {
    display: flex;
    justify-content: center;
    gap: 0.5rem;
    margin-top: 1.5rem;
}

.admin-pagination button {
    padding: 0.5rem 1rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--surface);
    color: var(--text);
    cursor: pointer;
}

.admin-pagination button.active {
    background: var(--primary);
    color: white;
    border-color: var(--primary);
}

.admin-pagination button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}
```

### 3.4 Admin JavaScript

```javascript
// app.js - Add admin functions

// ============================================================================
// ADMIN USER MANAGEMENT
// ============================================================================

let adminUsersData = [];
let adminCurrentPage = 1;
let adminPerPage = 20;

async function loadAdminUsers(page = 1, query = '', tier = '') {
    const searchInput = document.getElementById('adminSearchInput');
    const tierFilter = document.getElementById('adminTierFilter');
    
    query = query || (searchInput ? searchInput.value : '');
    tier = tier || (tierFilter ? tierFilter.value : '');
    
    try {
        let url = `/api/admin/users?page=${page}&per_page=${adminPerPage}`;
        if (query) url += `&q=${encodeURIComponent(query)}`;
        if (tier) url += `&tier=${tier}`;
        
        const result = await apiCall(url);
        if (result) {
            adminUsersData = result.users;
            adminCurrentPage = result.page;
            renderAdminUsersTable(result);
            renderAdminPagination(result);
            renderAdminStats(result);
        }
    } catch (e) {
        showToast('Failed to load users: ' + e.message, 'error');
    }
}

function renderAdminStats(data) {
    const statsEl = document.getElementById('adminStats');
    if (!statsEl) return;
    
    // Calculate tier counts from loaded data (or fetch separately for accuracy)
    const freeCount = adminUsersData.filter(u => u.subscription_tier === 'free').length;
    const proCount = adminUsersData.filter(u => u.subscription_tier === 'pro').length;
    const teamCount = adminUsersData.filter(u => u.subscription_tier === 'team').length;
    
    statsEl.innerHTML = `
        <div class="stat">
            <span>Total:</span>
            <span class="stat-value">${data.total}</span>
        </div>
        <div class="stat">
            <span>Page ${data.page} of ${data.pages}</span>
        </div>
    `;
}

function renderAdminUsersTable(data) {
    const tbody = document.getElementById('adminUsersBody');
    if (!tbody) return;
    
    if (data.users.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" style="text-align: center; padding: 2rem; color: var(--text-muted);">
                    No users found
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = data.users.map(user => {
        const joinDate = user.created_at 
            ? new Date(user.created_at).toLocaleDateString() 
            : 'N/A';
        
        const isCurrentUser = currentUser && currentUser.id === user.id;
        const adminBadge = user.is_admin ? ' 👑' : '';
        
        return `
            <tr>
                <td>${user.id}</td>
                <td>
                    <div class="user-cell">
                        <span class="user-name">${user.name || 'Unnamed'}${adminBadge}</span>
                        <span class="user-email">${user.email}</span>
                    </div>
                </td>
                <td>
                    <span class="tier-badge ${user.subscription_tier}">
                        ${user.subscription_tier}
                    </span>
                </td>
                <td>${user.session_count || 0}</td>
                <td>${joinDate}</td>
                <td>
                    <div class="admin-actions">
                        ${user.subscription_tier === 'free' ? `
                            <button class="btn-upgrade" onclick="adminSetUserTier(${user.id}, 'pro')">
                                Upgrade to Pro
                            </button>
                        ` : ''}
                        ${user.subscription_tier === 'pro' ? `
                            <button class="btn-upgrade" onclick="adminSetUserTier(${user.id}, 'team')">
                                Upgrade to Team
                            </button>
                            <button class="btn-revoke" onclick="adminSetUserTier(${user.id}, 'free')">
                                Revoke
                            </button>
                        ` : ''}
                        ${user.subscription_tier === 'team' ? `
                            <button class="btn-revoke" onclick="adminSetUserTier(${user.id}, 'pro')">
                                Downgrade to Pro
                            </button>
                            <button class="btn-revoke" onclick="adminSetUserTier(${user.id}, 'free')">
                                Revoke All
                            </button>
                        ` : ''}
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

function renderAdminPagination(data) {
    const paginationEl = document.getElementById('adminPagination');
    if (!paginationEl) return;
    
    if (data.pages <= 1) {
        paginationEl.innerHTML = '';
        return;
    }
    
    let html = '';
    
    // Previous button
    html += `<button onclick="loadAdminUsers(${data.page - 1})" ${data.page <= 1 ? 'disabled' : ''}>← Prev</button>`;
    
    // Page numbers (show max 5)
    const startPage = Math.max(1, data.page - 2);
    const endPage = Math.min(data.pages, data.page + 2);
    
    for (let i = startPage; i <= endPage; i++) {
        html += `<button onclick="loadAdminUsers(${i})" class="${i === data.page ? 'active' : ''}">${i}</button>`;
    }
    
    // Next button
    html += `<button onclick="loadAdminUsers(${data.page + 1})" ${data.page >= data.pages ? 'disabled' : ''}>Next →</button>`;
    
    paginationEl.innerHTML = html;
}

async function adminSetUserTier(userId, newTier) {
    const confirmMsg = newTier === 'free' 
        ? `Revoke premium access for user ${userId}?`
        : `Upgrade user ${userId} to ${newTier}?`;
    
    if (!confirm(confirmMsg)) return;
    
    try {
        const result = await apiCall(`/api/admin/users/${userId}/tier`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tier: newTier })
        });
        
        if (result && result.success) {
            showToast(`User ${userId} updated to ${newTier}`, 'success');
            
            // Refresh current user if we updated ourselves
            if (currentUser && currentUser.id === userId) {
                await checkAuth();
            }
            
            // Refresh table
            loadAdminUsers(adminCurrentPage);
        }
    } catch (e) {
        showToast('Failed to update tier: ' + e.message, 'error');
    }
}

function searchAdminUsers() {
    const query = document.getElementById('adminSearchInput').value;
    loadAdminUsers(1, query);
}

function filterAdminUsers() {
    const tier = document.getElementById('adminTierFilter').value;
    const query = document.getElementById('adminSearchInput').value;
    loadAdminUsers(1, query, tier);
}

// Add Enter key handler for search
document.addEventListener('DOMContentLoaded', () => {
    const searchInput = document.getElementById('adminSearchInput');
    if (searchInput) {
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') searchAdminUsers();
        });
    }
});
```

### 3.5 Update showView() 

Add admin case to the view switcher:

```javascript
// In showView() function, add case:
case 'admin':
    loadAdminUsers();
    break;
```

### 3.6 Update updateAuthUI()

Show/hide admin nav based on `is_admin`:

```javascript
// In updateAuthUI() function, update admin visibility:
const adminNavBtn = document.getElementById('adminNavBtn');

if (currentUser) {
    // Show admin nav if user is admin
    if (adminNavBtn) {
        adminNavBtn.style.display = currentUser.is_admin ? 'flex' : 'none';
    }
    
    // ... rest of function
}
```

---

## 4. Pro Upgrade Messaging Update

### Current State
The `showUpgradeModal()` displays a generic "Upgrade to Pro" message with a button that says "Payment integration coming soon."

### Target State
Update to direct users to contact admin:

```javascript
// app.js - Replace showUpgradeModal

function showUpgradeModal(featureName = "") {
    const modal = document.getElementById('upgradeModal');
    const title = document.getElementById('upgradeTitle');
    const message = document.getElementById('upgradeMessage');
    const actionBtn = document.getElementById('upgradeActionBtn');

    if (featureName) {
        title.textContent = "Unlock " + featureName;
        message.innerHTML = `
            <p>The <strong>${featureName}</strong> feature is available on our Pro plan.</p>
            <p style="margin-top: 1rem;">To upgrade your account, please contact:</p>
            <a href="mailto:racesense@example.com" style="
                display: inline-block;
                margin-top: 0.5rem;
                padding: 0.75rem 1.5rem;
                background: var(--primary);
                color: white;
                border-radius: 8px;
                text-decoration: none;
                font-weight: 500;
            ">📧 racesense@example.com</a>
        `;
    } else {
        title.textContent = "Upgrade to Pro";
        message.innerHTML = `
            <p>Get unlimited session storage, CSV exports, and advanced telemetry features.</p>
            <p style="margin-top: 1rem;">To unlock Pro, contact our team:</p>
            <a href="mailto:racesense@example.com" style="
                display: inline-block;
                margin-top: 0.5rem;
                padding: 0.75rem 1.5rem;
                background: var(--primary);
                color: white;
                border-radius: 8px;
                text-decoration: none;
                font-weight: 500;
            ">📧 racesense@example.com</a>
        `;
    }

    // Hide the old upgrade button since we're using inline email link
    if (actionBtn) actionBtn.style.display = 'none';

    if (modal) modal.classList.add('active');
}
```

### Update HTML Modal Structure

```html
<!-- Update upgradeModal in index.html -->
<div id="upgradeModal" class="modal">
    <div class="modal-content upgrade-modal">
        <button class="modal-close" onclick="closeUpgradeModal()">×</button>
        <div class="upgrade-icon">🚀</div>
        <h3 id="upgradeTitle">Upgrade to Pro</h3>
        <div id="upgradeMessage" class="upgrade-message">
            <!-- Populated by JS -->
        </div>
        <button id="upgradeActionBtn" onclick="handleUpgradeClick()" class="btn-primary" style="display: none;">
            Upgrade Now
        </button>
    </div>
</div>
```

---

## 5. Implementation Checklist

### Phase A: Backend (Day 1)

- [ ] **A1:** Add `is_admin` column to User model in `models.py`
- [ ] **A2:** Update `to_dict()` to include `is_admin`
- [ ] **A3:** Create migration script to add column + set user 1 as admin
- [ ] **A4:** Run migration on development database
- [ ] **A5:** Add `admin_required` decorator in `main.py`
- [ ] **A6:** Implement `GET /api/admin/users` endpoint
- [ ] **A7:** Implement `PUT /api/admin/users/<id>/tier` endpoint
- [ ] **A8:** Implement `GET /api/admin/users/<id>` endpoint (optional detail view)
- [ ] **A9:** Update old `/api/admin/set-tier` to use `admin_required`
- [ ] **A10:** Test all endpoints with Postman/curl

### Phase B: Frontend - Admin UI (Day 2)

- [ ] **B1:** Add Admin nav button to `index.html`
- [ ] **B2:** Add Admin view section to `index.html`
- [ ] **B3:** Add admin CSS to `styles.css`
- [ ] **B4:** Add `loadAdminUsers()` and related JS functions to `app.js`
- [ ] **B5:** Update `showView()` to handle 'admin' case
- [ ] **B6:** Update `updateAuthUI()` to show/hide admin nav
- [ ] **B7:** Test admin tab visibility (show for admins, hide for regular users)
- [ ] **B8:** Test user search and tier filtering
- [ ] **B9:** Test tier upgrade/revoke buttons

### Phase C: Upgrade Messaging (Day 2)

- [ ] **C1:** Update `showUpgradeModal()` with contact email messaging
- [ ] **C2:** Update modal HTML structure
- [ ] **C3:** Test upgrade modal displays correctly for free users

### Phase D: Testing & Polish (Day 3)

- [ ] **D1:** Test full flow: login as admin → view users → upgrade user → verify
- [ ] **D2:** Test full flow: login as regular user → hit limit → see upgrade modal
- [ ] **D3:** Test search functionality with various queries
- [ ] **D4:** Test pagination with large user lists
- [ ] **D5:** Mobile responsiveness for admin table
- [ ] **D6:** Update old admin card in Settings (can deprecate or keep for quick access)

---

## 6. API Reference Summary

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/admin/users` | Admin | List all users with pagination/search |
| GET | `/api/admin/users/<id>` | Admin | Get user details |
| PUT | `/api/admin/users/<id>/tier` | Admin | Update user subscription tier |
| PUT | `/api/admin/users/<id>/admin` | Super Admin | Toggle admin status |
| POST | `/api/admin/set-tier` | Admin | (Deprecated) Legacy tier update |

---

## 7. Security Considerations

1. **Admin check uses database field** - No more hardcoded email patterns
2. **Super admin (ID=1) has special privileges** - Only they can create other admins
3. **All admin endpoints protected** - Uses `@admin_required` decorator
4. **Rate limiting** - Consider adding rate limits to admin endpoints (future)
5. **Audit logging** - Consider logging tier changes (future)

---

## 8. Future Enhancements

- [ ] Email notification when tier is changed
- [ ] Audit log for admin actions
- [ ] Bulk tier update (select multiple users)
- [ ] User suspension/ban functionality
- [ ] Admin dashboard with analytics (user growth, tier distribution charts)
- [ ] Stripe/Razorpay integration for automated payments
