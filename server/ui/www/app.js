// ============================================================================
// DATALOGGER COMPANION - APPLICATION LOGIC
// ============================================================================

// API Base URL (check localStorage for developer overrides)
const API_BASE = localStorage.getItem('custom_api_url') || window.location.origin;

function setCustomApiUrl() {
    const url = document.getElementById('customApiUrl').value.trim();
    if (url) {
        // Ensure it starts with http/https
        if (!url.startsWith('http')) {
            showToast('URL must start with http:// or https://', 'error');
            return;
        }
        localStorage.setItem('custom_api_url', url);
        showToast('API URL Updated. Reloading...', 'success');
        setTimeout(() => window.location.reload(), 1000);
    } else {
        localStorage.removeItem('custom_api_url');
        showToast('Reset to default API URL. Reloading...', 'success');
        setTimeout(() => window.location.reload(), 1000);
    }
}

// State
let currentView = 'home';
let tracks = [];
let sessions = [];
let activeTrackId = null;  // Track identified by ESP32 status
let lastSyncedTrackId = null; // Track we last pushed to ESP32

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('Datalogger Companion App loaded');

    // Auto-detect device IP on startup
    autoDetectDeviceIP().then(ip => {
        if (ip) {
            console.log('[Init] Auto-detected device IP:', ip);
            checkDeviceConnection();
        }
    });

    // Set up navigation
    setupNavigation();

    // Check connection
    checkConnection();

    // Check BLE support
    initBleSupportCheck();

    // Check Auth
    checkAuth();

    // Check for shared session in URL
    const path = window.location.pathname;
    if (path.startsWith('/shared/')) {
        const token = path.split('/')[2];
        if (token) {
            viewSession(null, false, token);
            return; // Don't load home data
        }
    }

    if (path.startsWith('/teams/join/')) {
        const token = path.split('/')[3];
        if (token) {
            showJoinTeamModal(token);
            // Don't return, let home data load in background
        }
    }

    // Load initial data
    loadHomeData();
});

// ============================================================================
// NAVIGATION
// ============================================================================

function setupNavigation() {
    const navButtons = document.querySelectorAll('.nav-btn');
    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const view = btn.dataset.view;
            showView(view);
        });
    });
}

function showView(viewName) {
    // Update nav buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === viewName);
    });

    // Update views
    document.querySelectorAll('.view').forEach(view => {
        view.classList.remove('active');
    });

    const targetView = document.getElementById(viewName + 'View');
    if (targetView) {
        targetView.classList.add('active');
        currentView = viewName;

        // Load data for view
        switch (viewName) {
            case 'home':
                loadHomeData();
                break;
            case 'tracks':
                loadTracks();
                break;
            case 'sessions':
                loadSessions();
                break;
            case 'community':
                loadCommunitySessions();
                break;
            case 'teams':
                loadTeams();
                break;
            case 'process':
                loadLearningFiles();
                break;
            case 'settings':
                // Load custom API URL into input if it exists
                const customUrlInput = document.getElementById('customApiUrl');
                const defaultUrlSpan = document.getElementById('defaultApiUrl');
                if (customUrlInput) customUrlInput.value = localStorage.getItem('custom_api_url') || '';
                if (defaultUrlSpan) defaultUrlSpan.textContent = window.location.origin;
                break;
        }
    }
}

// ============================================================================
// API CALLS
// ============================================================================

async function apiCall(endpoint, options = {}) {
    try {
        // Prevent caching
        const separator = endpoint.includes('?') ? '&' : '?';
        const url = `${API_BASE}${endpoint}${separator}_t=${Date.now()}`;
        const response = await fetch(url, options);

        if (response.status === 401 && !endpoint.includes('/api/auth/')) {
            showAuthModal();
            return null;
        }

        if (response.status === 403) {
            const errorData = await response.json();
            if (errorData.error === "Upgrade required" || errorData.error === "Limit reached") {
                showUpgradeModal(errorData.required_tier ? errorData.required_tier.charAt(0).toUpperCase() + errorData.required_tier.slice(1) : "Pro Feature");
                return null;
            }
        }

        if (!response.ok) {
            let errorMessage = `HTTP ${response.status}`;
            try {
                const errorData = await response.json();
                if (errorData.error) errorMessage = errorData.error;
            } catch (e) { /* ignore JSON parsing error */ }
            throw new Error(errorMessage);
        }
        return await response.json();
    } catch (error) {
        console.error('API Error:', error);
        if (!options.displayError === false) {
            showToast('Connection error', 'error');
        }
        throw error;
    }
}

// ============================================================================
// AUTHENTICATION
// ============================================================================

let currentUser = null;

async function checkAuth() {
    try {
        const user = await apiCall('/api/auth/me');
        if (user) {
            currentUser = user;
            updateAuthUI();
        }
    } catch (e) {
        currentUser = null;
        updateAuthUI();
    }
}

function updateAuthUI() {
    const loginBtn = document.getElementById('loginBtn');
    const userProfileHeader = document.getElementById('userProfileHeader');
    const headerUserName = document.getElementById('headerUserName');
    const userProfileCard = document.getElementById('userProfileCard');
    const tierBadge = document.getElementById('tierBadge');
    const adminToolsCard = document.getElementById('adminToolsCard');

    if (currentUser) {
        if (loginBtn) loginBtn.style.display = 'none';
        if (userProfileHeader) userProfileHeader.style.display = 'flex';
        if (headerUserName) headerUserName.textContent = currentUser.name || currentUser.email;

        if (tierBadge) {
            tierBadge.textContent = (currentUser.subscription_tier || 'FREE').toUpperCase();
            tierBadge.className = `tier-badge ${currentUser.subscription_tier || 'free'}`;
        }

        // Admin Check
        const isAdmin = (currentUser.id === 1 || (currentUser.email && currentUser.email.endsWith('@racesense.v2')));
        if (adminToolsCard) adminToolsCard.style.display = isAdmin ? 'block' : 'none';

        if (userProfileCard) {
            userProfileCard.style.display = 'block';
            const nameInput = document.getElementById('profileName');
            const bikeInput = document.getElementById('profileBike');
            const trackInput = document.getElementById('profileHomeTrack');
            if (nameInput) nameInput.value = currentUser.name || '';
            if (bikeInput) bikeInput.value = currentUser.bike_info || '';
            if (trackInput) trackInput.value = currentUser.home_track || '';
        }
    } else {
        if (loginBtn) loginBtn.style.display = 'block';
        if (userProfileHeader) userProfileHeader.style.display = 'none';
        if (userProfileCard) userProfileCard.style.display = 'none';
        if (adminToolsCard) adminToolsCard.style.display = 'none';
    }
}

async function adminSetTier() {
    const userId = document.getElementById('adminUserId').value;
    const tier = document.getElementById('adminTierSelect').value;

    if (!userId || !tier) {
        showToast('User ID and Tier required', 'error');
        return;
    }

    try {
        const result = await apiCall('/api/admin/set-tier', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: parseInt(userId), tier: tier })
        });
        if (result && result.success) {
            showToast(`User ${userId} tier set to ${tier}`, 'success');
            // If we updated ourselves, refresh auth
            if (parseInt(userId) === currentUser.id) {
                checkAuth();
            }
        }
    } catch (e) {
        showToast('Admin action failed: ' + e.message, 'error');
    }
}

function showUpgradeModal(featureName = "") {
    const modal = document.getElementById('upgradeModal');
    const title = document.getElementById('upgradeTitle');
    const message = document.getElementById('upgradeMessage');

    if (featureName) {
        title.textContent = "Unlock " + featureName;
        message.textContent = `The ${featureName} feature is available on our Pro plan. Upgrade now to get full access!`;
    } else {
        title.textContent = "Upgrade to Pro";
        message.textContent = "Get unlimited session storage, CSV exports, and advanced telemetry features.";
    }

    if (modal) modal.classList.add('active');
}

function closeUpgradeModal() {
    const modal = document.getElementById('upgradeModal');
    if (modal) modal.classList.remove('active');
}

function handleUpgradeClick() {
    showToast("Payment integration coming soon! Contact support for manual upgrade.", "info");
}

async function saveProfile() {
    const name = document.getElementById('profileName').value;
    const bike_info = document.getElementById('profileBike').value;
    const home_track = document.getElementById('profileHomeTrack').value;

    try {
        const result = await apiCall('/api/auth/profile', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, bike_info, home_track })
        });
        if (result) {
            currentUser = result;
            updateAuthUI();
            showToast('Profile updated', 'success');
        }
    } catch (e) {
        showToast('Failed to update profile: ' + e.message, 'error');
    }
}

function showAuthModal() {
    const modal = document.getElementById('authModal');
    if (modal) {
        modal.style.display = 'flex';
        toggleAuthMode('login');
    }
}

function closeAuthModal() {
    const modal = document.getElementById('authModal');
    if (modal) modal.style.display = 'none';
}

function toggleAuthMode(mode) {
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');
    if (mode === 'login') {
        if (loginForm) loginForm.style.display = 'block';
        if (registerForm) registerForm.style.display = 'none';
    } else {
        if (loginForm) loginForm.style.display = 'none';
        if (registerForm) registerForm.style.display = 'block';
    }
}

async function submitLogin() {
    const email = document.getElementById('loginEmail')?.value || '';
    const password = document.getElementById('loginPassword')?.value || '';
    const errorEl = document.getElementById('loginError');

    try {
        const result = await apiCall('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        if (result && result.success) {
            currentUser = result.user;
            updateAuthUI();
            closeAuthModal();
            showToast('Logged in successfully', 'success');
            // Refresh data for current view
            showView(currentView);
        }
    } catch (e) {
        if (errorEl) {
            errorEl.textContent = e.message;
            errorEl.style.display = 'block';
        }
    }
}

async function submitRegister() {
    const name = document.getElementById('regName').value;
    const email = document.getElementById('regEmail').value;
    const password = document.getElementById('regPassword').value;
    const errorEl = document.getElementById('regError');

    try {
        const result = await apiCall('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, email, password })
        });
        if (result && result.success) {
            showToast('Registered! Please login.', 'success');
            toggleAuthMode('login');
        }
    } catch (e) {
        if (errorEl) {
            errorEl.textContent = e.message;
            errorEl.style.display = 'block';
        }
    }
}

async function logout() {
    try {
        await apiCall('/api/auth/logout', { method: 'POST' });
    } catch (e) { }
    currentUser = null;
    updateAuthUI();
    showToast('Logged out', 'info');
    // Refresh to home
    showView('home');
}

async function checkConnection() {
    try {
        await apiCall('/api/health');
        updateConnectionStatus(true);
    } catch (error) {
        updateConnectionStatus(false);
    }
}

function updateConnectionStatus(connected) {
    const statusEl = document.getElementById('connectionStatus');
    const dot = statusEl.querySelector('.status-dot');
    const text = document.getElementById('connText');

    if (connected) {
        statusEl.classList.remove('offline');
        statusEl.classList.add('online');
        dot.classList.add('connected');
        text.textContent = 'Connected';
    } else {
        statusEl.classList.remove('online');
        statusEl.classList.add('offline');
        dot.classList.remove('connected');
        text.textContent = 'Disconnected';
    }
}

async function pollStatus() {
    try {
        // 1. Get Pi Status (Recording, Storage, etc)
        const res = await apiCall('/api/status', { displayError: false });
        // Update Recording Dot
        const recEl = document.getElementById('recordingStatus');
        if (recEl) {
            recEl.style.display = (res.is_recording) ? 'flex' : 'none';
        }

        // 2. Get Device (ESP32) Status if IP is known
        const deviceIP = localStorage.getItem('lastDeviceIP');
        if (deviceIP) {
            try {
                const espRes = await fetch(`http://${deviceIP}/status?_t=${Date.now()}`).then(r => r.json());

                // Update Storage Bar
                const storageEl = document.getElementById('storageIndicator');
                if (storageEl) {
                    storageEl.style.display = 'flex';
                    const fill = document.getElementById('storageBarFill');
                    const text = document.getElementById('storageText');
                    const pct = espRes.storage_used_pct || 0;
                    fill.style.width = pct + '%';
                    text.textContent = pct + '%';
                    fill.style.background = pct > 90 ? 'var(--error)' : (pct > 70 ? 'var(--warning)' : 'var(--success)');
                }

                // Update Active Track Badge
                const trackBadge = document.getElementById('activeTrackBadge');
                const trackNameEl = document.getElementById('activeTrackName');
                const identDot = document.getElementById('trackIdentifiedDot');

                if (espRes.active_track) {
                    trackBadge.style.display = 'flex';
                    activeTrackId = espRes.active_track;

                    // Track Identification Status
                    identDot.style.background = espRes.track_identified ? 'var(--success)' : 'var(--text-muted)';
                    identDot.title = espRes.track_identified ? 'Track Matches GPS' : 'Waiting for GPS Match';

                    // Find track name locally
                    const track = tracks.find(t => t.track_id == activeTrackId);
                    trackNameEl.textContent = track ? track.track_name : `Track ${activeTrackId}`;

                    // AUTO SYNC: If track is set on device but we haven't synced it yet this session
                    if (activeTrackId !== lastSyncedTrackId) {
                        ensureTrackSynced(activeTrackId, deviceIP);
                    }
                } else {
                    trackBadge.style.display = 'none';
                    activeTrackId = null;
                }

            } catch (espErr) {
                // Device likely offline
                document.getElementById('storageIndicator').style.display = 'none';
                document.getElementById('activeTrackBadge').style.display = 'none';
            }
        }

    } catch (e) {
        // Ignore errors during poll
    }
}

/**
 * Ensures the full track metadata from Pi is pushed to the ESP32
 */
async function ensureTrackSynced(trackId, deviceIP) {
    if (!deviceIP) return;

    try {
        console.log(`[Sync] Auto-syncing track ${trackId} to device...`);
        const trackData = await apiCall(`/api/tracks/${trackId}`);

        // Format for ESP32
        const payload = {
            id: trackData.track_id.toString(),
            name: trackData.track_name,
            pit_center_lat: trackData.pit_center_lat,
            pit_center_lon: trackData.pit_center_lon,
            pit_radius_m: trackData.pit_radius_m || 50,
            start_line: {
                lat: trackData.start_line.lat,
                lon: trackData.start_line.lon,
                radius_m: 20
            },
            sectors: trackData.sectors.map((s, idx) => ({
                idx: idx,
                end_lat: s.end_lat,
                end_lon: s.end_lon
            })),
            tbl: {}
        };

        // Format TBL: Convert from list to dict with string keys
        if (trackData.tbl && trackData.tbl.sectors) {
            trackData.tbl.sectors.forEach((time, idx) => {
                payload.tbl[idx.toString()] = time;
            });
        }

        const resp = await fetch(`http://${deviceIP}/track/set`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        if (resp.ok) {
            console.log(`[Sync] Track ${trackId} synced successfully`);
            lastSyncedTrackId = trackId;
        }
    } catch (err) {
        console.error(`[Sync] Failed to sync track ${trackId}:`, err);
    }
}

// ============================================================================
// SOCIAL & COMMUNITY FEATURES
// ============================================================================

function switchCommunityTab(tab) {
    // Update tab buttons
    document.querySelectorAll('[data-comm-tab]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.commTab === tab);
    });

    // Show/hide panels
    const explorePanel = document.getElementById('explorePanel');
    const followingPanel = document.getElementById('followingPanel');
    const leaderboardsPanel = document.getElementById('leaderboardsPanel');

    if (explorePanel) explorePanel.style.display = tab === 'explore' ? 'block' : 'none';
    if (followingPanel) followingPanel.style.display = tab === 'following' ? 'block' : 'none';
    if (leaderboardsPanel) leaderboardsPanel.style.display = tab === 'leaderboards' ? 'block' : 'none';

    // Load data
    if (tab === 'explore') {
        loadCommunitySessions();
    } else if (tab === 'following') {
        loadFollowingFeed();
    } else if (tab === 'leaderboards') {
        loadLeaderboardTracks();
    }
}

async function loadFollowingFeed() {
    const container = document.getElementById('followingFeedList');
    if (!container) return;
    container.innerHTML = renderSkeletonCards(3, 'session');

    try {
        const feed = await apiCall('/api/feed/following');

        if (!feed || feed.length === 0) {
            container.innerHTML = renderEmptyState(
                '👥',
                'Your feed is empty',
                "You're not following anyone yet. Discover fast riders in the Explore tab!",
                'Explore Riders',
                "switchCommunityTab('explore')"
            );
            return;
        }

        container.innerHTML = feed.map(session => `
            <div class="session-card" onclick="viewSession('${session.session_id}', true)">
                <div class="session-header">
                    <div>
                        <div class="session-title">${session.track_name}</div>
                        <div style="font-size: 0.8rem; color: var(--primary); font-weight: 600; cursor: pointer;" onclick="event.stopPropagation(); showUserProfile(${session.owner_id})">👤 ${session.owner_name}</div>
                    </div>
                    <div class="session-time">${formatDateTimeAbbreviated(session.start_time)}</div>
                </div>
                <div class="session-stats">
                    <div class="session-stat">
                        <span>Laps:</span>
                        <strong>${session.total_laps}</strong>
                    </div>
                    <div class="session-stat">
                        <span>Best:</span>
                        <strong style="color: var(--success);">${formatTime(session.best_lap_time)}</strong>
                    </div>
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = '<p class="help-text">Failed to load feed</p>';
    }
}

async function loadLeaderboardTracks() {
    const select = document.getElementById('lbTrackSelect');
    if (!select || select.options.length > 1) return; // Already loaded

    try {
        const data = await apiCall('/api/tracks');
        select.innerHTML = '<option value="">Select Track...</option>' +
            data.tracks.map(t => `<option value="${t.track_id}">${t.track_name}</option>`).join('');
    } catch (e) { }
}

async function loadLeaderboard() {
    const trackId = document.getElementById('lbTrackSelect').value;
    const period = document.getElementById('lbPeriodSelect').value;
    const container = document.getElementById('leaderboardContent');

    if (!trackId) {
        container.innerHTML = renderEmptyState(
            '🏆',
            'Select a track',
            'Choose a track from the dropdown to view the leaderboard rankings.'
        );
        return;
    }

    container.innerHTML = '<div class="loading">Loading leaderboard...</div>';

    try {
        const leaderboard = await apiCall(`/api/leaderboards/track/${trackId}?period=${period}`);

        if (!leaderboard || leaderboard.length === 0) {
            container.innerHTML = renderEmptyState(
                '🏁',
                'No times recorded',
                'Be the first to set a public lap time on this track!'
            );
            return;
        }

        container.innerHTML = `
            <div class="table-responsive">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th style="width: 40px;">#</th>
                            <th>Rider</th>
                            <th>Time</th>
                            <th>Bike</th>
                            <th class="hide-mobile">Date</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${leaderboard.map(entry => {
            let rankDisplay = entry.rank;
            if (entry.rank === 1) rankDisplay = '🥇';
            else if (entry.rank === 2) rankDisplay = '🥈';
            else if (entry.rank === 3) rankDisplay = '🥉';

            return `
                            <tr onclick="viewSession('${entry.session_id}', true)" style="cursor: pointer;">
                                <td style="font-weight: 700;">${rankDisplay}</td>
                                <td>
                                    <div style="display: flex; flex-direction: column;">
                                        <span style="font-weight: 600; color: var(--primary);" onclick="event.stopPropagation(); showUserProfile(${entry.user_id})">${entry.user_name}</span>
                                    </div>
                                </td>
                                <td style="font-family: monospace; font-weight: 700; color: var(--success);">${formatTime(entry.lap_time)}</td>
                                <td style="font-size: 0.8rem; color: var(--text-dim);">${entry.bike_info || '-'}</td>
                                <td class="hide-mobile" style="font-size: 0.75rem; color: var(--text-muted);">${formatDateShort(entry.date)}</td>
                            </tr>
                            `;
        }).join('')}
                    </tbody>
                </table>
            </div>
        `;
    } catch (error) {
        container.innerHTML = '<p class="help-text">Failed to load leaderboard</p>';
    }
}

async function showUserProfile(userId) {
    const view = document.getElementById('userProfileView');
    const container = document.getElementById('userProfileContent');

    if (!view || !container) return;

    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    view.classList.add('active');

    container.innerHTML = '<div class="loading">Loading profile...</div>';

    try {
        // Fetch stats and user info
        const stats = await apiCall(`/api/users/${userId}/stats`);
        const social = await apiCall(`/api/users/${userId}/social-counts`);

        const name = stats.name || `Rider ${userId}`;

        container.innerHTML = `
            <div class="profile-header card" style="margin-bottom: 1.5rem; text-align: center; padding: 2rem;">
                <div style="font-size: 4rem; margin-bottom: 1rem; color: var(--primary);">
                    <i class="fas fa-user-circle"></i>
                </div>
                <h2>${name}</h2>
                <div style="display: flex; justify-content: center; gap: 2rem; margin: 1.5rem 0;">
                    <div style="text-align: center;">
                        <div style="font-size: 1.5rem; font-weight: 800;">${social.followers_count}</div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">Followers</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="font-size: 1.5rem; font-weight: 800;">${social.following_count}</div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">Following</div>
                    </div>
                </div>
                
                ${currentUser && currentUser.id != userId ? `
                    <button class="btn ${social.is_following ? 'secondary' : 'btn-primary'}" id="followBtn" onclick="toggleFollow(${userId}, ${social.is_following})">
                        ${social.is_following ? '<i class="fas fa-user-minus"></i> Unfollow' : '<i class="fas fa-user-plus"></i> Follow'}
                    </button>
                ` : ''}
            </div>

            <div class="quick-stats" style="margin-bottom: 1.5rem;">
                <div class="stat-card">
                    <div class="stat-info">
                        <div class="stat-label">Total Sessions</div>
                        <div class="stat-value">${stats.total_sessions}</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-info">
                        <div class="stat-label">Total Laps</div>
                        <div class="stat-value">${stats.total_laps}</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-info">
                        <div class="stat-label">Tracks Visited</div>
                        <div class="stat-value">${stats.tracks_visited}</div>
                    </div>
                </div>
            </div>

            <div class="card">
                <h3>Personal Bests</h3>
                ${!stats.personal_bests || stats.personal_bests.length === 0 ? '<p class="help-text">No public personal bests recorded.</p>' : `
                    <div class="pb-list">
                        ${stats.personal_bests.map(pb => `
                            <div style="display: flex; justify-content: space-between; padding: 0.75rem 0; border-bottom: 1px solid var(--border);">
                                <span style="font-weight: 600;">${pb.track_name}</span>
                                <span style="font-family: monospace; font-weight: 700; color: var(--success);">${formatTime(pb.best_lap)}</span>
                            </div>
                        `).join('')}
                    </div>
                `}
            </div>
        `;
    } catch (error) {
        container.innerHTML = '<p class="help-text">Failed to load profile</p>';
    }
}

async function toggleFollow(userId, currentlyFollowing) {
    try {
        const method = currentlyFollowing ? 'DELETE' : 'POST';
        const result = await apiCall(`/api/users/${userId}/follow`, { method });

        if (result && result.success) {
            showToast(currentlyFollowing ? 'Unfollowed' : 'Now following', 'success');
            // Refresh profile view
            showUserProfile(userId);
        }
    } catch (e) {
        showToast('Action failed: ' + e.message, 'error');
    }
}

function formatDateShort(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

// ============================================================================
// TEAM FEATURES (Phase 5)
// ============================================================================

async function loadTeams() {
    const container = document.getElementById('teamsList');
    if (!container) return;
    container.innerHTML = renderSkeletonCards(4, 'track');

    try {
        const teamsData = await apiCall('/api/teams');

        if (!teamsData || teamsData.length === 0) {
            const canCreate = currentUser && currentUser.subscription_tier === 'team';
            container.innerHTML = renderEmptyState(
                '👥',
                'No teams yet',
                canCreate
                    ? 'Create a team to collaborate with other riders and coaches.'
                    : 'Join a team via invite link, or upgrade to Team tier to create your own.',
                canCreate ? 'Create Team' : null,
                canCreate ? 'showCreateTeamModal()' : null
            );
            return;
        }

        container.innerHTML = teamsData.map(team => `
            <div class="track-card" onclick="viewTeam(${team.id})">
                <div style="height: 120px; background: var(--bg-secondary); display: flex; align-items: center; justify-content: center; border-radius: 8px 8px 0 0; overflow: hidden;">
                    ${team.logo_url ? `<img src="${team.logo_url}" style="max-width: 80%; max-height: 80%; object-fit: contain;">` : `<i class="fas fa-users" style="font-size: 3rem; color: var(--border);"></i>`}
                </div>
                <div class="track-info">
                    <div class="track-name">${team.name}</div>
                    <div class="track-meta">
                        <span><i class="fas fa-user-shield"></i> Role: ${team.my_role.toUpperCase()}</span>
                    </div>
                    <div class="track-actions">
                        <button class="btn btn-primary btn-sm">View Dashboard</button>
                    </div>
                </div>
            </div>
        `).join('');
    } catch (error) {
        container.innerHTML = '<p class="help-text">Failed to load teams</p>';
    }
}

function showCreateTeamModal() {
    if (currentUser.subscription_tier !== 'team') {
        showUpgradeModal('Team Creation');
        return;
    }
    const modal = document.getElementById('createTeamModal');
    if (modal) modal.classList.add('active');
}

function closeCreateTeamModal() {
    const modal = document.getElementById('createTeamModal');
    if (modal) modal.classList.remove('active');
}

async function submitCreateTeam() {
    const name = document.getElementById('teamNameInput').value.trim();
    const logo_url = document.getElementById('teamLogoInput').value.trim();

    if (!name) {
        showToast('Team name is required', 'error');
        return;
    }

    try {
        const result = await apiCall('/api/teams', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, logo_url })
        });
        if (result) {
            showToast('Team created successfully!', 'success');
            closeCreateTeamModal();
            loadTeams();
        }
    } catch (e) {
        showToast('Failed to create team: ' + e.message, 'error');
    }
}

async function viewTeam(teamId) {
    const view = document.getElementById('teamDetailView');
    const container = document.getElementById('teamDetailContent');

    if (!view || !container) return;

    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    view.classList.add('active');

    container.innerHTML = '<div class="loading">Loading team details...</div>';

    try {
        const team = await apiCall(`/api/teams/${teamId}`);
        const isOwner = team.owner_id === currentUser.id;
        const myMembership = team.members.find(m => m.user_id === currentUser.id);
        const isCoachOrOwner = myMembership && ['owner', 'coach'].includes(myMembership.role);

        container.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 2rem;">
                <div style="display: flex; gap: 1.5rem; align-items: center;">
                    <div style="width: 80px; height: 80px; background: var(--bg-secondary); border-radius: 12px; display: flex; align-items: center; justify-content: center; overflow: hidden; border: 1px solid var(--border);">
                        ${team.logo_url ? `<img src="${team.logo_url}" style="max-width: 100%; max-height: 100%; object-fit: contain;">` : `<i class="fas fa-users" style="font-size: 2rem; color: var(--border);"></i>`}
                    </div>
                    <div>
                        <h2 style="margin: 0;">${team.name}</h2>
                        <p class="help-text" style="margin: 0.25rem 0 0 0;">Team ID: ${team.id} • Created ${formatDateShort(team.created_at)}</p>
                    </div>
                </div>
                <div style="display: flex; gap: 0.5rem;">
                    ${isCoachOrOwner ? `<button class="btn btn-primary btn-sm" onclick="showTeamInviteModal(${team.id})"><i class="fas fa-user-plus"></i> Invite Rider</button>` : ''}
                    ${isOwner ? `<button class="btn btn-secondary btn-sm" onclick="editTeam(${team.id})"><i class="fas fa-edit"></i> Edit</button>` : ''}
                    ${!isOwner ? `<button class="btn btn-danger btn-sm" onclick="leaveTeam(${team.id})">Leave Team</button>` : ''}
                </div>
            </div>

            <div class="settings-grid" style="grid-template-columns: 1fr 2fr; gap: 1.5rem;">
                <!-- Member List -->
                <div class="card">
                    <h3>Members</h3>
                    <div class="members-list">
                        ${team.members.map(m => `
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.75rem 0; border-bottom: 1px solid var(--border);">
                                <div style="display: flex; align-items: center; gap: 0.75rem;">
                                    <div style="width: 32px; height: 32px; background: var(--primary); color: #000; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 0.8rem;">
                                        ${(m.name || m.email).charAt(0).toUpperCase()}
                                    </div>
                                    <div style="display: flex; flex-direction: column;">
                                        <span style="font-weight: 600; font-size: 0.9rem;">${m.name || m.email}</span>
                                        <span class="badge" style="font-size: 0.6rem; width: fit-content; margin-top: 2px;">${m.role.toUpperCase()}</span>
                                    </div>
                                </div>
                                ${isCoachOrOwner && m.user_id !== currentUser.id && m.role !== 'owner' ? `
                                    <button class="btn-icon" onclick="removeTeamMember(${team.id}, ${m.user_id})" title="Remove Member">×</button>
                                ` : ''}
                            </div>
                        `).join('')}
                    </div>
                </div>

                <!-- Team Sessions / Dashboard -->
                <div class="card">
                    <h3>Rider Sessions</h3>
                    <div id="teamSessionsList" class="sessions-list">
                        <div class="loading">Loading rider sessions...</div>
                    </div>
                </div>
            </div>
        `;

        // Load sessions for team members
        loadTeamSessions(team.members.filter(m => m.role === 'rider').map(m => m.user_id));

    } catch (error) {
        container.innerHTML = '<p class="help-text">Failed to load team details</p>';
    }
}

async function loadTeamSessions(riderIds) {
    const container = document.getElementById('teamSessionsList');
    if (!container) return;

    if (!riderIds || riderIds.length === 0) {
        container.innerHTML = '<p class="help-text">No riders in this team yet.</p>';
        return;
    }

    try {
        // Since our API doesn't have a bulk rider session endpoint, we'll fetch community/public sessions 
        // OR we can rely on the fact that if we are coach, we can now access their private sessions too.
        // For now, let's fetch sessions for each rider.

        let allTeamSessions = [];
        for (const riderId of riderIds) {
            try {
                // We need an endpoint to list a user's sessions if we are their coach
                // Or we can update /api/sessions to take a user_id
                const riderSessions = await apiCall(`/api/sessions?user_id=${riderId}`);
                if (riderSessions) {
                    allTeamSessions = allTeamSessions.concat(riderSessions);
                }
            } catch (e) {
                console.warn(`Could not load sessions for rider ${riderId}`);
            }
        }

        if (allTeamSessions.length === 0) {
            container.innerHTML = '<p class="help-text">No sessions found for team riders.</p>';
            return;
        }

        // Sort by time
        allTeamSessions.sort((a, b) => new Date(b.start_time) - new Date(a.start_time));

        container.innerHTML = allTeamSessions.slice(0, 20).map(session => `
            <div class="session-card" onclick="viewSession('${session.session_id}')">
                <div class="session-header">
                    <div>
                        <div class="session-title">${session.track_name}</div>
                        <div style="font-size: 0.75rem; color: var(--primary);">👤 ${session.owner_name || 'Rider'}</div>
                    </div>
                    <div class="session-time">${formatDateTimeAbbreviated(session.start_time)}</div>
                </div>
                <div class="session-stats">
                    <div class="session-stat">
                        <span>Best:</span>
                        <strong style="color: var(--success);">${formatTime(session.best_lap_time)}</strong>
                    </div>
                    ${session.is_public ? '<span class="badge" style="background: var(--primary); color: white;"><i class="fas fa-globe"></i> Public</span>' : '<span class="badge" style="background: var(--border); color: var(--text-muted);"><i class="fas fa-lock"></i> Team Only</span>'}
                </div>
            </div>
        `).join('');

    } catch (error) {
        container.innerHTML = '<p class="help-text">Failed to load team sessions</p>';
    }
}

async function showTeamInviteModal(teamId) {
    try {
        const result = await apiCall(`/api/teams/${teamId}/invite`, { method: 'POST' });
        if (result) {
            const inviteUrl = window.location.origin + result.invite_url;
            document.getElementById('teamInviteLinkInput').value = inviteUrl;
            document.getElementById('teamInviteModal').classList.add('active');
        }
    } catch (e) {
        showToast('Failed to generate invite: ' + e.message, 'error');
    }
}

function closeTeamInviteModal() {
    document.getElementById('teamInviteModal').classList.remove('active');
}

function copyTeamInviteLink() {
    const input = document.getElementById('teamInviteLinkInput');
    input.select();
    input.setSelectionRange(0, 99999);
    document.execCommand('copy');
    showToast('Invite link copied!', 'success');
}

async function removeTeamMember(teamId, userId) {
    if (!confirm('Remove this member from the team?')) return;

    try {
        await apiCall(`/api/teams/${teamId}/members/${userId}`, { method: 'DELETE' });
        showToast('Member removed', 'success');
        viewTeam(teamId);
    } catch (e) {
        showToast('Failed to remove member: ' + e.message, 'error');
    }
}

async function leaveTeam(teamId) {
    if (!confirm('Are you sure you want to leave this team?')) return;

    try {
        await apiCall(`/api/teams/${teamId}/members/${currentUser.id}`, { method: 'DELETE' });
        showToast('Left team', 'success');
        showView('teams');
    } catch (e) {
        showToast('Failed to leave team: ' + e.message, 'error');
    }
}

// ----------------------------------------------------------------------------
// ANNOTATIONS (Phase 5)
// ----------------------------------------------------------------------------

let currentSessionAnnotations = [];

async function loadAnnotations(sessionId, containerId = 'pbAnnotationsList') {
    try {
        const annotations = await apiCall(`/api/sessions/${sessionId}/annotations`);
        currentSessionAnnotations = annotations || [];
        renderAnnotations(containerId);
    } catch (e) {
        console.warn('Could not load annotations:', e);
    }
}

function loadAnnotationsForDetail(sessionId) {
    loadAnnotations(sessionId, 'detailAnnotationsList');
}

function renderAnnotations(containerId = 'pbAnnotationsList') {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (!currentSessionAnnotations || currentSessionAnnotations.length === 0) {
        container.innerHTML = `
            <div class="empty-state" style="padding: 1rem 0;">
                <p style="font-size: 0.75rem; color: var(--text-muted);">No notes for this session</p>
            </div>
        `;
        return;
    }

    container.innerHTML = currentSessionAnnotations.map(a => `
        <div class="card" style="padding: 0.75rem; margin-bottom: 0.75rem; border-left: 3px solid var(--primary); background: rgba(255,255,255,0.02);">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.25rem;">
                <div style="font-weight: bold; color: var(--primary); font-size: 0.75rem;">
                    ${a.author_name} ${a.lap_number ? `• Lap ${a.lap_number}` : ''} ${a.sector_number ? `• S${a.sector_number}` : ''}
                </div>
                ${currentUser && a.author_id === currentUser.id ? `
                    <button class="btn-icon" onclick="deleteAnnotation(${a.id})" style="font-size: 0.7rem; opacity: 0.5;">×</button>
                ` : ''}
            </div>
            <div style="font-size: 0.85rem; line-height: 1.4;">${a.text}</div>
            <div style="font-size: 0.65rem; color: var(--text-muted); margin-top: 0.4rem; text-align: right;">
                ${formatDateTimeAbbreviated(a.created_at)}
            </div>
        </div>
    `).join('');
}

function showAddAnnotationModalWithLap(sessionId, lapNumber) {
    if (!pbState.session || pbState.session.meta.session_id !== sessionId) {
        pbState.session = { meta: { session_id: sessionId } };
    }

    const modal = document.getElementById('annotationModal');
    if (!modal) return;

    document.getElementById('annotationLapInput').value = lapNumber;
    document.getElementById('annotationSectorInput').value = '';

    modal.classList.add('active');
    window.annotationSource = 'detail';
}

function showAddAnnotationModalFromDetail(sessionId) {
    // Set up pbState.session if not in playback
    if (!pbState.session || pbState.session.meta.session_id !== sessionId) {
        pbState.session = { meta: { session_id: sessionId } };
    }

    const modal = document.getElementById('annotationModal');
    if (!modal) return;

    document.getElementById('annotationLapInput').value = '';
    document.getElementById('annotationSectorInput').value = '';

    modal.classList.add('active');

    // Track where we came from to refresh the right list
    window.annotationSource = 'detail';
}

function showAddAnnotationModal() {
    if (!pbState.session) return;

    const modal = document.getElementById('annotationModal');
    if (!modal) return;

    // Prefill lap/sector if possible
    const lapInput = document.getElementById('annotationLapInput');
    const sectorInput = document.getElementById('annotationSectorInput');

    // Try to guess current lap from playback state
    if (pbState.data && pbState.data.time) {
        const curTime = pbState.data.time[pbState.currentIndex];
        const curLap = pbState.laps.find(l => curTime >= l.start_time && (!l.end_time || curTime <= l.end_time));
        if (curLap) {
            lapInput.value = curLap.lap_number;
        }
    }

    modal.classList.add('active');
    window.annotationSource = 'playback';
}

function closeAnnotationModal() {
    document.getElementById('annotationModal').classList.remove('active');
}

async function submitAddAnnotation() {
    const text = document.getElementById('annotationTextInput').value.trim();
    const lap = document.getElementById('annotationLapInput').value;
    const sector = document.getElementById('annotationSectorInput').value;

    if (!text) {
        showToast('Note text is required', 'error');
        return;
    }

    try {
        const result = await apiCall(`/api/sessions/${pbState.session.meta.session_id}/annotations`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text,
                lap_number: lap ? parseInt(lap) : null,
                sector_number: sector ? parseInt(sector) : null
            })
        });

        if (result) {
            showToast('Note added', 'success');
            closeAnnotationModal();
            document.getElementById('annotationTextInput').value = '';

            if (window.annotationSource === 'detail') {
                loadAnnotationsForDetail(pbState.session.meta.session_id);
            } else {
                loadAnnotations(pbState.session.meta.session_id);
            }
        }
    } catch (e) {
        showToast('Failed to add note: ' + e.message, 'error');
    }
}

async function deleteAnnotation(id) {
    if (!confirm('Delete this note?')) return;

    try {
        await apiCall(`/api/annotations/${id}`, { method: 'DELETE' });
        showToast('Note deleted', 'success');

        if (window.annotationSource === 'detail') {
            loadAnnotationsForDetail(pbState.session.meta.session_id);
        } else {
            loadAnnotations(pbState.session.meta.session_id);
        }
    } catch (e) {
        showToast('Failed to delete note', 'error');
    }
}

let pendingJoinToken = null;

async function showJoinTeamModal(token) {
    pendingJoinToken = token;
    const modal = document.getElementById('joinTeamModal');
    if (!modal) return;

    modal.classList.add('active');

    // Optional: fetch team name if possible without joining
    // For now, we'll just show the modal
}

function closeJoinTeamModal() {
    document.getElementById('joinTeamModal').classList.remove('active');
    pendingJoinToken = null;
    window.history.replaceState({}, document.title, "/");
}

async function submitJoinTeam() {
    if (!pendingJoinToken) return;

    if (!currentUser) {
        showToast('Please login to join the team', 'info');
        showAuthModal();
        return;
    }

    const btn = document.getElementById('confirmJoinBtn');
    btn.disabled = true;
    btn.textContent = 'Joining...';

    try {
        const result = await apiCall(`/api/teams/join/${pendingJoinToken}`, { method: 'POST' });
        if (result && result.success) {
            showToast(`Successfully joined team: ${result.team_name}`, 'success');
            closeJoinTeamModal();
            showView('teams');
        }
    } catch (e) {
        showToast('Failed to join team: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Join Team';
    }
}

// ----------------------------------------------------------------------------
// TRACKDAY LEADERBOARD (M3)
// ----------------------------------------------------------------------------

async function loadTrackdayLeaderboard(trackdayId) {
    const container = document.getElementById('trackdayLeaderboardContent');
    if (!container) return;

    container.innerHTML = '<div class="loading">Loading leaderboard...</div>';

    try {
        const data = await apiCall(`/api/leaderboards/trackday/${trackdayId}`);

        if (!data.leaderboard || data.leaderboard.length === 0) {
            container.innerHTML = '<p class="help-text">No public lap times recorded for this trackday yet.</p>';
            return;
        }

        container.innerHTML = `
            <table class="data-table">
                <thead>
                    <tr>
                        <th style="width: 40px;">#</th>
                        <th>Rider</th>
                        <th>Best Lap</th>
                        <th>Bike</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.leaderboard.map(entry => `
                        <tr onclick="viewSession('${entry.session_id}', true)" style="cursor: pointer;">
                            <td>${entry.rank}</td>
                            <td>
                                <span style="font-weight: 600; color: var(--primary);" onclick="event.stopPropagation(); showUserProfile(${entry.user_id})">${entry.user_name}</span>
                            </td>
                            <td style="font-family: monospace; font-weight: 700; color: var(--success);">${formatTime(entry.lap_time)}</td>
                            <td style="font-size: 0.8rem; color: var(--text-dim);">${entry.bike_info || '-'}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    } catch (e) {
        container.innerHTML = '<p class="help-text">Failed to load leaderboard</p>';
    }
}

// ----------------------------------------------------------------------------
// HELPER FUNCTIONS (Formatting)
// ----------------------------------------------------------------------------

function formatDate(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
}

function formatDateTimeAbbreviated(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' +
        d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
}

function formatTime24h(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
}

async function loadHomeData() {
    try {
        // Load tracks and sessions
        const [tracksData, sessionsData] = await Promise.all([
            apiCall('/api/tracks'),
            apiCall('/api/sessions')
        ]);

        tracks = tracksData.tracks || [];
        sessions = sessionsData || [];

        // Update quick stats
        document.getElementById('totalTracks').textContent = tracks.length;
        document.getElementById('totalSessions').textContent = sessions.length;

        if (sessions.length > 0) {
            const lastSession = new Date(sessions[0].start_time);
            document.getElementById('recentSession').textContent = lastSession.toLocaleDateString();
        } else {
            document.getElementById('recentSession').textContent = 'None';
        }

        // Show recent sessions (last 5)
        renderRecentSessions(sessions.slice(0, 5));

    } catch (error) {
        console.error('Failed to load home data:', error);
    }
}

function renderRecentSessions(recentSessions) {
    const container = document.getElementById('recentSessionsList');

    if (recentSessions.length === 0) {
        container.innerHTML = renderEmptyState(
            '🏁',
            'No sessions yet',
            'Connect your device and hit the track to start logging laps!',
            'Connect Device',
            "showView('settings')"
        );
        return;
    }

    container.innerHTML = recentSessions.map(session => `
        <div class="session-card" onclick="viewSession('${session.session_id}')">
            <div class="session-header">
                <div class="session-title">${session.track_name}</div>
                <div class="session-time"><i class="far fa-calendar-alt"></i> ${formatDateTimeAbbreviated(session.start_time)}</div>
            </div>
            <div class="session-stats">
                <div class="session-stat">
                    <span>Laps</span>
                    <strong>${session.total_laps}</strong>
                </div>
                <div class="session-stat">
                    <span>Best Time</span>
                    <strong>${formatTime(session.best_lap_time)}</strong>
                </div>
                ${session.tbl_improved ? '<span class="badge success"><i class="fas fa-rocket"></i> New TBL!</span>' : ''}
            </div>
        </div>
    `).join('');
}

// ============================================================================
// TRACKS VIEW
// ============================================================================

async function loadTracks() {
    const container = document.getElementById('tracksList');
    container.innerHTML = renderSkeletonCards(4, 'track');

    try {
        const data = await apiCall('/api/tracks');
        tracks = data.tracks || [];

        if (tracks.length === 0) {
            container.innerHTML = renderEmptyState(
                '🗺️',
                'No tracks yet',
                'Process your first session and we\'ll automatically learn the track layout.',
                'Process Files',
                "showView('process')"
            );
            return;
        }

        container.innerHTML = tracks.map(track => {
            const isActive = activeTrackId == track.track_id;
            return `
            <div class="track-card ${isActive ? 'active' : ''}" onclick="viewTrack(${track.track_id})">
                <img src="${API_BASE}/api/tracks/${track.track_id}/map" 
                     alt="${track.track_name}" 
                     class="track-map"
                     onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22300%22 height=%22200%22%3E%3Crect fill=%22%232a2a2a%22 width=%22300%22 height=%22200%22/%3E%3Ctext x=%2250%25%22 y=%2250%25%22 fill=%22%23666%22 text-anchor=%22middle%22%3ENo Map%3C/text%3E%3C/svg%3E'">
                <div class="track-info">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <div class="track-name">${track.track_name}</div>
                        ${isActive ? '<span class="badge success" style="font-size: 0.6rem;">ACTIVE</span>' : ''}
                    </div>
                    <div class="track-meta">
                        <span><i class="fas fa-history"></i> ${track.sessions_count || 0} sessions</span>
                        <span><i class="fas fa-vector-square"></i> 7 sectors</span>
                    </div>
                    <div class="track-actions">
                        ${!isActive ? `
                        <button class="btn btn-primary btn-sm" onclick="event.stopPropagation(); pushTrackToESP(${track.track_id})">
                            <i class="fas fa-bolt"></i> Set Active
                        </button>` : ''}
                        <button class="btn small" onclick="event.stopPropagation(); renameTrack(${track.track_id}, '${track.track_name}')">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-danger btn-sm" onclick="event.stopPropagation(); deleteTrack(${track.track_id}, '${track.track_name}')">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
            `;
        }).join('');
    } catch (error) {
        container.innerHTML = '<p class="help-text">Failed to load tracks</p>';
    }
}

/**
 * Manually trigger pushing a track to the ESP32
 */
async function pushTrackToESP(trackId) {
    const deviceIP = localStorage.getItem('lastDeviceIP');
    if (!deviceIP) {
        showToast('Device not connected', 'error');
        return;
    }

    try {
        showToast('Pushing track data...', 'info');
        await ensureTrackSynced(trackId, deviceIP);
        showToast('Track set as active', 'success');

        // Refresh tracks view to show active state
        loadTracks();
    } catch (err) {
        showToast('Failed to push track', 'error');
    }
}

async function markPitLane(trackId) {
    const deviceIP = localStorage.getItem('lastDeviceIP');
    if (!deviceIP) {
        showToast('Device not connected', 'error');
        return;
    }

    try {
        showToast('Getting GPS from device...', 'info');
        const status = await fetch(`http://${deviceIP}/status`).then(r => r.json());

        if (!status.gps_lat || !status.gps_lon) {
            showToast('No GPS fix on device', 'error');
            return;
        }

        showToast('Saving pit geofence...', 'info');
        // Update track metadata via Pi API
        // Note: Using track_id in the URL, and sending the new fields
        await apiCall(`/api/tracks/${trackId}`, {
            method: 'POST', // The server seems to use POST for updates in some places, or I'll assume it works
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                pit_center_lat: status.gps_lat,
                pit_center_lon: status.gps_lon,
                pit_radius_m: 50
            })
        });

        showToast('Pit Lane marked at current location', 'success');

        // Re-push to ESP32 to sync the new metadata
        await pushTrackToESP(trackId);

    } catch (err) {
        console.error('Mark Pit Error:', err);
        showToast('Failed to mark pit lane', 'error');
    }
}

async function viewTrack(trackId) {
    const container = document.getElementById('trackDetailContent');
    const view = document.getElementById('trackDetailView');

    container.innerHTML = '<div class="loading">Loading track details...</div>';
    view.classList.add('active');
    document.querySelectorAll('.view').forEach(v => {
        if (v !== view) v.classList.remove('active');
    });

    try {
        const track = await apiCall(`/api/tracks/${trackId}`);

        let mapDisplay = '';
        try {
            const geometry = await apiCall(`/api/tracks/${trackId}/geometry`);
            mapDisplay = generateTrackMapSVG(geometry, null, null, { title: '' });
        } catch (e) {
            mapDisplay = `<img src="${API_BASE}/api/tracks/${trackId}/map" 
                 alt="${track.track_name}" 
                 style="width: 100%; max-width: 600px; border-radius: 8px; margin: 1rem 0;"
                 onerror="this.style.display='none'">`;
        }

        const isActive = activeTrackId == trackId;
        container.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <h2>${track.track_name}</h2>
                <div>
                ${isActive ? '<span class="badge success">ACTIVE ON DEVICE</span>' : `
                    <button class="btn btn-primary" onclick="pushTrackToESP(${trackId})">
                        <i class="fas fa-bolt"></i> Set as Active
                    </button>
                `}
                </div>
            </div>
            ${mapDisplay}
            
            <div class="quick-stats">
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-flag-checkered"></i></div>
                    <div class="stat-info">
                        <div class="stat-label">Sessions</div>
                        <div class="stat-value">${track.sessions_count || 0}</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-vector-square"></i></div>
                    <div class="stat-info">
                        <div class="stat-label">Sectors</div>
                        <div class="stat-value">7</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><i class="fas fa-stopwatch"></i></div>
                    <div class="stat-info">
                        <div class="stat-label">Total Best (TBL)</div>
                        <div class="stat-value" style="font-size: 1.5rem;">${track.tbl ? formatTime(track.tbl.total_best_time) : 'N/A'}</div>
                    </div>
                </div>
            </div>
            
            <button class="btn" style="margin-top: 1rem;" onclick="viewTrackSessions(${trackId})">
                View Sessions
            </button>
            <button class="btn btn-secondary" style="margin-top: 1rem; margin-left: 0.5rem;" onclick="markPitLane(${trackId})">
                <i class="fas fa-map-pin"></i> Mark Pit Lane
            </button>
        `;
    } catch (error) {
        container.innerHTML = '<p class="help-text">Failed to load track</p>';
    }
}

function viewTrackSessions(trackId) {
    showView('sessions');
    loadSessions(trackId);
}

// ============================================================================
// SESSIONS VIEW
// ============================================================================

async function loadSessions(filterTrackId = null) {
    const container = document.getElementById('sessionsList');
    const filterSelect = document.getElementById('trackFilter');

    container.innerHTML = renderSkeletonCards(3, 'session');

    try {
        // Load sessions
        const endpoint = filterTrackId ? `/api/sessions?track_id=${filterTrackId}` : '/api/sessions';
        sessions = await apiCall(endpoint);

        // Populate filter dropdown
        if (!filterTrackId) {
            const tracksData = await apiCall('/api/tracks');
            filterSelect.innerHTML = '<option value="">All Tracks</option>' +
                tracksData.tracks.map(t => `<option value="${t.track_id}">${t.track_name}</option>`).join('');

            filterSelect.onchange = (e) => {
                const trackId = e.target.value ? parseInt(e.target.value) : null;
                loadSessions(trackId);
            };
        }

        if (sessions.length === 0) {
            container.innerHTML = renderEmptyState(
                '📊',
                'No sessions yet',
                'Process your first ride data to see your sessions here.',
                'Process Files',
                "showView('process')"
            );
            return;
        }

        // Group by date
        const grouped = groupSessionsByDate(sessions);

        container.innerHTML = Object.entries(grouped).map(([date, dateSessions]) => `
            <h3>${date}</h3>
            ${dateSessions.map(session => `
                <div class="session-card" onclick="viewSession('${session.session_id}')">
                    <div class="session-header">
                        <div class="session-title">${session.track_name}</div>
                        <div class="session-time">${formatTime24h(session.start_time)}</div>
                    </div>
                    <div class="session-stats">
                        <div class="session-stat">
                            <span>Laps:</span>
                            <strong>${session.total_laps}</strong>
                        </div>
                        <div class="session-stat">
                            <span>Best:</span>
                            <strong>${formatTime(session.best_lap_time)}</strong>
                        </div>
                        <div class="session-stat">
                            <span>Duration:</span>
                            <strong>${formatDuration(session.duration_sec)}</strong>
                        </div>
                        ${session.is_public ? '<span class="badge" style="background: var(--primary); color: white;"><i class="fas fa-globe"></i> Public</span>' : ''}
                        ${session.tbl_improved ? '<span class="badge success">New TBL!</span>' : ''}
                    </div>
                </div>
            `).join('')}
        `).join('');

    } catch (error) {
        container.innerHTML = '<p class="help-text">Failed to load sessions</p>';
    }
}

// ============================================================================
// COMMUNITY VIEW
// ============================================================================

async function loadCommunitySessions() {
    const container = document.getElementById('communitySessionsList');
    const filterSelect = document.getElementById('communityTrackFilter');

    container.innerHTML = renderSkeletonCards(3, 'session');

    try {
        const trackId = filterSelect.value ? parseInt(filterSelect.value) : null;
        const endpoint = trackId ? `/api/public/sessions?track_id=${trackId}` : '/api/public/sessions';
        const publicSessions = await apiCall(endpoint);

        // Populate filter dropdown if empty
        if (filterSelect.options.length <= 1) {
            const tracksData = await apiCall('/api/tracks');
            filterSelect.innerHTML = '<option value="">All Tracks</option>' +
                tracksData.tracks.map(t => `<option value="${t.track_id}">${t.track_name}</option>`).join('');
        }

        if (publicSessions.length === 0) {
            container.innerHTML = renderEmptyState(
                '🌍',
                'No public sessions yet',
                'Be the first to share your lap times with the community!',
                'View My Sessions',
                "showView('sessions')"
            );
            return;
        }

        container.innerHTML = publicSessions.map(session => `
            <div class="session-card" onclick="viewSession('${session.session_id}', true)">
                <div class="session-header">
                    <div>
                        <div class="session-title">${session.track_name}</div>
                        <div style="font-size: 0.8rem; color: var(--primary); font-weight: 600; cursor: pointer;" onclick="event.stopPropagation(); showUserProfile(${session.owner_id})">👤 ${session.owner_name}</div>
                    </div>
                    <div class="session-time">${formatDateTimeAbbreviated(session.start_time)}</div>
                </div>
                <div class="session-stats">
                    <div class="session-stat">
                        <span>Laps:</span>
                        <strong>${session.total_laps}</strong>
                    </div>
                    <div class="session-stat">
                        <span>Best:</span>
                        <strong style="color: var(--success);">${formatTime(session.best_lap_time)}</strong>
                    </div>
                    <div class="session-stat">
                        <span>Duration:</span>
                        <strong>${formatDuration(session.duration_sec)}</strong>
                    </div>
                </div>
            </div>
        `).join('');

    } catch (error) {
        container.innerHTML = '<p class="help-text">Failed to load community sessions</p>';
    }
}

// ============================================================================
// PRIVACY & SHARING
// ============================================================================

async function togglePrivacy(sessionId, isPublic) {
    try {
        const result = await apiCall(`/api/sessions/${sessionId}/privacy`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_public: isPublic })
        });

        if (result && result.success) {
            showToast(isPublic ? 'Session is now PUBLIC' : 'Session is now PRIVATE', 'info');
            // Update UI without full reload
            const toggle = document.getElementById('privacyToggle');
            if (toggle) toggle.checked = isPublic;
        }
    } catch (e) {
        showToast('Failed to update privacy: ' + e.message, 'error');
    }
}

async function shareSession(sessionId) {
    try {
        const result = await apiCall(`/api/sessions/${sessionId}/share`, {
            method: 'POST'
        });

        if (result && result.success) {
            const shareUrl = window.location.origin + result.share_url;
            document.getElementById('shareLinkInput').value = shareUrl;
            document.getElementById('shareModal').classList.add('active');
        }
    } catch (e) {
        showToast('Failed to generate share link: ' + e.message, 'error');
    }
}

function closeShareModal() {
    document.getElementById('shareModal').classList.remove('active');
}

function copyShareLink() {
    const input = document.getElementById('shareLinkInput');
    input.select();
    input.setSelectionRange(0, 99999);
    document.execCommand('copy');
    showToast('Link copied to clipboard!', 'success');
}

// ============================================================================
// ACTIONS DROPDOWN (Session Header)
// ============================================================================

function toggleActionsDropdown() {
    const dropdown = document.getElementById('sessionActionsDropdown');
    if (dropdown) {
        dropdown.classList.toggle('open');
        
        // Close when clicking outside
        if (dropdown.classList.contains('open')) {
            setTimeout(() => {
                document.addEventListener('click', closeActionsDropdownOnOutsideClick);
            }, 10);
        }
    }
}

function closeActionsDropdown() {
    const dropdown = document.getElementById('sessionActionsDropdown');
    if (dropdown) {
        dropdown.classList.remove('open');
    }
    document.removeEventListener('click', closeActionsDropdownOnOutsideClick);
}

function closeActionsDropdownOnOutsideClick(e) {
    const dropdown = document.getElementById('sessionActionsDropdown');
    if (dropdown && !dropdown.contains(e.target)) {
        closeActionsDropdown();
    }
}

// ============================================================================
// TRACKDAY FEATURE
// ============================================================================

let currentTaggingSessionId = null;

function switchSessionTab(tab) {
    // Update tab buttons
    document.querySelectorAll('.session-tab').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tab);
    });

    // Show/hide panels
    document.getElementById('sessionsPanel').style.display = tab === 'sessions' ? 'block' : 'none';
    document.getElementById('trackdaysPanel').style.display = tab === 'trackdays' ? 'block' : 'none';

    // Load data
    if (tab === 'trackdays') {
        loadTrackdays();
    }
}

async function loadTrackdays() {
    const container = document.getElementById('trackdaysList');
    container.innerHTML = '<div class="loading">Loading trackdays...</div>';

    try {
        const trackdays = await apiCall('/api/trackdays');

        if (trackdays.length === 0) {
            container.innerHTML = `
                <div style="text-align: center; padding: 3rem; color: var(--text-dim);">
                    <p style="font-size: 1.2rem; margin-bottom: 1rem;">🏁 No trackdays yet</p>
                    <p>Create a trackday to group multiple sessions together</p>
                    <button class="btn btn-primary" style="margin-top: 1rem;" onclick="showCreateTrackdayModal()">+ Create First Trackday</button>
                </div>
            `;
            return;
        }

        container.innerHTML = trackdays.map(td => `
            <div class="trackday-card" onclick="viewTrackday('${td.id}')">
                <div class="trackday-header">
                    <div>
                        <div class="trackday-name">${td.name}</div>
                        <div class="trackday-date">${td.track_name || 'Unknown Track'}</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 0.9rem; color: var(--text-dim);">${formatDate(td.date)}</div>
                        ${td.organizer ? `<div style="font-size: 0.8rem; color: var(--text-dim);">${td.organizer}</div>` : ''}
                        ${td.rider_name ? `<div style="font-size: 0.8rem; color: var(--primary);">👤 ${td.rider_name}</div>` : ''}
                    </div>
                </div>
                <div class="trackday-meta">
                    <div class="trackday-stat">
                        <span>Sessions:</span>
                        <strong>${td.session_count || 0}</strong>
                    </div>
                    <div class="trackday-stat">
                        <span>Total Laps:</span>
                        <strong>${td.total_laps || 0}</strong>
                    </div>
                    <div class="trackday-stat">
                        <span>Best Lap:</span>
                        <strong style="color: var(--success);">${td.best_lap_time ? formatTime(td.best_lap_time) : '--'}</strong>
                    </div>
                </div>
                <button class="btn btn-danger btn-sm" style="margin-top: 0.75rem;" onclick="event.stopPropagation(); deleteTrackday('${td.id}', '${td.name}')">Delete</button>
            </div>
        `).join('');

    } catch (error) {
        container.innerHTML = '<p class="help-text">Failed to load trackdays</p>';
    }
}

function formatDate(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
}

async function showCreateTrackdayModal() {
    const modal = document.getElementById('createTrackdayModal');
    const trackSelect = document.getElementById('tdTrack');

    // Set default date to today
    document.getElementById('tdDate').value = new Date().toISOString().split('T')[0];
    document.getElementById('tdName').value = '';
    document.getElementById('tdRider').value = '';
    document.getElementById('tdOrganizer').value = '';
    document.getElementById('tdNotes').value = '';

    // Load tracks
    try {
        const data = await apiCall('/api/tracks');
        trackSelect.innerHTML = '<option value="">Select Track...</option>' +
            data.tracks.map(t => `<option value="${t.track_id}" data-name="${t.track_name}">${t.track_name}</option>`).join('');
    } catch (e) {
        trackSelect.innerHTML = '<option value="">Failed to load tracks</option>';
    }

    modal.classList.add('active');
}

function closeCreateTrackdayModal() {
    document.getElementById('createTrackdayModal').classList.remove('active');
}

async function submitCreateTrackday() {
    const name = document.getElementById('tdName').value.trim();
    const date = document.getElementById('tdDate').value;
    const organizer = document.getElementById('tdOrganizer').value.trim();
    const rider_name = document.getElementById('tdRider').value.trim();
    const trackSelect = document.getElementById('tdTrack');
    const trackId = trackSelect.value ? parseInt(trackSelect.value) : null;
    const trackName = trackSelect.selectedOptions[0]?.dataset?.name || '';
    const notes = document.getElementById('tdNotes').value.trim();

    if (!name) {
        showToast('Please enter a trackday name', 'error');
        return;
    }

    try {
        await apiCall('/api/trackdays', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, date, organizer, rider_name, track_id: trackId, track_name: trackName, notes })
        });

        closeCreateTrackdayModal();
        showToast('Trackday created', 'success');
        loadTrackdays();
    } catch (error) {
        showToast('Failed to create trackday', 'error');
    }
}

async function deleteTrackday(trackdayId, trackdayName) {
    if (!confirm(`Delete trackday "${trackdayName}"?\n\nThis will NOT delete the sessions, only the trackday grouping.`)) {
        return;
    }

    try {
        await apiCall(`/api/trackdays/${trackdayId}`, { method: 'DELETE' });
        showToast('Trackday deleted', 'success');
        loadTrackdays();
    } catch (error) {
        showToast('Failed to delete trackday', 'error');
    }
}

async function viewTrackday(trackdayId) {
    const view = document.getElementById('trackdayDetailView');
    const container = document.getElementById('trackdayDetailContent');

    // Show the view
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    view.classList.add('active');

    container.innerHTML = '<div class="loading">Loading trackday...</div>';

    try {
        const td = await apiCall(`/api/trackdays/${trackdayId}`);

        const sectorCount = td.sector_count || 3;

        container.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1.5rem;">
                <div>
                    <h2 style="margin-bottom: 0.25rem;">${td.name}</h2>
                    <p class="help-text" style="margin: 0;">${td.track_name || 'Unknown Track'} • ${formatDate(td.date)}</p>
                    ${td.organizer ? `<p class="help-text" style="margin: 0.25rem 0 0 0;">Organizer: ${td.organizer}</p>` : ''}
                    ${td.rider_name ? `<p class="help-text" style="margin: 0.25rem 0 0 0; color: var(--primary);">👤 Rider: ${td.rider_name}</p>` : ''}
                </div>
                <div class="no-print">
                    <button class="btn btn-secondary btn-sm" onclick="window.print()" style="margin-right: 0.5rem;">🖨️ Print Report</button>
                    <button class="btn btn-secondary btn-sm" onclick="showTagSessionModal('${trackdayId}')">+ Add Session</button>
                </div>
            </div>
            
            <!-- Summary Stats -->
            <div class="quick-stats" style="margin-bottom: 1.5rem;">
                <div class="stat-card">
                    <div class="stat-icon" style="background: rgba(255, 107, 53, 0.1); color: var(--primary);"><i class="fas fa-flag-checkered"></i></div>
                    <div class="stat-info">
                        <div class="stat-label">Sessions</div>
                        <div class="stat-value">${td.summary.total_sessions}</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon" style="background: rgba(0, 78, 137, 0.1); color: var(--secondary);"><i class="fas fa-redo"></i></div>
                    <div class="stat-info">
                        <div class="stat-label">Total Laps</div>
                        <div class="stat-value">${td.summary.total_laps}</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon" style="background: rgba(0, 210, 106, 0.1); color: var(--success);"><i class="fas fa-trophy"></i></div>
                    <div class="stat-info">
                        <div class="stat-label">Best Lap</div>
                        <div class="stat-value" style="color: var(--success);">${td.summary.best_lap_time ? formatTime(td.summary.best_lap_time) : '--'}</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon" style="background: rgba(255, 193, 7, 0.1); color: #FFC107;"><i class="fas fa-clock"></i></div>
                    <div class="stat-info">
                        <div class="stat-label">Total Time</div>
                        <div class="stat-value">${Math.floor(td.summary.total_duration / 60)}m</div>
                    </div>
                </div>
            </div>
            
            <!-- Track Layout -->
            ${td.track_id ? `
            <div class="card" style="margin-bottom: 1.5rem;">
                <h3 style="margin: 0 0 1rem 0; display: flex; align-items: center; gap: 0.5rem;">
                    <span style="color: var(--primary);">🗺️</span> Track Layout
                    <span style="font-size: 0.8rem; font-weight: normal; color: var(--text-dim);">${td.sector_count || 0} sectors</span>
                </h3>
                <div id="trackdayMapContainer" style="text-align: center; min-height: 200px;">
                    <div class="loading">Loading track map...</div>
                </div>
            </div>
            ` : ''}
            
            ${td.notes ? `
            <div class="card" style="margin-bottom: 1.5rem;">
                <h4 style="margin: 0 0 0.5rem 0;">Notes</h4>
                <p style="margin: 0; white-space: pre-wrap;">${td.notes}</p>
            </div>
            ` : ''}

            <!-- Trackday Leaderboard (Phase 4) -->
            <div class="card" style="margin-bottom: 1.5rem;">
                <h3 style="margin: 0 0 1rem 0; display: flex; align-items: center; gap: 0.5rem;">
                    <span style="color: var(--primary);">🥇</span> Trackday Leaderboard
                    <span style="font-size: 0.8rem; font-weight: normal; color: var(--text-dim);">Public times for this track & date</span>
                </h3>
                <div id="trackdayLeaderboardContent">
                    <div class="loading">Loading leaderboard...</div>
                </div>
            </div>
            
            <!-- Sessions in Trackday (Collapsible) -->
            <div class="card" style="margin-bottom: 1.5rem;">
                <h3 style="margin: 0; display: flex; align-items: center; justify-content: space-between; cursor: pointer;" onclick="toggleSessionsList()">
                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                        <span style="color: var(--primary);">📋</span> Sessions (${td.sessions.length})
                    </div>
                    <span id="sessionsToggleIcon" style="font-size: 0.8rem; color: var(--text-dim);">▼</span>
                </h3>
                <div id="sessionsListContent" style="margin-top: 1rem;">
                ${td.sessions.length === 0 ? '<p class="help-text">No sessions added yet. Click "+ Add Session" to tag sessions to this trackday.</p>' : `
                <div class="sessions-list">
                    ${td.sessions.map(s => {
            // Calculate consistency (std dev of lap times within session)
            const sessionLaps = td.laps.filter(l => l.session_id === s.session_id);
            let consistencyText = '--';
            if (sessionLaps.length > 1) {
                const times = sessionLaps.map(l => l.lap_time).filter(t => t > 0);
                if (times.length > 1) {
                    const mean = times.reduce((a, b) => a + b, 0) / times.length;
                    const variance = times.reduce((a, t) => a + Math.pow(t - mean, 2), 0) / times.length;
                    const stdDev = Math.sqrt(variance);
                    consistencyText = formatTime(stdDev) + ' σ';
                }
            }
            return `
                        <div class="session-card" style="cursor: default; display: flex; justify-content: space-between; align-items: center;">
                            <div onclick="viewSession('${s.session_id}')" style="cursor: pointer; flex: 1;">
                                <div class="session-title">${s.session_name}</div>
                                <div class="session-stats">
                                    <div class="session-stat"><span>Laps:</span><strong>${s.total_laps}</strong></div>
                                    <div class="session-stat"><span>Best:</span><strong>${formatTime(s.best_lap_time)}</strong></div>
                                    <div class="session-stat"><span>Consistency:</span><strong style="color: var(--text-dim);">${consistencyText}</strong></div>
                                </div>
                            </div>
                            <button class="btn btn-danger btn-sm" onclick="untagSession('${trackdayId}', '${s.session_id}')">Remove</button>
                        </div>
                    `;
        }).join('')}
                </div>
                `}
                </div>
            </div>
            
            <!-- Theoretical Best Lap Card -->
            ${td.tbl ? `
            <div class="card" style="margin-bottom: 1.5rem; border-left: 4px solid var(--success);">
                <h3 style="margin: 0 0 1rem 0; display: flex; align-items: center; gap: 0.5rem;">
                    <span style="color: var(--success);">⚡</span> Theoretical Best Lap
                </h3>
                <div style="display: flex; gap: 2rem; flex-wrap: wrap; align-items: center;">
                    <div>
                        <div style="font-size: 2rem; font-weight: bold; color: var(--success);">${formatTime(td.tbl.total)}</div>
                        <div class="help-text" style="margin-top: 0.25rem;">Combined best sectors</div>
                    </div>
                    <div style="flex: 1; min-width: 300px;">
                        <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                            ${(td.tbl.sectors || []).map((s, i) => `
                                <div style="background: var(--surface); padding: 0.5rem 1rem; border-radius: 4px; text-align: center;">
                                    <div style="font-size: 0.8rem; color: var(--text-dim);">S${i + 1}</div>
                                    <div style="font-family: monospace; font-weight: bold;">${formatTime(s)}</div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            </div>
            ` : ''}
            
            <!-- Best Actual Lap Card -->
            ${(() => {
                const bestLap = td.laps.find(l => l.lap_time === td.summary.best_lap_time);
                if (!bestLap) return '';
                return `
                <div class="card" style="margin-bottom: 1.5rem; border-left: 4px solid var(--primary);">
                    <h3 style="margin: 0 0 1rem 0; display: flex; align-items: center; gap: 0.5rem;">
                        <span style="color: var(--primary);">🏆</span> Best Actual Lap
                    </h3>
                    <div style="display: flex; gap: 2rem; flex-wrap: wrap; align-items: center;">
                        <div>
                            <div style="font-size: 2rem; font-weight: bold; color: var(--primary);">${formatTime(bestLap.lap_time)}</div>
                            <div class="help-text" style="margin-top: 0.25rem;">${bestLap.session_name} • Lap ${bestLap.lap_number}</div>
                        </div>
                        <div style="flex: 1; min-width: 300px;">
                            <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
                                ${(bestLap.sector_times || []).map((s, i) => `
                                    <div style="background: var(--surface); padding: 0.5rem 1rem; border-radius: 4px; text-align: center;">
                                        <div style="font-size: 0.8rem; color: var(--text-dim);">S${i + 1}</div>
                                        <div style="font-family: monospace; font-weight: bold;">${formatTime(s)}</div>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    </div>
                </div>
                `;
            })()}
            
            <!-- All Laps By Session -->
            <div class="card" style="margin-bottom: 1.5rem;">
                <h3 style="margin: 0 0 1rem 0; display: flex; align-items: center; gap: 0.5rem;">
                    <span style="color: var(--primary);">📊</span> All Laps (Grouped by Session)
                </h3>
                <div style="overflow-x: auto;">
                    ${td.sessions.map(session => {
                const sessionLaps = td.laps
                    .filter(l => l.session_id === session.session_id)
                    .sort((a, b) => (a.lap_time || 999) - (b.lap_time || 999));
                if (sessionLaps.length === 0) return '';

                const bestLapTime = Math.min(...sessionLaps.map(l => l.lap_time || 999));

                return `
                        <div style="margin-bottom: 1.5rem;">
                            <h4 style="margin: 0 0 0.75rem 0; padding: 0.5rem; background: var(--surface-alt); border-radius: 4px; display: flex; justify-content: space-between; align-items: center;">
                                <span>${session.session_name}</span>
                                <span style="font-size: 0.85rem; color: var(--text-dim);">${sessionLaps.length} laps • Best: <strong style="color: var(--success);">${formatTime(bestLapTime)}</strong></span>
                            </h4>
                            <table class="modern-table" style="width: 100%; min-width: 600px;">
                                <thead>
                                    <tr>
                                        <th style="width: 60px;">#</th>
                                        <th>Lap</th>
                                        <th>Time</th>
                                        ${Array(sectorCount).fill(0).map((_, i) => `<th style="text-align: center;">S${i + 1}</th>`).join('')}
                                        <th style="width: 80px;"></th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${sessionLaps.map((lap, idx) => `
                                        <tr class="lap-row ${lap.lap_time === bestLapTime ? 'best-lap' : ''}">
                                            <td class="lap-number">${idx + 1}</td>
                                            <td>L${lap.lap_number}</td>
                                            <td class="lap-time">${formatTime(lap.lap_time)}</td>
                                            ${(lap.sector_times || []).map(t => `
                                                <td style="text-align: center; font-family: monospace; font-size: 0.85rem;">${formatTime(t)}</td>
                                            `).join('')}
                                            <td style="text-align: center;">
                                                ${lap.lap_time === bestLapTime ? '<span class="best-badge">★ BEST</span>' : ''}
                                            </td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    `;
            }).join('')}
                </div>
            </div>
        `;

        // Load track map asynchronously with SVG visualization
        if (td.track_id) {
            loadTrackdayMap(td.track_id, td.track_name);
        }

        // Load Trackday Leaderboard (Phase 4)
        loadTrackdayLeaderboard(trackdayId);

    } catch (error) {
        container.innerHTML = '<p class="help-text">Failed to load trackday</p>';
    }
}

async function loadTrackdayMap(trackId, trackName) {
    const mapContainer = document.getElementById('trackdayMapContainer');
    if (!mapContainer) return;

    try {
        const geometry = await apiCall(`/api/tracks/${trackId}/geometry`);
        mapContainer.innerHTML = generateTrackMapSVG(geometry, null, null, { title: '' });
    } catch (e) {
        // Fallback to static image
        mapContainer.innerHTML = `
            <img src="/api/tracks/${trackId}/map" 
                 alt="${trackName} Track Map" 
                 style="max-width: 100%; max-height: 400px; border-radius: 8px; background: var(--surface);"
                 onerror="this.parentElement.innerHTML='<p class=\\'help-text\\'>Track map not available</p>'">
        `;
    }
}

function toggleSessionsList() {
    const content = document.getElementById('sessionsListContent');
    const icon = document.getElementById('sessionsToggleIcon');
    if (content && icon) {
        if (content.style.display === 'none') {
            content.style.display = 'block';
            icon.textContent = '▼';
        } else {
            content.style.display = 'none';
            icon.textContent = '▶';
        }
    }
}

// Tag session to trackday
async function showTagToTrackdayModal(sessionId) {
    currentTaggingSessionId = sessionId;
    const modal = document.getElementById('tagTrackdayModal');
    const container = document.getElementById('tagTrackdayList');

    container.innerHTML = '<div class="loading">Loading trackdays...</div>';
    modal.classList.add('active');

    try {
        const trackdays = await apiCall('/api/trackdays');

        if (trackdays.length === 0) {
            container.innerHTML = `
                <p class="help-text">No trackdays found. Create one first.</p>
                <button class="btn btn-primary btn-sm" onclick="closeTagTrackdayModal(); showCreateTrackdayModal();">Create Trackday</button>
            `;
            return;
        }

        container.innerHTML = trackdays.map(td => `
            <div class="trackday-card" style="padding: 0.75rem;" onclick="tagSessionToTrackday('${td.id}')">
                <div style="font-weight: 600;">${td.name}</div>
                <div style="font-size: 0.85rem; color: var(--text-dim);">${td.track_name} • ${formatDate(td.date)}</div>
            </div>
        `).join('');

    } catch (error) {
        container.innerHTML = '<p class="help-text">Failed to load trackdays</p>';
    }
}

function closeTagTrackdayModal() {
    document.getElementById('tagTrackdayModal').classList.remove('active');
    currentTaggingSessionId = null;
}

async function tagSessionToTrackday(trackdayId) {
    if (!currentTaggingSessionId) return;

    try {
        await apiCall(`/api/trackdays/${trackdayId}/sessions/${currentTaggingSessionId}`, { method: 'POST' });
        closeTagTrackdayModal();
        showToast('Session added to trackday', 'success');
    } catch (error) {
        showToast('Failed to add session to trackday', 'error');
    }
}

async function untagSession(trackdayId, sessionId) {
    if (!confirm('Remove this session from the trackday?')) return;

    try {
        await apiCall(`/api/trackdays/${trackdayId}/sessions/${sessionId}`, { method: 'DELETE' });
        showToast('Session removed from trackday', 'success');
        viewTrackday(trackdayId); // Refresh
    } catch (error) {
        showToast('Failed to remove session', 'error');
    }
}

// For adding session from trackday detail view - with multi-select
async function showTagSessionModal(trackdayId) {
    // Show modal to select from available sessions
    const modal = document.getElementById('tagTrackdayModal');
    const container = document.getElementById('tagTrackdayList');

    container.innerHTML = renderSkeletonCards(3, 'session');
    modal.classList.add('active');

    // Store trackday ID for the bulk add
    window.currentTagTrackdayId = trackdayId;

    try {
        const [sessions, trackday] = await Promise.all([
            apiCall('/api/sessions'),
            apiCall(`/api/trackdays/${trackdayId}`)
        ]);

        // Get already added session IDs
        const existingSessions = new Set(trackday.session_ids || []);

        container.innerHTML = `
            <p class="help-text" style="margin-bottom: 1rem;">Select sessions to add (multi-select):</p>
            <div style="margin-bottom: 1rem;">
                <button class="btn btn-primary btn-sm" id="btnAddSelectedSessions" onclick="addSelectedSessions()" disabled>
                    Add Selected (0)
                </button>
            </div>
            <div class="sessions-list" style="max-height: 400px; overflow-y: auto;">
                ${sessions.map(s => {
            const alreadyAdded = existingSessions.has(s.session_id);
            return `
                    <label class="session-card" style="padding: 0.75rem; margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.75rem; cursor: ${alreadyAdded ? 'not-allowed' : 'pointer'}; opacity: ${alreadyAdded ? '0.5' : '1'};">
                        <input type="checkbox" class="session-select-cb" value="${s.session_id}" 
                               ${alreadyAdded ? 'disabled' : ''} 
                               onchange="updateSessionSelectCount()">
                        <div style="flex: 1;">
                            <div style="font-weight: 600;">${s.session_name || s.track_name}</div>
                            <div style="font-size: 0.85rem; color: var(--text-dim);">
                                ${formatTime24h(s.start_time)} • ${s.total_laps} laps • Best: ${formatTime(s.best_lap_time)}
                                ${alreadyAdded ? '<span style="color: var(--success);"> ✓ Added</span>' : ''}
                            </div>
                        </div>
                    </label>
                `;
        }).join('')}
            </div>
        `;

    } catch (error) {
        container.innerHTML = '<p class="help-text">Failed to load sessions</p>';
    }
}

function updateSessionSelectCount() {
    const checked = document.querySelectorAll('.session-select-cb:checked').length;
    const btn = document.getElementById('btnAddSelectedSessions');
    if (btn) {
        btn.textContent = `Add Selected (${checked})`;
        btn.disabled = checked === 0;
    }
}

async function addSelectedSessions() {
    const trackdayId = window.currentTagTrackdayId;
    const selectedSessions = Array.from(document.querySelectorAll('.session-select-cb:checked')).map(cb => cb.value);

    if (selectedSessions.length === 0) {
        showToast('No sessions selected', 'info');
        return;
    }

    showToast(`Adding ${selectedSessions.length} session(s)...`, 'info');

    let successCount = 0;
    let failCount = 0;

    for (const sessionId of selectedSessions) {
        try {
            await apiCall(`/api/trackdays/${trackdayId}/sessions/${sessionId}`, { method: 'POST' });
            successCount++;
        } catch (error) {
            failCount++;
        }
    }

    closeTagTrackdayModal();

    if (successCount > 0) {
        showToast(`Added ${successCount} session(s)`, 'success');
    }
    if (failCount > 0) {
        showToast(`Failed to add ${failCount} session(s)`, 'warning');
    }

    viewTrackday(trackdayId);
}

async function tagToTrackdayFromDetail(trackdayId, sessionId) {
    try {
        await apiCall(`/api/trackdays/${trackdayId}/sessions/${sessionId}`, { method: 'POST' });
        closeTagTrackdayModal();
        showToast('Session added', 'success');
        viewTrackday(trackdayId);
    } catch (error) {
        showToast('Failed to add session', 'error');
    }
}

async function exportSession(sessionId) {
    if (!currentUser || currentUser.subscription_tier === 'free') {
        showUpgradeModal("Export");
        return;
    }

    // Use window.open or fetch with blob if we need auth headers
    // Since our API uses cookies for JWT, window.open should work if the cookie is set
    window.open(`${API_BASE}/api/sessions/${sessionId}/export`);
}

async function viewSession(sessionId, isPublicView = false, shareToken = null) {
    const container = document.getElementById('sessionDetailContent');
    const view = document.getElementById('sessionDetailView');

    container.innerHTML = '<div class="loading">Loading session...</div>';
    view.classList.add('active');
    document.querySelectorAll('.view').forEach(v => {
        if (v !== view) v.classList.remove('active');
    });

    try {
        let endpoint = isPublicView ? `/api/sessions/${sessionId}` : `/api/sessions/${sessionId}`;
        if (shareToken) {
            endpoint = `/api/shared/${shareToken}`;
        }

        // If it's a public view from community, we still use the main session endpoint but might need to adjust auth
        // Actually, the API I wrote for /api/public/sessions returns enough info to identify it.
        // But for details, we need the full session.

        const session = await apiCall(endpoint);
        const isShared = session.is_shared_view || isPublicView;

        // Phase 7.1 Calculations
        const validLapsTimes = session.laps.filter(l => l.valid && l.lap_time > 0).map(l => l.lap_time);
        const consistency = calculateStandardDeviation(validLapsTimes);

        const sectorCount = session.track.sector_count;
        const sectorMedians = [];
        for (let i = 0; i < sectorCount; i++) {
            const times = session.laps.map(l => l.sector_times[i]).filter(t => t > 0);
            sectorMedians.push(calculateMedian(times));
        }

        // Get all-time best for this track (from track data)
        let allTimeBest = null;
        if (!isShared) {
            try {
                const trackData = await apiCall(`/api/tracks/${session.track.track_id}`);
                if (trackData && trackData.best_lap_time) {
                    allTimeBest = trackData.best_lap_time;
                }
            } catch (e) { console.log("Track PB not available"); }
        }

        // Generate sector comparison data
        const sectorBests = [];
        for (let i = 0; i < sectorCount; i++) {
            const times = session.laps.map(l => l.sector_times[i]).filter(t => t > 0);
            sectorBests.push(times.length ? Math.min(...times) : 0);
        }

        // Build telemetry info (IMU + Consistency consolidated)
        const imuStatus = session.calibration?.calibrated 
            ? (session.calibration.confidence === 'HIGH' ? 'green' : 'orange')
            : 'gray';
        const imuLabel = session.calibration?.calibrated 
            ? `IMU: ${session.calibration.confidence}`
            : 'IMU: RAW';

        container.innerHTML = `
            ${isShared ? `
                <div class="shared-session-banner">
                    <div class="rider-info">
                        <div class="rider-avatar">${(session.owner_name || 'A').charAt(0).toUpperCase()}</div>
                        <div>
                            <div class="rider-name" onclick="showUserProfile(${session.user_id})">${session.owner_name || 'Anonymous'}</div>
                            <div class="shared-label">Viewing shared session</div>
                        </div>
                    </div>
                    ${!currentUser ? `
                        <button class="btn btn-primary btn-sm" onclick="showAuthModal()">Sign up to track your laps</button>
                    ` : ''}
                </div>
            ` : `
                <a href="#" class="session-back-link no-print" onclick="showView('sessions'); return false;">
                    <i class="fas fa-arrow-left"></i> Back to Sessions
                </a>
            `}

            <!-- PREMIUM SESSION HEADER -->
            <div class="session-header-premium">
                <div class="session-title-block">
                    <h2 class="session-title">
                        ${session.meta.session_name || session.track.track_name + ' Session'}
                        ${!isShared ? `<button class="btn-icon no-print" onclick="promptRenameSession('${session.meta.session_id}', '${session.meta.session_name || ''}')" title="Rename Session" style="opacity: 0.5; font-size: 0.9rem;">✎</button>` : ''}
                    </h2>
                    <div class="session-meta-row">
                        <span class="meta-item"><i class="far fa-calendar"></i> ${formatDateTime(session.meta.start_time)}</span>
                        <span class="meta-item"><i class="fas fa-road"></i> ${session.track.track_name}</span>
                        <span class="meta-item"><i class="far fa-clock"></i> ${Math.floor(session.meta.duration_sec / 60)}m</span>
                    </div>
                    
                    <!-- Consolidated Telemetry Info Row -->
                    <div class="telemetry-info-row no-print">
                        <span class="telemetry-item" title="Standard Deviation of valid laps">
                            <i class="fas fa-chart-line"></i> Consistency: <strong>±${consistency.toFixed(2)}s</strong>
                        </span>
                        <span class="divider"></span>
                        <span class="telemetry-item" title="${session.calibration?.calibrated ? 'Gravity Aligned' : 'Uncalibrated IMU'}">
                            <span class="dot ${imuStatus}"></span> ${imuLabel}
                        </span>
                    </div>
                </div>

                <div class="session-actions no-print">
                    <!-- Primary Action: Live Playback -->
                    <button class="btn-playback" onclick="openPlayback('${session.meta.session_id}', ${isShared ? `'${shareToken}'` : 'null'})">
                        <i class="fas fa-play"></i> Playback
                    </button>

                    ${!isShared ? `
                    <!-- Public Toggle (Premium style) -->
                    <div class="privacy-toggle-premium ${session.is_public ? 'is-public' : ''}" title="${session.is_public ? 'Session is public' : 'Session is private'}">
                        <i class="fas ${session.is_public ? 'fa-globe' : 'fa-lock'}"></i>
                        <span>${session.is_public ? 'Public' : 'Private'}</span>
                        <label class="toggle-switch">
                            <input type="checkbox" id="privacyToggle" ${session.is_public ? 'checked' : ''} onchange="togglePrivacy('${session.meta.session_id}', this.checked); this.closest('.privacy-toggle-premium').classList.toggle('is-public', this.checked); this.closest('.privacy-toggle-premium').querySelector('span').textContent = this.checked ? 'Public' : 'Private'; this.closest('.privacy-toggle-premium').querySelector('i').className = 'fas ' + (this.checked ? 'fa-globe' : 'fa-lock');">
                            <span class="toggle-slider"></span>
                        </label>
                    </div>

                    <!-- Actions Dropdown -->
                    <div class="actions-dropdown" id="sessionActionsDropdown">
                        <button class="actions-dropdown-btn" onclick="toggleActionsDropdown()">
                            <i class="fas fa-ellipsis-h"></i> More <i class="fas fa-chevron-down"></i>
                        </button>
                        <div class="actions-dropdown-menu">
                            <button class="dropdown-item" onclick="shareSession('${session.meta.session_id}'); closeActionsDropdown();">
                                <i class="fas fa-share-alt"></i> Share Link
                            </button>
                            <button class="dropdown-item" onclick="showTagToTrackdayModal('${session.meta.session_id}'); closeActionsDropdown();">
                                <i class="fas fa-tag"></i> Tag to Trackday
                            </button>
                            <button class="dropdown-item ${(!currentUser || currentUser.subscription_tier === 'free') ? 'disabled' : ''}" 
                                    onclick="${(!currentUser || currentUser.subscription_tier === 'free') ? '' : `exportSession('${session.meta.session_id}'); closeActionsDropdown();`}"
                                    ${(!currentUser || currentUser.subscription_tier === 'free') ? 'title="Upgrade to Pro"' : ''}>
                                <i class="fas fa-file-archive"></i> Export ZIP ${(!currentUser || currentUser.subscription_tier === 'free') ? '🔒' : ''}
                            </button>
                            <button class="dropdown-item" onclick="window.print(); closeActionsDropdown();">
                                <i class="fas fa-print"></i> Print Report
                            </button>
                            <div class="dropdown-divider"></div>
                            <button class="dropdown-item danger" onclick="deleteSession('${session.meta.session_id}')">
                                <i class="fas fa-trash"></i> Delete Session
                            </button>
                        </div>
                    </div>
                    ` : ''}
                </div>
            </div>
            
            <!-- SESSION SUMMARY CARDS -->
            <div class="quick-stats" style="margin-bottom: 1.5rem;">
                <div class="stat-card">
                    <div class="stat-icon" style="background: rgba(255, 107, 53, 0.1); color: var(--primary);"><i class="fas fa-redo"></i></div>
                    <div class="stat-info">
                        <div class="stat-label">Total Laps</div>
                        <div class="stat-value">${session.summary.total_laps}</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon" style="background: rgba(0, 210, 106, 0.1); color: var(--success);"><i class="fas fa-stopwatch"></i></div>
                    <div class="stat-info">
                        <div class="stat-label">Session Best</div>
                        <div class="stat-value lap-time-display" style="color: var(--success);">${formatTime(session.summary.best_lap_time)}</div>
                    </div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon" style="background: rgba(0, 78, 137, 0.1); color: var(--secondary);"><i class="fas fa-magic"></i></div>
                    <div class="stat-info">
                        <div class="stat-label">Theo. Best</div>
                        <div class="stat-value lap-time-display">${formatTime(session.references.theoretical_best_reference)}</div>
                    </div>
                </div>
                ${allTimeBest ? `
                <div class="stat-card">
                    <div class="stat-icon" style="background: rgba(156, 39, 176, 0.1); color: #9c27b0;"><i class="fas fa-crown"></i></div>
                    <div class="stat-info">
                        <div class="stat-label">All-Time PB</div>
                        <div class="stat-value lap-time-display" style="color: #9c27b0;">${formatTime(allTimeBest)}</div>
                        ${session.summary.best_lap_time <= allTimeBest ? '<div style="color: #4CAF50; font-size: 0.7rem; font-weight: 700;">🏆 NEW PB!</div>' : ''}
                    </div>
                </div>
                ` : ''}
                <div class="stat-card">
                    <div class="stat-icon" style="background: ${session.analysis?.diagnostics?.consistency_score > 80 ? 'rgba(76, 175, 80, 0.1)' : 'rgba(255, 193, 7, 0.1)'}; color: ${session.analysis?.diagnostics?.consistency_score > 80 ? '#4CAF50' : '#FFC107'};">
                        <i class="fas fa-chart-line"></i>
                    </div>
                    <div class="stat-info">
                        <div class="stat-label">Consistency</div>
                        <div class="stat-value">${session.analysis?.diagnostics?.consistency_score || '--'}%</div>
                    </div>
                </div>
            </div>

            <!-- SECTION: SESSION CONTEXT (Environment, Notes, Diagnostics) -->
            <div id="sectionContext" class="details-section collapsed">
                <div class="details-section-header" onclick="toggleDetailsSection('sectionContext')">
                    <h3><i class="fas fa-info-circle" style="color: var(--secondary);"></i> Session Context & Health</h3>
                    <i class="fas fa-chevron-down chevron-icon"></i>
                </div>
                <div class="details-section-content">
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 1.5rem;">
                        <div class="card" style="display: flex; align-items: center; gap: 0.75rem; padding: 1rem;">
                            <span style="font-size: 1.5rem;">🌡️</span>
                            <div>
                                <div style="font-size: 0.75rem; color: var(--text-dim); text-transform: uppercase;">Track Temp</div>
                                <div style="font-weight: 600;">${session.environment?.track_temperature ? session.environment.track_temperature + '°C' : '--'}</div>
                            </div>
                        </div>
                        <div class="card" style="display: flex; align-items: center; gap: 0.75rem; padding: 1rem;">
                            <span style="font-size: 1.5rem;">☁️</span>
                            <div>
                                <div style="font-size: 0.75rem; color: var(--text-dim); text-transform: uppercase;">Ambient</div>
                                <div style="font-weight: 600;">${session.environment?.ambient_temperature ? session.environment.ambient_temperature + '°C' : '--'}</div>
                            </div>
                        </div>
                        <div class="card" style="display: flex; align-items: center; gap: 0.75rem; padding: 1rem;">
                            <span style="font-size: 1.5rem;">📡</span>
                            <div>
                                <div style="font-size: 0.75rem; color: var(--text-dim); text-transform: uppercase;">GPS Quality</div>
                                <div style="font-weight: 600;">${session.environment?.gps_quality_summary?.fix_dropouts === 0 ? '✓ Excellent' : session.environment?.gps_quality_summary?.fix_dropouts + ' dropouts'}</div>
                            </div>
                        </div>
                        <div class="card" style="display: flex; align-items: center; gap: 0.75rem; padding: 1rem;">
                            <span style="font-size: 1.5rem;">⏱️</span>
                            <div>
                                <div style="font-size: 0.75rem; color: var(--text-dim); text-transform: uppercase;">Duration</div>
                                <div style="font-weight: 600;">${Math.floor(session.meta.duration_sec / 60)}m ${Math.floor(session.meta.duration_sec % 60)}s</div>
                            </div>
                        </div>
                    </div>

                    <div style="margin-bottom: 1.5rem;">
                        <h4 style="margin: 0 0 0.75rem 0; font-size: 0.9rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px;">Session Notes</h4>
                        <textarea 
                            id="sessionNotes" 
                            ${isShared ? 'readonly' : ''}
                            placeholder="${isShared ? 'No notes available.' : 'Add notes about this session (e.g., tire pressure, setup changes, conditions)...'}"
                            style="width: 100%; min-height: 80px; background: var(--surface-light); border: 1px solid var(--border); border-radius: 6px; padding: 0.75rem; color: var(--text); resize: vertical; font-family: inherit;"
                            onblur="saveSessionNotes('${session.meta.session_id}')"
                        >${session.mode?.notes || ''}</textarea>
                    </div>

                    <div>
                        <h4 style="margin: 0 0 0.75rem 0; font-size: 0.9rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px;">Technical Diagnostics</h4>
                        ${generateDiagnosticsPanelFixed(session)}
                    </div>
                </div>
            </div>

            <!-- SECTION: LAP ANALYSIS (Main Table) -->
            <div id="sectionLaps" class="details-section">
                <div class="details-section-header" onclick="toggleDetailsSection('sectionLaps')">
                    <h3><i class="fas fa-stopwatch" style="color: var(--success);"></i> Lap Analysis</h3>
                    <i class="fas fa-chevron-down chevron-icon"></i>
                </div>
                <div class="details-section-content">
                    <div style="overflow-x: auto;">
                        <table class="modern-table" style="width: 100%; border-collapse: collapse; min-width: 600px;">
                            <thead>
                                <tr>
                                    <th style="width: 60px;">Lap</th>
                                    <th>Time</th>
                                    <th>Delta</th>
                                    ${session.analysis?.metrics ? '<th style="text-align: center;">Stability</th><th style="text-align: center;">Lat Load</th>' : ''}
                                    ${Array(sectorCount).fill(0).map((_, i) => `<th style="text-align: center;">S${i + 1}</th>`).join('')}
                                    <th style="width: 60px;"></th>
                                </tr>
                            </thead>
                            <tbody>
                                ${session.laps.map(lap => {
            const m = session.analysis?.metrics?.laps?.find(x => x && x.lap_number === lap.lap_number);
            const stab = m?.scores?.stability_score;
            const load = m?.scores?.lateral_load_score;

            const stabColor = stab > 80 ? '#4CAF50' : (stab > 50 ? '#FF9800' : '#F44336');
            const isBest = lap.is_session_best;

            return `
                                    <tr onclick="viewLapDetail('${session.meta.session_id}', ${lap.lap_number}, ${isShared ? `'${shareToken}'` : 'null'})" class="lap-row ${isBest ? 'best-lap' : ''}" title="Click for Detailed Analysis">
                                        <td class="lap-number">
                                            ${lap.lap_number}
                                        </td>
                                        <td class="lap-time">${formatTime(lap.lap_time)}</td>
                                        <td class="lap-delta ${lap.delta_to_reference > 0 ? 'slower' : 'faster'}">
                                            ${lap.delta_to_reference > 0 ? '+' : ''}${lap.delta_to_reference.toFixed(3)}
                                        </td>
                                        ${session.analysis?.metrics ? `
                                            <td style="text-align: center;">
                                                ${stab ? `<span class="score-pill" style="background: ${stabColor}22; color: ${stabColor};">${stab}%</span>` : '-'}
                                            </td>
                                            <td style="text-align: center;">
                                                ${load ? `<span class="score-pill">${load}%</span>` : '-'}
                                            </td>
                                        ` : ''}
                                        ${lap.sector_times.map((t, i) => `
                                            <td class="${getHeatmapClass(t, sectorMedians[i])}" style="text-align: center; font-family: monospace;">${formatTime(t)}</td>
                                        `).join('')}
                                        <td style="text-align: center;">
                                            ${isBest ? '<span class="best-badge">★ BEST</span>' : ''}
                                            <button class="btn-icon no-print" onclick="event.stopPropagation(); setForComparison('${session.meta.session_id}', ${lap.lap_number})" title="Add to Compare">⚖️</button>
                                            <button class="btn-icon no-print" onclick="event.stopPropagation(); showAddAnnotationModalWithLap('${session.meta.session_id}', ${lap.lap_number})" title="Add Note">📝</button>
                                        </td>
                                    </tr>
                                `}).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            
            <div id="comparisonContainer"></div>

            <!-- SECTION: VISUAL INSIGHTS (Charts) -->
            <div id="sectionVisuals" class="details-section collapsed">
                <div class="details-section-header" onclick="toggleDetailsSection('sectionVisuals')">
                    <h3><i class="fas fa-chart-area" style="color: var(--primary);"></i> Visual Insights</h3>
                    <i class="fas fa-chevron-down chevron-icon"></i>
                </div>
                <div class="details-section-content">
                    <div style="margin-bottom: 2rem;">
                        <h4 style="margin: 0 0 1rem 0; font-size: 0.9rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px;">Sector Comparison</h4>
                        ${generateSectorComparisonChart(session.laps, sectorCount, sectorBests)}
                    </div>
                    <div>
                        <h4 style="margin: 0 0 1rem 0; font-size: 0.9rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px;">Session Timeline</h4>
                        ${generateTimelineSVG(session.laps)}
                    </div>
                </div>
            </div>

            <!-- SECTION: COACH'S CORNER (Annotations) -->
            <div id="sectionCoach" class="details-section">
                <div class="details-section-header" onclick="toggleDetailsSection('sectionCoach')">
                    <h3><i class="fas fa-user-graduate" style="color: #9c27b0;"></i> Coach's Corner</h3>
                    <i class="fas fa-chevron-down chevron-icon"></i>
                </div>
                <div class="details-section-content">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
                        <p class="help-text" style="margin: 0;">Add notes and feedback for specific laps or the entire session.</p>
                        <button class="btn btn-primary btn-sm" onclick="showAddAnnotationModalFromDetail('${session.meta.session_id}')">Add Note</button>
                    </div>
                    <div id="detailAnnotationsList">
                        <div class="loading">Loading notes...</div>
                    </div>
                </div>
            </div>
        `;

        // Load Annotations
        loadAnnotationsForDetail(session.meta.session_id);

        // Phase 7.4.3: Init Comparison
        if (typeof initComparison === 'function') {
            setTimeout(() => initComparison(session), 100);
        }

    } catch (error) {
        console.error(error);
        container.innerHTML = `<div class="error-state">
            <p>Failed to load session</p>
            <p class="help-text" style="color: var(--error);">${error.message}</p>
        </div>`;
    }
}



// ============================================================================
// PROCESS VIEW
// ============================================================================
// State for Archive View
let isArchivesView = false;

function toggleArchivesView() {
    const toggle = document.getElementById('showArchivesToggle');
    if (toggle) {
        isArchivesView = toggle.checked;
        loadLearningFiles();
    }
}

async function loadLearningFiles() {
    const container = document.getElementById('learningFilesList');
    container.innerHTML = '<div class="loading">Loading files...</div>';

    try {
        // Fetch both file list (with archive flag), processed files, and session limit in parallel
        const [files, processedList, limitInfo] = await Promise.all([
            apiCall(`/api/learning/list?archived=${isArchivesView}`),
            apiCall('/api/learning/processed'),
            apiCall('/api/sessions/limit')
        ]);
        window.currentFiles = files;
        window.processedFiles = new Set(processedList);
        window.sessionLimit = limitInfo;
        renderFileTable();
    } catch (error) {
        container.innerHTML = '<p class="help-text">Failed to load files</p>';
    }
}

function renderFileTable() {
    const container = document.getElementById('learningFilesList');
    const files = window.currentFiles || [];
    const processedFiles = window.processedFiles || new Set();
    const limit = window.sessionLimit;

    if (files.length === 0) {
        container.innerHTML = '<p class="help-text">No learning files available</p>';
        return;
    }

    // Session Limit Banner
    let limitBanner = '';
    if (limit && limit.tier === 'free') {
        const isFull = limit.used >= limit.max;
        const color = isFull ? 'var(--error)' : (limit.used >= limit.max - 1 ? 'var(--warning)' : 'var(--success)');
        limitBanner = `
            <div class="card" style="margin-bottom: 1.5rem; border-left: 4px solid ${color}; background: rgba(255,255,255,0.02);">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <strong style="color: ${color};">${isFull ? 'Session Limit Reached' : 'Free Tier Storage'}</strong>
                        <p class="help-text" style="margin: 0.25rem 0 0 0;">
                            You have used ${limit.used} of ${limit.max} available sessions. 
                            ${isFull ? 'Upgrade to Pro for unlimited storage.' : 'Upgrade to Pro to remove this limit.'}
                        </p>
                    </div>
                    <button class="btn btn-primary btn-sm" onclick="showUpgradeModal('Unlimited Storage')">Upgrade</button>
                </div>
                <div style="height: 4px; background: rgba(255,255,255,0.05); border-radius: 2px; margin-top: 1rem; overflow: hidden;">
                    <div style="height: 100%; width: ${(limit.used / limit.max) * 100}%; background: ${color};"></div>
                </div>
            </div>
        `;
    }

    // Count unprocessed files for the Process All button
    const unprocessedCount = files.filter(f => !processedFiles.has(f.filename)).length;

    const rows = files.map(f => {
        const rowClass = f.locked ? 'locked-row' : '';
        const lockIcon = f.locked ? '🔒' : '🔓';
        const lockTitle = f.locked ? 'Unlock File' : 'Lock File';
        const deleteStyle = f.locked ? 'color:#555' : 'color:var(--error)';
        const deleteAttr = f.locked ? 'disabled title="File is Locked"' : 'title="Delete"';
        const notes = f.notes ? `<div style="font-size:0.8em; color:#aaa;">${f.notes}</div>` : '';

        // Check if file is already processed
        const isProcessed = processedFiles.has(f.filename);
        const processedBadge = isProcessed ? '<span style="color:#4CAF50; margin-left:0.5rem;" title="Already Processed">✅</span>' : '';

        const isLimitReached = limit && limit.tier === 'free' && limit.used >= limit.max;
        const processBtn = isProcessed
            ? '<button class="btn small" disabled style="opacity:0.5;" title="Already Processed">Processed</button>'
            : `<button class="btn small" ${isLimitReached ? 'disabled title="Session limit reached. Upgrade to Pro."' : ''} onclick="processFile('${f.filename}')">Process</button>`;

        return `
            <tr class="${rowClass}">
                <td>
                    <input type="checkbox" class="file-sel" value="${f.filename}" 
                           ${f.locked ? 'disabled' : ''} onchange="updateBulkUI()">
                </td>
                <td>
                    <div style="font-weight:bold; display:flex; align-items:center;">
                        ${f.filename}${processedBadge}
                    </div>
                    ${notes}
                </td>
                <td>
                    <div style="font-size:0.9em;">${f.size_kb} KB</div>
                    <div style="font-size:0.8em; color:#888;">${formatDateTimeAbbreviated(f.modified)}</div>
                </td>
                <td style="text-align:center;">
                    <button class="btn-icon" onclick="toggleFileLock('${f.filename}', ${!f.locked})" 
                            title="${lockTitle}">
                        ${lockIcon}
                    </button>
                </td>
                <td style="text-align:right; white-space:nowrap;">
                    <button class="btn-icon" onclick="viewGeoPath('${f.filename}')" title="Visualize Path">🗺️</button>
                    <button class="btn-icon" onclick="viewRawFile('${f.filename}')" title="View Raw Data">👁️</button>
                    ${!isArchivesView ? `<button class="btn-icon" onclick="renameLearningFile('${f.filename}')" title="Rename">✎</button>` : ''}
                    ${isArchivesView
                ? `<button class="btn small" style="background:var(--secondary);" onclick="restoreFile('${f.filename}')">Restore</button>`
                : processBtn}
                    <button class="btn-icon" onclick="deleteFile('${f.filename}')" 
                            style="${deleteStyle}" ${deleteAttr}>
                        🗑️
                    </button>
                </td>
            </tr>
        `;
    }).join('');

    const html = `
        ${limitBanner}
        <div style="margin-bottom: 1rem; display: flex; gap: 1rem; align-items: center; flex-wrap: wrap;">
            <button class="btn btn-primary" id="btnProcessAll" onclick="processAllFiles()" ${(unprocessedCount === 0 || (limit && limit.tier === 'free' && limit.used >= limit.max)) ? 'disabled style="opacity:0.5;"' : ''}>
                🚀 Process All${unprocessedCount > 0 ? ` (${unprocessedCount})` : ''}
            </button>
            <button class="btn btn-danger btn-sm" id="btnDeleteBulk" onclick="deleteSelectedFiles()" style="display:none;">
                Delete Selected
            </button>
            <span class="help-text" id="selCount"></span>
        </div>
        <div class="table-responsive">
            <table class="data-table">
                <thead>
                    <tr>
                        <th width="30"><input type="checkbox" onchange="toggleSelectAll(this)"></th>
                        <th>Filename</th>
                        <th>Size | Date</th>
                        <th width="50" style="text-align:center;">Lock</th>
                        <th style="text-align:right;">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${rows}
                </tbody>
            </table>
        </div>
    `;
    container.innerHTML = html;
}

function toggleSelectAll(cb) {
    document.querySelectorAll('.file-sel:not(:disabled)').forEach(el => el.checked = cb.checked);
    updateBulkUI();
}

function updateBulkUI() {
    const checked = document.querySelectorAll('.file-sel:checked').length;
    const btn = document.getElementById('btnDeleteBulk');
    const lbl = document.getElementById('selCount');
    const processBtn = document.getElementById('btnProcessAll');
    const processedFiles = window.processedFiles || new Set();

    if (checked > 0) {
        btn.style.display = 'inline-block';
        lbl.textContent = `${checked} selected`;

        // Update Process All count based on selected unprocessed files
        const selectedUnprocessed = Array.from(document.querySelectorAll('.file-sel:checked'))
            .filter(el => !processedFiles.has(el.value)).length;

        if (processBtn) {
            if (selectedUnprocessed > 0) {
                processBtn.textContent = `🚀 Process Selected (${selectedUnprocessed})`;
                processBtn.disabled = false;
                processBtn.style.opacity = '1';
            } else {
                processBtn.textContent = '🚀 Process Selected (0)';
                processBtn.disabled = true;
                processBtn.style.opacity = '0.5';
            }
        }
    } else {
        btn.style.display = 'none';
        lbl.textContent = '';

        // Reset to show all unprocessed count
        const files = window.currentFiles || [];
        const unprocessedCount = files.filter(f => !processedFiles.has(f.filename)).length;
        if (processBtn) {
            processBtn.textContent = `🚀 Process All${unprocessedCount > 0 ? ` (${unprocessedCount})` : ''}`;
            processBtn.disabled = unprocessedCount === 0;
            processBtn.style.opacity = unprocessedCount === 0 ? '0.5' : '1';
        }
    }
}

async function toggleFileLock(filename, lock) {
    try {
        await apiCall(`/api/learning/${filename}/lock`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ locked: lock })
        });
        loadLearningFiles(); // Reload
    } catch (e) {
        showToast("Lock update failed: " + e.message, "error");
    }
}

async function deleteFile(filename) {
    if (isArchivesView) {
        if (!confirm(`Are you sure you want to PERMANENTLY delete ${filename}? This cannot be undone.`)) return;
        await performDelete([filename], true);
    } else {
        // Main view: Move to Archive
        if (!confirm(`Move ${filename} to archive?`)) return;
        try {
            const res = await apiCall('/api/learning/archive', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ files: [filename] })
            });

            if (res.success) {
                showToast('File moved to archive', 'success');
                loadLearningFiles();
            }
        } catch (e) {
            showToast('Archive Failed', 'error');
        }
    }
}

async function restoreFile(filename) {
    try {
        const res = await apiCall('/api/learning/restore', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ files: [filename] })
        });

        if (res.success) {
            showToast('File restored from archive', 'success');
            loadLearningFiles();
        }
    } catch (e) {
        showToast('Restore Failed', 'error');
    }
}

async function deleteSelectedFiles() {
    const selected = Array.from(document.querySelectorAll('.file-sel:checked')).map(el => el.value);
    if (selected.length === 0) return;

    if (isArchivesView) {
        if (!confirm(`PERMANENTLY delete ${selected.length} files?`)) return;
        await performDelete(selected, true);
    } else {
        if (!confirm(`Move ${selected.length} files to archive?`)) return;
        try {
            const res = await apiCall('/api/learning/archive', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ files: selected })
            });
            if (res.success) {
                showToast(`Archived ${res.moved.length} files`, 'success');
                loadLearningFiles();
            }
        } catch (e) {
            showToast('Archive Failed', 'error');
        }
    }
}

async function performDelete(filenames, fromArchive = false) {
    try {
        const res = await apiCall('/api/learning/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ files: filenames, from_archive: fromArchive })
        });

        if (res && res.deleted && res.deleted.length > 0) {
            showToast(`Deleted ${res.deleted.length} files`, 'success');
        }
        if (res && res.failed && res.failed.length > 0) {
            showToast(`Failed to delete ${res.failed.length} files (Check locks)`, 'warning');
        }
        loadLearningFiles();
    } catch (e) {
        showToast("Delete failed: " + e.message, "error");
    }
}

async function processFile(filename) {
    if (!confirm(`Process session '${filename}'? This will take a few seconds.`)) {
        return;
    }

    showToast('Processing session...', 'info');

    try {
        const result = await apiCall('/api/process', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: filename })
        });

        showToast('Session processed successfully!', 'success');

        // Refresh data
        setTimeout(() => {
            loadLearningFiles(); // Refresh to show checkmark
        }, 1000);

    } catch (error) {
        showToast('Processing failed', 'error');
    }
}

async function processAllFiles() {
    const processedFiles = window.processedFiles || new Set();
    const files = window.currentFiles || [];

    // Check if there's a selection - if so, only process selected unprocessed files
    const selectedCheckboxes = document.querySelectorAll('.file-sel:checked');
    let filesToProcess = [];

    if (selectedCheckboxes.length > 0) {
        // Process only selected unprocessed files
        filesToProcess = Array.from(selectedCheckboxes)
            .map(cb => cb.value)
            .filter(filename => !processedFiles.has(filename));
    } else {
        // Process all unprocessed files
        filesToProcess = files
            .filter(f => !processedFiles.has(f.filename))
            .map(f => f.filename);
    }

    if (filesToProcess.length === 0) {
        showToast('No unprocessed files to process', 'info');
        return;
    }

    const actionText = selectedCheckboxes.length > 0 ? 'selected' : 'all';
    if (!confirm(`Process ${filesToProcess.length} ${actionText} unprocessed file(s)? This may take a while.`)) {
        return;
    }

    showToast(`Processing ${filesToProcess.length} files...`, 'info');

    try {
        const result = await apiCall('/api/process/all', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ files: filesToProcess })
        });

        if (result.processed > 0) {
            showToast(`Successfully processed ${result.processed} file(s)!`, 'success');
        } else if (result.skipped > 0) {
            showToast('All files were already processed', 'info');
        }

        if (result.failed > 0) {
            showToast(`${result.failed} file(s) failed to process`, 'warning');
            console.error('Processing failures:', result.details?.failed);
        }

        // Refresh the file list to show updated checkmarks
        setTimeout(() => {
            loadLearningFiles();
        }, 500);

    } catch (error) {
        showToast('Bulk processing failed: ' + error.message, 'error');
    }
}

// ----------------------------------------------------------------------------
// LAP DETAILED ANALYSIS (Phase 7.4)
// ----------------------------------------------------------------------------

// ----------------------------------------------------------------------------
// LAP DETAILED ANALYSIS (Phase 7.4)
// ----------------------------------------------------------------------------

async function viewLapDetail(sessionId, lapNumber, shareToken = null) {
    const container = document.getElementById('sessionDetailContent');
    container.innerHTML = `<div class="loading">Loading Lap ${lapNumber} telemetry...</div>`;

    try {
        let endpoint = `/api/sessions/${sessionId}`;
        if (shareToken) {
            endpoint = `/api/shared/${shareToken}`;
        }
        const session = await apiCall(endpoint);
        const lap = session.laps.find(l => l.lap_number === lapNumber);

        // Fetch Telemetry
        let telemetry = null;
        try {
            let teleEndpoint = `/api/sessions/${sessionId}_telemetry`;
            if (shareToken) {
                teleEndpoint = `/api/shared/${shareToken}/telemetry`;
            }
            telemetry = await apiCall(teleEndpoint);
        } catch (e) {
            throw new Error("Telemetry not available for this session.");
        }


        // Slice Telemetry
        const tStart = lap.start_time;
        const tEnd = tStart + lap.lap_time;

        // Filter indices
        const times = telemetry.time;
        const indices = [];
        for (let i = 0; i < times.length; i++) {
            if (times[i] >= tStart && times[i] <= tEnd) {
                indices.push(i);
            }
        }

        if (indices.length === 0) throw new Error("No samples found for this lap.");

        // Extract subset
        const subset = {
            times: indices.map(i => telemetry.time[i]),
            lats: indices.map(i => telemetry.lat[i]),
            lons: indices.map(i => telemetry.lon[i]),
            speeds: indices.map(i => telemetry.speed[i]),
            ax: telemetry.ax ? indices.map(i => telemetry.ax[i]) : null,
            ay: telemetry.ay ? indices.map(i => telemetry.ay[i]) : null
        };

        // Metrics & Confidence
        const lapMetrics = session.analysis?.metrics?.laps?.find(x => x.lap_number === lapNumber);
        const imuConfidence = lapMetrics?.confidence || session.calibration?.confidence || "N/A";
        // Color for badge: Green/Orange/Red
        const imuColor = imuConfidence.includes('HIGH') || imuConfidence === true ? '#4CAF50' : (imuConfidence.includes('MEDIUM') ? '#FF9800' : '#F44336');

        // Reference Data for Table
        const sectors = lap.sector_times || [];
        // TBL from session reference
        const tblSectors = session.references?.sector_times || [];
        const tblTotal = session.references?.theoretical_best_reference || (tblSectors.length ? tblSectors.reduce((a, b) => a + b, 0) : 0);

        // --------------------------------------------------------
        // DASHBOARD LAYOUT
        // --------------------------------------------------------
        container.innerHTML = `
            <!-- HEADER -->
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                <div>
                    <h2 style="margin:0;">Lap ${lapNumber} Analysis</h2>
                    <p class="help-text" style="margin:0;">${session.track.track_name} • ${formatTime(lap.lap_time)}</p>
                </div>
                <div style="display:flex; gap:1rem; align-items:center;">
                    <span class="badge" style="background:${imuColor}22; color:${imuColor}; border:1px solid ${imuColor}55;">IMU: ${imuConfidence}</span>
                    <button class="btn" onclick="viewSession('${sessionId}')">Back</button>
                </div>
            </div>
            
            <!-- MAPS GRID -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 2rem;">
                <!-- Dynamics Tooltip & Card -->
                <div class="card" onclick="openLapModal('dynamics')" style="cursor:pointer; transition: transform 0.2s; position:relative;" 
                     onmouseover="this.style.borderColor='var(--primary)'; this.style.transform='scale(1.01)'" 
                     onmouseout="this.style.borderColor='var(--border)'; this.style.transform='scale(1)'"
                     title="Click to Expand & View G-Force Trace">
                    <h3 style="margin-top:0; font-size:1rem; display:flex; justify-content:space-between;">
                        Dynamics Map <span style="font-size:0.8em; opacity:0.6">⤢ Expand</span>
                    </h3>
                    ${generateColorMapSVG(subset, 'imu', { small: true })}
                    <p class="help-text" style="margin-top:0.5rem; font-size:0.8rem;">Accel(Grn) • Brake(Red) • Lat(Glow)</p>
                </div>
                
                <!-- Speed Tooltip & Card -->
                <div class="card" onclick="openLapModal('speed')" style="cursor:pointer; transition: transform 0.2s;" 
                     onmouseover="this.style.borderColor='var(--primary)'; this.style.transform='scale(1.01)'" 
                     onmouseout="this.style.borderColor='var(--border)'; this.style.transform='scale(1)'"
                     title="Click to Expand">
                    <h3 style="margin-top:0; font-size:1rem; display:flex; justify-content:space-between;">
                         Speed Map <span style="font-size:0.8em; opacity:0.6">⤢ Expand</span>
                    </h3>
                    ${generateColorMapSVG(subset, 'speed', { small: true })}
                    <p class="help-text" style="margin-top:0.5rem; font-size:0.8rem;">Fast(Green) • Slow(Red)</p>
                </div>
            </div>
            
            <!-- DETAILED METRICS -->
            <div class="card">
                <h3 style="margin-top:0;">Sector Breakdown</h3>
                <div style="overflow-x: auto;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 0.9rem;">
                        <thead>
                            <tr style="background: var(--surface); color: var(--text-secondary);">
                                <th style="padding: 0.75rem; text-align: left;">Metric</th>
                                ${sectors.map((_, i) => `<th style="padding: 0.75rem; text-align: right;">S${i + 1}</th>`).join('')}
                                <th style="padding: 0.75rem; text-align: right;">Lap Total</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr style="border-bottom: 1px solid var(--border);">
                                <td style="padding: 0.75rem; font-weight:bold;">Current Lap</td>
                                ${sectors.map(t => `<td style="padding: 0.75rem; text-align:right;">${formatTime(t)}</td>`).join('')}
                                <td style="padding: 0.75rem; text-align:right; font-weight:bold;">${formatTime(lap.lap_time)}</td>
                            </tr>
                            <tr style="border-bottom: 1px solid var(--border);">
                                <td style="padding: 0.75rem; color:#888;">Theoretical Best</td>
                                ${tblSectors.map(t => `<td style="padding: 0.75rem; text-align:right; color:#888;">${formatTime(t)}</td>`).join('')}
                                <td style="padding: 0.75rem; text-align:right; color:#888;">${formatTime(tblTotal)}</td>
                            </tr>
                            <tr>
                                <td style="padding: 0.75rem; color:${lap.lap_time - tblTotal > 0 ? '#f44336' : '#4caf50'};">Delta to Optimal</td>
                                ${sectors.map((t, i) => {
            const d = tblSectors[i] ? t - tblSectors[i] : 0;
            const col = d > 0.05 ? '#f44336' : (d < -0.05 ? '#4caf50' : '#888');
            return `<td style="padding: 0.75rem; text-align:right; color:${col};">${d > 0 ? '+' : ''}${d.toFixed(3)}</td>`;
        }).join('')}
                                <td style="padding: 0.75rem; text-align:right; font-weight:bold; color:${lap.lap_time - tblTotal > 0 ? '#f44336' : '#4caf50'}">
                                    ${(lap.lap_time - tblTotal).toFixed(3)}
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- MODAL (Hidden) -->
            <div id="lapModal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.95); z-index:9999; overflow-y:auto; padding:2rem;">
                <div style="max-width:1200px; margin:0 auto;">
                     <div style="display:flex; justify-content:flex-end; margin-bottom:1rem;">
                        <button class="btn" style="background:#555; padding:0.5rem 1.5rem;" onclick="document.getElementById('lapModal').style.display='none'">CLOSE [X]</button>
                     </div>
                     <div id="lapModalContent"></div>
                </div>
            </div>
        `;

        // Store for Modal access
        window._currentLapData = { subset, lap };

    } catch (e) {
        container.innerHTML = `
            <div class="error">
                <h3>Analysis Failed</h3>
                <p>${e.message}</p>
                <button class="btn btn-primary" onclick="viewSession('${sessionId}')">Back</button>
            </div>
        `;
    }
}

// ----------------------------------------------------------------------------
// MODAL LOGIC
// ----------------------------------------------------------------------------
window.openLapModal = function (mode) {
    const modal = document.getElementById('lapModal');
    const content = document.getElementById('lapModalContent');
    const { subset, lap } = window._currentLapData;

    let html = '';

    if (mode === 'dynamics') {
        html = `
            <div class="card" style="margin-bottom:1rem; border:1px solid var(--primary);">
                <h2 style="text-align:center; margin:0 0 1rem 0;">Rider Dynamics (Full View)</h2>
                ${generateColorMapSVG(subset, 'imu', { small: false, sectors: lap.sector_times })}
            </div>
            <div class="card">
                <h3 style="margin-top:0;">G-Force Trace (Synced)</h3>
                ${generateGForceChart(subset, lap)}
            </div>
        `;
    } else {
        html = `
             <div class="card" style="margin-bottom:1rem; border:1px solid #4CAF50;">
                <h2 style="text-align:center; margin:0 0 1rem 0;">Speed Profile (Full View)</h2>
                ${generateColorMapSVG(subset, 'speed', { small: false, sectors: lap.sector_times })}
            </div>
        `;
    }

    content.innerHTML = html;
    modal.style.display = 'block';
}

// ----------------------------------------------------------------------------
// COMPARISON FEATURE (M6)
// ----------------------------------------------------------------------------

let comparisonSlots = [null, null];

function setForComparison(sessionId, lapNumber) {
    if (!comparisonSlots[0]) {
        comparisonSlots[0] = { sessionId, lapNumber };
        showToast(`Lap ${lapNumber} added as Lap 1`, 'info');
    } else if (!comparisonSlots[1]) {
        comparisonSlots[1] = { sessionId, lapNumber };
        showToast(`Lap ${lapNumber} added as Lap 2`, 'info');
        // Auto-show comparison if we have both
        showComparison();
    } else {
        // Shift and add
        comparisonSlots[0] = comparisonSlots[1];
        comparisonSlots[1] = { sessionId, lapNumber };
        showToast(`Lap ${lapNumber} added as Lap 2`, 'info');
        showComparison();
    }
}

async function showComparison() {
    if (!comparisonSlots[0] || !comparisonSlots[1]) {
        showToast('Select two laps to compare', 'warning');
        return;
    }

    const view = document.getElementById('comparisonView');
    const container = document.getElementById('comparisonContent');

    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    view.classList.add('active');

    container.innerHTML = '<div class="loading">Aligning telemetry...</div>';

    try {
        const s1 = comparisonSlots[0];
        const s2 = comparisonSlots[1];

        const data = await apiCall(`/api/compare?session1=${s1.sessionId}&lap1=${s1.lapNumber - 1}&session2=${s2.sessionId}&lap2=${s2.lapNumber - 1}`);

        container.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
                <h2>Lap Comparison</h2>
                <button class="btn btn-secondary" onclick="comparisonSlots = [null, null]; showView('sessions');">Clear & Exit</button>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 2rem;">
                <div class="card" style="border-left: 4px solid var(--primary);">
                    <h3 style="margin: 0 0 0.5rem 0; font-size: 0.9rem; color: var(--text-dim);">LAP 1</h3>
                    <div style="font-size: 1.5rem; font-weight: bold;">${formatTime(data.lap1.lap_info.lap_time)}</div>
                    <div style="font-size: 0.8rem; color: var(--primary); font-weight: 600;">👤 ${data.lap1.user_name}</div>
                    <div style="font-size: 0.75rem; color: var(--text-muted);">${data.lap1.session_name} • Lap ${data.lap1.lap_info.lap_number}</div>
                </div>
                <div class="card" style="border-left: 4px solid var(--secondary);">
                    <h3 style="margin: 0 0 0.5rem 0; font-size: 0.9rem; color: var(--text-dim);">LAP 2</h3>
                    <div style="font-size: 1.5rem; font-weight: bold;">${formatTime(data.lap2.lap_info.lap_time)}</div>
                    <div style="font-size: 0.8rem; color: var(--secondary); font-weight: 600;">👤 ${data.lap2.user_name}</div>
                    <div style="font-size: 0.75rem; color: var(--text-muted);">${data.lap2.session_name} • Lap ${data.lap2.lap_info.lap_number}</div>
                </div>
            </div>

            <div class="card" style="margin-bottom: 1.5rem;">
                <h3>Sector Comparison</h3>
                <div style="overflow-x: auto;">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>Sector</th>
                                <th>Lap 1</th>
                                <th>Lap 2</th>
                                <th>Delta</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.lap1.lap_info.sector_times.map((s1_time, i) => {
            const s2_time = data.lap2.lap_info.sector_times[i];
            const delta = s1_time - s2_time;
            const deltaColor = delta > 0 ? 'var(--success)' : 'var(--error)';
            return `
                                <tr>
                                    <td>Sector ${i + 1}</td>
                                    <td style="font-family: monospace;">${formatTime(s1_time)}</td>
                                    <td style="font-family: monospace;">${formatTime(s2_time)}</td>
                                    <td style="font-family: monospace; font-weight: 700; color: ${deltaColor};">
                                        ${delta > 0 ? '+' : ''}${delta.toFixed(3)}s
                                    </td>
                                </tr>
                                `;
        }).join('')}
                        </tbody>
                    </table>
                </div>
            </div>

            <div class="card" style="margin-bottom: 1.5rem;">
                <h3>Telemetry Overlay (MVP)</h3>
                <p class="help-text">Side-by-side visualization coming in next update. For now, use sector times for comparison.</p>
                <div style="display: flex; gap: 1rem;">
                    <div style="flex: 1;">
                        ${generateColorMapSVG(sliceTelemetry(data.lap1), 'speed', { small: true })}
                        <p style="text-align: center; font-size: 0.8rem;">Lap 1 Speed Map</p>
                    </div>
                    <div style="flex: 1;">
                        ${generateColorMapSVG(sliceTelemetry(data.lap2), 'speed', { small: true })}
                        <p style="text-align: center; font-size: 0.8rem;">Lap 2 Speed Map</p>
                    </div>
                </div>
            </div>
        `;
    } catch (error) {
        container.innerHTML = `<p class="help-text">Failed to load comparison: ${error.message}</p>`;
    }
}

function sliceTelemetry(lapData) {
    const { lap_info, telemetry } = lapData;
    // For compare API, we already sliced it on the server (if it's my new API)
    // Wait, let's check my compare API return format.
    // Yes, lap1_data.telemetry is the sliced list.

    // Actually, generateColorMapSVG expects { lats, lons, speeds, times }
    // But my sliced telemetry might be a list of dicts or something.
    // Let's assume it's a list of dicts.
    if (Array.isArray(telemetry)) {
        return {
            lats: telemetry.map(p => p.lat),
            lons: telemetry.map(p => p.lon),
            speeds: telemetry.map(p => p.speed),
            times: telemetry.map(p => p.time)
        };
    }
    return telemetry;
}

function generateColorMapSVG(data, mode, options = {}) {
    // Mode: 'imu' | 'speed'

    // 1. Normalization
    const minLat = Math.min(...data.lats);
    const maxLat = Math.max(...data.lats);
    const minLon = Math.min(...data.lons);
    const maxLon = Math.max(...data.lons);

    if (minLat === maxLat || minLon === maxLon) return '<p>No Data</p>';

    const latDiff = maxLat - minLat;
    const lonDiff = (maxLon - minLon) * Math.cos(minLat * Math.PI / 180);
    const aspect = latDiff / lonDiff;

    // Size logic
    const w = options.small ? 400 : 800;
    const h = Math.max(200, Math.min(w * 0.8, w * aspect)); // Limit height
    const pad = options.small ? 20 : 40;
    const keyHeight = options.small ? 0 : 30; // Extra space for key in large mode

    const scaleX = (lon) => pad + ((lon - minLon) / (maxLon - minLon)) * (w - 2 * pad);
    const scaleY = (lat) => h - keyHeight - (pad + ((lat - minLat) / (maxLat - minLat)) * (h - keyHeight - 2 * pad));

    // 2. Data Ranges
    const G = 16384.0;
    const hasIMU = data.ax && data.ay;
    const minSpeed = Math.min(...data.speeds);
    const maxSpeed = Math.max(...data.speeds);

    let maxAccelVal = 1, maxBrakeVal = -1, maxLatVal = 1;
    if (hasIMU) {
        maxAccelVal = Math.max(1.0, Math.max(...data.ay));
        maxBrakeVal = Math.min(-1.0, Math.min(...data.ay));
        maxLatVal = Math.max(1.0, Math.max(...data.ax.map(Math.abs)));
    }

    let bottomPaths = ''; // Halo / Background
    let topPaths = '';    // Core / Trajectory

    // Thicker Core, Much Thicker Halo to appear "outside"
    // Small: Core 4, Halo 10 (3px border). Large: Core 6, Halo 22 (8px border).
    const strokeCore = options.small ? 4 : 6;
    const strokeGlow = options.small ? 10 : 22;

    for (let i = 0; i < data.lats.length - 1; i++) {
        const x1 = scaleX(data.lons[i]);
        const y1 = scaleY(data.lats[i]);
        const x2 = scaleX(data.lons[i + 1]);
        const y2 = scaleY(data.lats[i + 1]);

        if (mode === 'imu' && hasIMU) {
            // IMU Logic
            // Lateral Glow (Background Layer)
            const latVal = Math.abs(data.ax[i]);
            if (latVal > 0.15 * maxLatVal) {
                const t = (latVal - 0.15 * maxLatVal) / (0.85 * maxLatVal);
                // Blue(Low) -> Red(High)
                const tClamped = Math.min(1, t * 1.5);
                const r = Math.floor(33 + tClamped * (244 - 33));
                const g = Math.floor(150 + tClamped * (67 - 150));
                const b = Math.floor(243 + tClamped * (54 - 243));
                const c = `rgb(${r},${g},${b})`;

                // Solid opacity (1.0) to avoid "dots" at joints. Round caps for smooth corners.
                bottomPaths += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${c}" stroke-width="${strokeGlow}" stroke-linecap="round" />`;
            }

            // Core (Accel/Brake) (Top Layer)
            const val = data.ay[i];
            let c = '#FFEB3B';
            if (val > 0) { // Accel
                const t = Math.min(1, val / maxAccelVal);
                // Yel -> Grn
                const r = Math.floor(255 + t * (76 - 255));
                const g = Math.floor(235 + t * (175 - 235));
                const b = Math.floor(59 + t * (80 - 59));
                c = `rgb(${r},${g},${b})`;
            } else { // Brake
                const t = Math.min(1, val / maxBrakeVal);
                // Yel -> Red
                const r = Math.floor(255 + t * (244 - 255));
                const g = Math.floor(235 + t * (67 - 235));
                const b = Math.floor(59 + t * (54 - 59));
                c = `rgb(${r},${g},${b})`;
            }
            topPaths += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${c}" stroke-width="${strokeCore}" stroke-linecap="round" />`;

        } else {
            // Speed Logic (Green Fast, Red Slow)
            const speed = data.speeds[i];
            const t = (speed - minSpeed) / (maxSpeed - minSpeed || 1);
            let r, g, b;
            if (t < 0.5) { // Red -> Yellow
                const t2 = t * 2;
                r = Math.floor(244 + t2 * (255 - 244));
                g = Math.floor(67 + t2 * (235 - 67));
                b = Math.floor(54 + t2 * (59 - 54));
            } else { // Yellow -> Green
                const t2 = (t - 0.5) * 2;
                r = Math.floor(255 + t2 * (76 - 255));
                g = Math.floor(235 + t2 * (175 - 235));
                b = Math.floor(59 + t2 * (80 - 59));
            }
            const c = `rgb(${r},${g},${b})`;
            topPaths += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${c}" stroke-width="${strokeCore}" stroke-linecap="round" />`;
        }
    }

    // Markers logic
    let markers = '';
    if (options.sectors && !options.small) {
        let cumTime = 0;
        const totalDuration = data.times[data.times.length - 1] - data.times[0];

        options.sectors.forEach((st, idx) => {
            cumTime += st;
            if (cumTime < totalDuration - 1.0) {
                const tTarget = data.times[0] + cumTime;
                const index = data.times.findIndex(t => t >= tTarget);
                if (index > 0) {
                    const xm = scaleX(data.lons[index]);
                    const ym = scaleY(data.lats[index]);
                    markers += `
                     <circle cx="${xm}" cy="${ym}" r="8" fill="#fff" stroke="#000" stroke-width="2"/>
                     <text x="${xm + 12}" y="${ym + 4}" fill="#eee" font-size="14" font-weight="bold" style="text-shadow: 1px 1px 2px black;">S${idx + 1}</text>
                   `;
                }
            }
        });
    }

    // Legend
    let legendGroup = '';
    if (!options.small) { // Only show legend in large view
        if (mode === 'imu') {
            legendGroup = `
                 <g transform="translate(${w / 2 - 150}, ${h - 20})">
                    <rect x="0" y="0" width="300" height="20" rx="4" fill="#000" fill-opacity="0.5" />
                    <!-- Accel -->
                    <circle cx="20" cy="10" r="4" fill="#4CAF50" />
                    <text x="30" y="14" fill="#ddd" font-size="10">Acceleration</text>
                    <!-- Brake -->
                    <circle cx="110" cy="10" r="4" fill="#F44336" />
                    <text x="120" y="14" fill="#ddd" font-size="10">Braking</text>
                    <!-- Lat -->
                    <circle cx="180" cy="10" r="6" stroke="#2196F3" stroke-width="2" fill="none" />
                    <text x="195" y="14" fill="#ddd" font-size="10">Lateral Force</text>
                 </g>
             `;
        } else {
            legendGroup = `
                 <g transform="translate(${w / 2 - 100}, ${h - 20})">
                    <rect x="0" y="0" width="200" height="20" rx="4" fill="#000" fill-opacity="0.5" />
                    <circle cx="20" cy="10" r="4" fill="#4CAF50" />
                    <text x="30" y="14" fill="#ddd" font-size="10">Fast</text>
                    <circle cx="80" cy="10" r="4" fill="#FFEB3B" />
                    <text x="90" y="14" fill="#ddd" font-size="10">Mod</text>
                    <circle cx="140" cy="10" r="4" fill="#F44336" />
                    <text x="150" y="14" fill="#ddd" font-size="10">Slow</text>
                 </g>
             `;
        }
    }

    return `
        <div style="max-width:${options.small ? '100%' : '1000px'}; margin:0 auto;">
            <svg viewBox="0 0 ${w} ${h}" style="width:100%; height:auto; background:#111; border-radius:8px;">
                ${bottomPaths}
                ${topPaths}
                ${markers}
                ${legendGroup}
            </svg>
        </div>
    `;
}

function generateGForceChart(data, lap) {
    if (!data.ax || !data.ay) return '<p class="help-text">No G-Force data</p>';

    const h = 250, w = 800, pad = 40;
    const tStart = data.times[0];
    const tDuration = data.times[data.times.length - 1] - tStart;
    const xScale = (tRel) => pad + (tRel / tDuration) * (w - 2 * pad);

    const zeroY = h / 2;
    const maxScale = 25000; // Fixed scale for 1.5G
    const yScale = (val) => zeroY - (val / maxScale) * (h / 2 - pad);

    let axPath = `M ${xScale(0)} ${yScale(data.ax[0])}`;
    let ayPath = `M ${xScale(0)} ${yScale(data.ay[0])}`;

    for (let i = 1; i < data.times.length; i++) {
        const x = xScale(data.times[i] - tStart);
        axPath += ` L ${x} ${yScale(data.ax[i])}`;
        ayPath += ` L ${x} ${yScale(data.ay[i])}`;
    }

    let sectorLines = '';
    let cumTime = 0;
    if (lap && lap.sector_times) {
        lap.sector_times.forEach((st, idx) => {
            cumTime += st;
            if (cumTime <= tDuration + 1.0) {
                const xS = xScale(cumTime);
                sectorLines += `
                    <line x1="${xS}" y1="${pad}" x2="${xS}" y2="${h - pad}" stroke="#666" stroke-dasharray="4" />
                    <text x="${xS}" y="${pad - 5}" fill="#aaa" font-size="10" text-anchor="middle">S${idx + 1}</text>
                `;
            }
        });
    }

    return `
        <svg viewBox="0 0 ${w} ${h}" style="width:100%; height:auto; background:#222; border-radius:8px;">
            <line x1="${pad}" y1="${zeroY}" x2="${w - pad}" y2="${zeroY}" stroke="#444" />
            ${sectorLines}
            <path d="${axPath}" fill="none" stroke="#FF9800" stroke-width="2" opacity="0.8" />
            <path d="${ayPath}" fill="none" stroke="#2196F3" stroke-width="2" opacity="0.8" />
            <text x="${pad}" y="20" fill="#FF9800" font-size="12">Lat (Org)</text>
            <text x="${pad}" y="35" fill="#2196F3" font-size="12">Lon (Blu)</text>
        </svg>
    `;
}
// ============================================================================
// UTILITIES
// ============================================================================

function formatTime(seconds) {
    if (seconds === null || seconds === undefined) return 'N/A';
    const mins = Math.floor(seconds / 60);
    const secs = (seconds % 60).toFixed(3);
    return mins > 0 ? `${mins}:${secs.padStart(6, '0')}` : `${secs}s`;
}

function formatLapTime(seconds) {
    if (seconds === null || seconds === undefined || isNaN(seconds)) return '--:--.---';
    const mins = Math.floor(seconds / 60);
    const secs = (seconds % 60).toFixed(3);
    return `${mins}:${secs.padStart(6, '0')}`;
}

function formatDuration(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function formatDateTime(isoString) {
    const date = new Date(isoString);
    return date.toLocaleString();
}

function formatDateTimeAbbreviated(isoString) {
    const date = new Date(isoString);
    const now = new Date();
    const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return 'Today ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    if (diffDays === 1) return 'Yesterday';
    return date.toLocaleDateString();
}

function formatTime24h(isoString) {
    const date = new Date(isoString);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function groupSessionsByDate(sessions) {
    const groups = {};

    sessions.forEach(session => {
        const date = new Date(session.start_time);
        const today = new Date();
        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);

        let label;
        if (date.toDateString() === today.toDateString()) {
            label = 'Today';
        } else if (date.toDateString() === yesterday.toDateString()) {
            label = 'Yesterday';
        } else {
            label = date.toLocaleDateString();
        }

        if (!groups[label]) {
            groups[label] = [];
        }
        groups[label].push(session);
    });

    return groups;
}

function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type} active`;

    setTimeout(() => {
        toast.classList.remove('active');
    }, 3000);
}

function closeModal() {
    document.getElementById('modal').classList.remove('active');
}


// TRACK RENAME
// TRACK & FILE RENAME
function renameTrack(trackId, currentName) {
    window.renameMode = 'track';
    window.renameTrackId = trackId;
    window.renameCurrentName = currentName;

    const modal = document.getElementById('renameModal');
    const title = modal.querySelector('h3');
    if (title) title.textContent = 'Rename Track';

    const input = document.getElementById('renameInput');
    const preview = document.getElementById('sanitizedPreview');

    input.value = currentName;
    preview.textContent = sanitizeName(currentName);

    input.oninput = () => {
        preview.textContent = sanitizeName(input.value) || '-';
    };

    input.onkeypress = (e) => {
        if (e.key === 'Enter') submitRename();
    };

    modal.classList.add('active');
    setTimeout(() => input.focus(), 100);
}

function renameLearningFile(filename) {
    window.renameMode = 'file';
    window.renameFileOld = filename;

    const modal = document.getElementById('renameModal');
    const title = modal.querySelector('h3');
    if (title) title.textContent = 'Rename File';

    const input = document.getElementById('renameInput');
    const preview = document.getElementById('sanitizedPreview');

    input.value = filename.replace('.csv', '');
    preview.textContent = filename;

    input.oninput = () => {
        let val = input.value.trim();
        // Simple sanitization for file
        val = val.replace(/[^a-zA-Z0-9_\-\.]/g, '_');
        if (!val.toLowerCase().endsWith('.csv')) val += '.csv';
        preview.textContent = val;
    };

    input.onkeypress = (e) => {
        if (e.key === 'Enter') submitRename();
    };

    modal.classList.add('active');
    setTimeout(() => input.focus(), 100);
}

function sanitizeName(name) {
    return name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');
}

function closeRenameModal() {
    document.getElementById('renameModal').classList.remove('active');
}

function submitRename() {
    const inputVal = document.getElementById('renameInput').value.trim();
    closeRenameModal();

    if (window.renameMode === 'file') {
        let newName = inputVal;
        // ensure valid char
        newName = newName.replace(/[^a-zA-Z0-9_\-\.]/g, '_');

        apiCall('/api/learning/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_name: window.renameFileOld, new_name: newName })
        })
            .then(() => {
                showToast('File renamed!', 'success');
                loadLearningFiles();
            })
            .catch((e) => {
                showToast('Rename failed', 'error');
                console.error(e);
            });
        return;
    }

    // TRACK MODE
    const trackId = window.renameTrackId;
    const currentName = window.renameCurrentName;

    if (!inputVal || inputVal === currentName) return;

    apiCall(`/api/tracks/${trackId}/rename`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_name: inputVal })
    })
        .then(() => {
            showToast('Track renamed successfully!', 'success');
            loadTracks();
            // If we are continuously viewing details? Ideally reload details too if open.
        })
        .catch(() => {
            showToast('Rename failed', 'error');
        });
}

// DELETE LOGIC
function deleteSession(sessionId) {
    if (!confirm('Are you sure you want to delete this analysis? The raw CSV will remain safe.')) {
        return;
    }

    apiCall(`/api/sessions/${sessionId}`, { method: 'DELETE' })
        .then(() => {
            showToast('Session Analysis Deleted', 'success');
            showView('sessionsView'); // Go back to list
            loadSessions();
        })
        .catch(err => {
            const msg = err.message || 'Unknown error';
            showToast('Delete failed: ' + msg, 'error');
            console.error(err);
        });
}

function deleteTrack(trackId, trackName) {
    if (!confirm(`Delete track "${trackName}"?\n\nThis will delete:\n- The track definition & map\n- ALL processed sessions for this track.\n\nRaw CSV files are SAFE.`)) {
        return;
    }

    apiCall(`/api/tracks/${trackId}`, { method: 'DELETE' })
        .then(() => {
            showToast('Track Deleted', 'success');
            loadTracks();
        })
        .catch(err => {
            const msg = err.message || 'Unknown error';
            showToast('Delete failed: ' + msg, 'error');
            console.error(err);
        });
}

// ============================================================================
// PHASE 7.1 HELPERS (Visual Analysis)
// ============================================================================

function calculateMedian(values) {
    if (values.length === 0) return 0;
    const sorted = [...values].sort((a, b) => a - b);
    const half = Math.floor(sorted.length / 2);
    if (sorted.length % 2) return sorted[half];
    return (sorted[half - 1] + sorted[half]) / 2.0;
}

function calculateStandardDeviation(values) {
    if (values.length < 2) return 0;
    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const variance = values.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / values.length;
    return Math.sqrt(variance);
}

function getHeatmapClass(time, median) {
    if (!time || !median) return '';
    const pct = (time - median) / median;

    // Faster (Green) - "Better than median"
    if (pct < -0.05) return 'heat-fast-3'; // >5% faster
    if (pct < -0.02) return 'heat-fast-2'; // >2% faster
    if (pct < 0) return 'heat-fast-1';     // any fast

    // Slower (Red) - "Worse than median"
    if (pct > 0.05) return 'heat-slow-3'; // >5% slower
    if (pct > 0.02) return 'heat-slow-2'; // >2% slower
    if (pct > 0) return 'heat-slow-1';    // any slow

    return '';
}

function generateTimelineSVG(laps) {
    const validLaps = laps.filter(l => l.valid && l.lap_time > 0);
    if (validLaps.length < 2) return '';

    // Config
    const width = 800;
    const height = 120;
    const padding = 20;

    // Scales
    const times = validLaps.map(l => l.lap_time);
    const minTime = Math.min(...times);
    const maxTime = Math.max(...times);
    const timeRange = maxTime - minTime || 1;

    // X scale: Lap Number
    const stepX = (width - 2 * padding) / (validLaps.length - 1 || 1);

    // Points
    const points = validLaps.map((lap, i) => {
        const x = padding + i * stepX;
        // Y: map time to height. Min time = top (padding), Max time = bottom (height - padding)
        // normalized (0-1): (lap.lap_time - minTime) / timeRange
        // We want minTime at y=padding, maxTime at y=height-padding
        // So y = padding + (normalized * (height - 2*padding))
        const normalized = (lap.lap_time - minTime) / timeRange;
        const y = padding + (normalized * (height - 2 * padding));
        return { x, y, lap };
    });

    const pathD = `M ${points.map(p => `${p.x},${p.y}`).join(' L ')}`;

    // Best Lap Point
    const bestLap = validLaps.reduce((prev, curr) => curr.lap_time < prev.lap_time ? curr : prev);
    const bestPoint = points.find(p => p.lap.lap_number === bestLap.lap_number);

    return `
        <div style="margin: 2rem 0;">
            <h3 style="margin-bottom: 0.5rem;">Session Trend</h3>
            <svg viewBox="0 0 ${width} ${height}" style="width: 100%; height: auto; background: var(--surface); border: 1px solid var(--border); border-radius: 6px;">
                <!-- Grid Lines (Optional) -->
                <line x1="${padding}" y1="${padding}" x2="${width - padding}" y2="${padding}" stroke="var(--border)" stroke-dasharray="4" />
                <line x1="${padding}" y1="${height - padding}" x2="${width - padding}" y2="${height - padding}" stroke="var(--border)" stroke-dasharray="4" />
                
                <!-- Trend Line -->
                <path d="${pathD}" fill="none" stroke="var(--primary)" stroke-width="2" />
                
                <!-- Points -->
                ${points.map(p => `
                    <circle cx="${p.x}" cy="${p.y}" r="3" fill="var(--surface)" stroke="var(--primary)" stroke-width="2">
                        <title>Lap ${p.lap.lap_number}: ${formatTime(p.lap.lap_time)}</title>
                    </circle>
                `).join('')}
                
                <!-- Best Lap Highlight -->
                ${bestPoint ? `
                    <circle cx="${bestPoint.x}" cy="${bestPoint.y}" r="5" fill="var(--success)" stroke="none" />
                    <text x="${bestPoint.x}" y="${bestPoint.y - 10}" text-anchor="middle" fill="var(--success)" font-size="12" font-weight="bold">BEST</text>
                ` : ''}
            </svg>
             <p class="help-text" style="text-align: right; margin-top: 0.25rem;">Chart: Lower is Faster</p>
        </div>
    `;
}

function generateTrackMapSVG(geometry, bestSectors, targetLap, options = {}) {
    if (!geometry || !geometry.coordinates || !geometry.coordinates.length) return '<p class="help-text">Map geometry unavailable</p>';

    // 1. Normalize Coordinates
    const coords = geometry.coordinates;
    const lats = coords.map(p => p[0]);
    const lons = coords.map(p => p[1]);

    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    const minLon = Math.min(...lons);
    const maxLon = Math.max(...lons);

    const latRange = maxLat - minLat || 0.001;
    const lonRange = maxLon - minLon || 0.001;

    // Viewport 800x600 (Logical)
    const w = 800;
    const h = 600;
    const padding = 50;

    const scaleX = (w - 2 * padding) / lonRange;
    const scaleY = (h - 2 * padding) / latRange;
    const scale = Math.min(scaleX, scaleY);

    const project = (lat, lon) => {
        const x = padding + (lon - minLon) * scale;
        const y = padding + (maxLat - lat) * scale;
        return [x + (w - 2 * padding - lonRange * scale) / 2, y + (h - 2 * padding - latRange * scale) / 2];
    };

    // 2. Build Segments
    let svgPaths = '';
    let labels = '';

    const indices = geometry.sector_indices || [];
    let startIdx = 0;
    const startPt = project(coords[0][0], coords[0][1]);

    for (let i = 0; i < indices.length; i++) {
        let endIdx = indices[i];
        if (endIdx === 0) endIdx = coords.length - 1;

        let segmentCoords = [];
        if (endIdx < startIdx) {
            segmentCoords = coords.slice(startIdx);
        } else {
            segmentCoords = coords.slice(startIdx, endIdx + 1);
        }

        if (segmentCoords.length > 1) {
            const d = 'M ' + segmentCoords.map(p => {
                const xy = project(p[0], p[1]);
                return `${xy[0]},${xy[1]}`;
            }).join(' L ');

            // Determine Color
            let color = '#555'; // Base Neutral
            let stroke = 6;

            // Logic: Compare targetLap sector time vs bestSectors
            if (targetLap && bestSectors && targetLap.sectors && targetLap.sectors[i] && bestSectors[i]) {
                const actual = targetLap.sectors[i];
                const best = bestSectors[i];
                const delta = actual - best;

                if (delta <= 0.05) color = '#4caf50';
                else if (delta <= 0.3) color = '#ffeb3b';
                else color = '#f44336';

                if (delta > 0.5) stroke = 8;
            }

            svgPaths += `<path d="${d}" fill="none" stroke="${color}" stroke-width="${stroke}" stroke-linecap="round" stroke-linejoin="round" />`;

            // Label
            const midIdx = Math.floor(segmentCoords.length / 2);
            const midPt = project(segmentCoords[midIdx][0], segmentCoords[midIdx][1]);
            labels += `<text x="${midPt[0]}" y="${midPt[1]}" fill="#aaa" font-size="16" font-weight="bold" text-anchor="middle" dy="-10">S${i + 1}</text>`;
        }

        startIdx = endIdx;
    }

    // Legend Logic
    let legend = '';
    if (targetLap) {
        legend = `
             <div style="display:flex; justify-content:center; gap:1rem; margin-top:0.5rem; font-size:0.9rem; color:#aaa;">
                <span style="color:#4caf50">● Optimal</span>
                <span style="color:#ffeb3b">● <0.3s Loss</span>
                <span style="color:#f44336">● >0.3s Loss</span>
             </div>`;
    }

    const svgBlock = `
        <svg viewBox="0 0 ${w} ${h}" style="width:100%; height:auto; max-height: 500px;">
            ${svgPaths}
            <circle cx="${startPt[0]}" cy="${startPt[1]}" r="8" fill="#fff" stroke="#000" stroke-width="2"/>
            <text x="${startPt[0]}" y="${startPt[1]}" dy="25" text-anchor="middle" fill="#fff" font-size="14">S/F</text>
            ${labels}
        </svg>
        ${legend}
    `;

    // Collapsible Wrapper or Standard
    if (options.collapsible) {
        return `
            <details style="background:var(--surface); border:1px solid var(--border); border-radius:8px; margin:1rem 0;">
                <summary style="padding:1rem; cursor:pointer; font-weight:bold;">${options.title || 'Track Map'}</summary>
                <div style="padding:0 1rem 1rem 1rem;">
                    ${svgBlock}
                </div>
            </details>
        `;
    }

    return `
        <div style="background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:1rem; margin:1rem 0;">
            ${options.title ? `<h3 style="margin:0 0 1rem 0;">${options.title}</h3>` : ''}
            ${svgBlock}
        </div>
    `;
}

// ============================================================================
// COMPARATIVE ANALYSIS (PHASE 7.4.3)
// ============================================================================

let currentComparisonData = null;

async function initComparison(session) {
    const container = document.getElementById('comparisonContainer');
    if (!container) return;

    // Populate Dropdowns
    const laps = session.laps.filter(l => l.valid !== false);

    const opts = laps.map(l =>
        `<option value="${l.lap_number}">Lap ${l.lap_number} (${formatTime(l.lap_time)})</option>`
    ).join('') + `<option value="optimal">Session Optimal (TBL)</option>`;

    // Find Best Lap
    let bestLap = null;
    let minTime = Infinity;
    laps.forEach(l => {
        if (l.lap_time > 0 && l.lap_time < minTime) {
            minTime = l.lap_time;
            bestLap = l;
        }
    });

    container.innerHTML = `
        <div class="card" style="margin-top: 2rem;">
            <h3>Comparative Analysis (Ghost Lap)</h3>
            <div class="analysis-controls" style="display:flex; gap:1rem; align-items:center; flex-wrap:wrap; margin-bottom:1rem;">
                <div>
                    <label class="help-text">Reference (Green)</label>
                    <select id="compRefLap" class="modal-input" style="width: auto;">
                        ${opts}
                    </select>
                </div>
                <div style="font-weight:bold; color:#666;">VS</div>
                <div>
                    <label class="help-text">Target (Red)</label>
                    <select id="compTargetLap" class="modal-input" style="width: auto;">
                        ${opts}
                    </select>
                </div>
                <button class="btn small" onclick="runComparison('${session.meta.session_id}')">Analyze</button>
            </div>
            
            <div id="compStatus" class="help-text">Select laps and click Analyze</div>
            
            <div id="compResults" style="display:none; margin-top:2rem;">
                <!-- Delta Chart -->
                <h4>Time Delta (Over Distance)</h4>
                <div id="deltaChart" style="width:100%; height:150px; background:var(--surface); border:1px solid var(--border); border-radius:8px;"></div>
                <p class="help-text" style="text-align:center; margin-top:0.5rem; margin-bottom:2rem;">
                    <span style="color:#f44336">Curve UP: Target Slower (Loss)</span> • 
                    <span style="color:#4caf50">Curve DOWN: Target Faster (Gain)</span>
                </p>
                
                <!-- Ghost Map Replay -->
                <h4>Ghost Lap Replay</h4>
                <div style="display: flex; gap: 1rem; flex-wrap: wrap;">
                    <!-- Map Container -->
                    <div id="replayMap" style="flex: 1 1 300px; height: 300px; background:var(--surface); border:1px solid var(--border); border-radius:8px; position: relative;"></div>
                    
                    <!-- Controls -->
                    <div style="flex: 1 1 200px; display: flex; flex-direction: column; gap: 1rem;">
                        <div class="stat-card">
                            <div class="stat-value" id="replayTime">0.0s</div>
                            <div class="stat-label">Elapsed Time</div>
                        </div>
                        <div class="stat-card">
                             <div class="stat-value" id="replayGap">0.00s</div>
                             <div class="stat-label">Live Gap (Ref - Tgt)</div>
                        </div>
                        
                        <div style="display:flex; align-items:center; gap:0.5rem;">
                            <button id="btnPlay" class="btn small" onclick="toggleReplay()">Play</button>
                            <input type="range" id="replaySlider" min="0" max="100" value="0" step="0.1" style="flex-grow:1" oninput="seekReplay(this.value)">
                        </div>
                        <div style="text-align: center; font-size: 0.9em;">
                            <span style="color:#4CAF50">● Reference</span> vs <span style="color:#F44336">● Target</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    // Set defaults
    if (bestLap) {
        document.getElementById('compRefLap').value = bestLap.lap_number;
    }
    if (laps.length > 0) {
        document.getElementById('compTargetLap').value = laps[laps.length - 1].lap_number;
    }
}

async function runComparison(sessionId) {
    const ref = document.getElementById('compRefLap').value;
    const target = document.getElementById('compTargetLap').value;
    const status = document.getElementById('compStatus');
    const results = document.getElementById('compResults');

    status.innerText = "Analyzing telemetry...";

    try {
        const res = await apiCall(`/api/sessions/${sessionId}/compare?lap1=${ref}&lap2=${target}`);
        currentComparisonData = res.data;

        status.innerText = "";
        results.style.display = "block";

        // Setup Replay
        initReplayMap(res.data);

        // Draw Chart
        setTimeout(() => {
            drawDeltaChart(res.data);
        }, 50);

    } catch (e) {
        // Handle server errors cleanly
        let msg = e.message;
        if (e.error) msg = e.error; // If JSON response
        status.innerHTML = `<span style="color:red">Analysis failed: ${msg}</span>`;
    }
}

// --------------------------------------------------------
// REPLAY LOGIC
// --------------------------------------------------------
let replayTimer = null;
let replayState = {
    duration: 0,
    currentTime: 0,
    playing: false,
    project: null
};

function initReplayMap(data) {
    const container = document.getElementById('replayMap');
    const slider = document.getElementById('replaySlider');
    if (!container || !data.lat || !data.lat.length) return;

    // 1. Calculate Bounds
    const lats = data.lat;
    const lons = data.lon;
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    const minLon = Math.min(...lons);
    const maxLon = Math.max(...lons);

    // 2. Setup Projection
    const w = container.offsetWidth || 300;
    const h = container.offsetHeight || 300;
    const pad = 20;

    const latRange = maxLat - minLat || 0.0001;
    const lonRange = maxLon - minLon || 0.0001;

    // Aspect Ratio lock
    const scaleX = (w - 2 * pad) / lonRange;
    const scaleY = (h - 2 * pad) / latRange;
    const scale = Math.min(scaleX, scaleY); // Uniform scale

    // Center it
    const cx = pad + (w - 2 * pad - lonRange * scale) / 2;
    const cy = pad + (h - 2 * pad - latRange * scale) / 2;

    const project = (lat, lon) => {
        const x = cx + (lon - minLon) * scale;
        const y = h - (cy + (lat - minLat) * scale); // Invert Y
        return [x, y];
    };
    replayState.project = project;

    // 3. Draw Path
    let d = `M ${project(lats[0], lons[0]).join(' ')}`;
    for (let i = 1; i < lats.length; i++) {
        d += ` L ${project(lats[i], lons[i]).join(' ')}`;
    }

    container.innerHTML = `
        <svg width="100%" height="100%" viewBox="0 0 ${w} ${h}">
            <path d="${d}" fill="none" stroke="#444" stroke-width="3" />
            <!-- Dots -->
            <circle id="ghostRefDot" r="6" fill="#4CAF50" stroke="#fff" stroke-width="1" cx="-10" cy="-10" />
            <circle id="ghostTargetDot" r="6" fill="#F44336" stroke="#fff" stroke-width="1" cx="-10" cy="-10" />
        </svg>
    `;

    // 4. Reset State
    const maxTime = Math.max(data.ref_time[data.ref_time.length - 1], data.target_time[data.target_time.length - 1]);
    replayState.duration = maxTime;
    replayState.currentTime = 0;
    slider.max = maxTime;
    slider.value = 0;

    updateReplayVisuals(0);
}

function toggleReplay() {
    const btn = document.getElementById('btnPlay');
    if (replayState.playing) {
        // Pause
        replayState.playing = false;
        btn.innerText = "Play";
        if (replayTimer) cancelAnimationFrame(replayTimer);
    } else {
        // Play
        replayState.playing = true;
        btn.innerText = "Pause";

        let lastTs = performance.now();

        const loop = (ts) => {
            if (!replayState.playing) return;

            const dt = (ts - lastTs) / 1000; // seconds
            lastTs = ts;

            // Advance time
            replayState.currentTime += dt; // Realtime speed
            // Optional: speed multiplier? replayState.currentTime += dt * 2;

            if (replayState.currentTime >= replayState.duration) {
                replayState.currentTime = 0; // Loop? Or Stop?
                // Let's Loop
            }

            document.getElementById('replaySlider').value = replayState.currentTime;
            updateReplayVisuals(replayState.currentTime);

            replayTimer = requestAnimationFrame(loop);
        };
        replayTimer = requestAnimationFrame(loop);
    }
}

function seekReplay(val) {
    replayState.currentTime = parseFloat(val);
    updateReplayVisuals(replayState.currentTime);
}

function updateReplayVisuals(time) {
    const data = currentComparisonData;
    if (!data) return;

    document.getElementById('replayTime').innerText = time.toFixed(1) + "s";

    // Find Indices
    // Optimization: Binary search is better, but array is small (~2000), linear find is ok or cached index
    // Let's stick to simple find for now
    let idxRef = data.ref_time.findIndex(t => t >= time);
    if (idxRef === -1) idxRef = data.ref_time.length - 1;

    let idxTgt = data.target_time.findIndex(t => t >= time);
    if (idxTgt === -1) idxTgt = data.target_time.length - 1;

    // Update Dots
    const pRef = replayState.project(data.lat[idxRef], data.lon[idxRef]);
    const pTgt = replayState.project(data.lat[idxTgt], data.lon[idxTgt]);

    const dotRef = document.getElementById('ghostRefDot');
    const dotTgt = document.getElementById('ghostTargetDot');

    if (dotRef) { dotRef.setAttribute('cx', pRef[0]); dotRef.setAttribute('cy', pRef[1]); }
    if (dotTgt) { dotTgt.setAttribute('cx', pTgt[0]); dotTgt.setAttribute('cy', pTgt[1]); }

    // Update Gap
    // Gap = Target Time - Ref Time (at this distance)
    // Wait, we are at time t.
    // We want the gap at the current location of the REFERENCE.
    // Ref is at Distance D at time t. Which time did Target cross Distance D?
    // This requires distance-based lookup, not time-based.
    // Luckily indices are aligned by distance!
    // At index idxRef (Ref location), the Time Delta is data.delta_time[idxRef]

    const gap = data.delta_time[idxRef];
    const gapEl = document.getElementById('replayGap');
    if (gapEl && gap !== undefined) {
        const sign = gap > 0 ? "+" : "";
        const color = gap > 0 ? "#F44336" : "#4CAF50"; // Red if slower (+), Green if faster (-)
        gapEl.innerHTML = `<span style="color:${color}">${sign}${gap.toFixed(2)}s</span>`;
    }
}


function drawDeltaChart(data) {
    const container = document.getElementById('deltaChart');
    if (!container) return;
    const w = container.offsetWidth;
    const h = container.offsetHeight;
    const pad = 30;

    // Unpack
    const dist = data.distance; // X
    const delta = data.delta_time; // Y

    if (!dist || dist.length === 0) return;

    // Bounds
    let maxDelta = 0;
    delta.forEach(d => { if (Math.abs(d) > maxDelta) maxDelta = Math.abs(d); });
    if (maxDelta === 0) maxDelta = 1; // Avoid divide by zero

    const maxX = Math.max(...dist);

    // Scale Functions
    const scaleX = (x) => pad + (x / maxX) * (w - 2 * pad);
    // Y: Center is h/2. Positive (Loss) is UP (y < h/2). Negative (Gain) is DOWN (y > h/2).
    // We want +Delta (Slower) to be HIGHER visually.
    const scaleY = (y) => (h / 2) - (y / maxDelta) * (h / 2 - pad);

    // Build Path
    let pathD = `M ${scaleX(dist[0])} ${scaleY(delta[0])}`;
    for (let i = 1; i < dist.length; i++) {
        pathD += ` L ${scaleX(dist[i])} ${scaleY(delta[i])}`;
    }

    // Zero line
    const y0 = scaleY(0);
    const zeroLine = `M ${pad} ${y0} L ${w - pad} ${y0}`;

    container.innerHTML = `
        <svg width="${w}" height="${h}">
            <!-- Grid / Zero Line -->
            <path d="${zeroLine}" stroke="#555" stroke-width="1" stroke-dasharray="4"/>
            
            <!-- Data Path -->
            <path d="${pathD}" fill="none" stroke="#2196F3" stroke-width="2" />
            
            <!-- Hover Target (Overlay) -->
            <!-- Optional: Could add vertical line on hover -->
            
            <!-- Labels -->
            <text x="${w - pad}" y="${y0 - 5}" fill="#aaa" text-anchor="end" font-size="10">0.0s</text>
            <text x="${w - pad}" y="${pad}" fill="#f44336" text-anchor="end" font-size="10">+${maxDelta.toFixed(2)}s</text>
            <text x="${w - pad}" y="${h - pad}" fill="#4caf50" text-anchor="end" font-size="10">-${maxDelta.toFixed(2)}s</text>
            
            <text x="${w / 2}" y="${h - 5}" fill="#aaa" text-anchor="middle" font-size="10">Distance (m)</text>
        </svg>
    `;
}

// ----------------------------------------------------------------------------
// UTILITY
// ----------------------------------------------------------------------------

function renderEmptyState(icon, title, message, actionText = null, actionFn = null) {
    return `
        <div class="empty-state">
            <div class="empty-state-icon">${icon}</div>
            <div class="empty-state-title">${title}</div>
            <div class="empty-state-message">${message}</div>
            ${actionText && actionFn ? `<button class="btn btn-primary" onclick="${actionFn}">${actionText}</button>` : ''}
        </div>
    `;
}

function renderSkeletonCards(count = 3, type = 'session') {
    const skeletons = [];
    for (let i = 0; i < count; i++) {
        if (type === 'session') {
            skeletons.push(`
                <div class="skeleton-card">
                    <div class="skeleton skeleton-line title"></div>
                    <div class="skeleton skeleton-line subtitle"></div>
                    <div style="display: flex; gap: 1rem; margin-top: 1rem;">
                        <div class="skeleton skeleton-line short"></div>
                        <div class="skeleton skeleton-line short"></div>
                        <div class="skeleton skeleton-line short"></div>
                    </div>
                </div>
            `);
        } else if (type === 'track') {
            skeletons.push(`
                <div class="skeleton-card" style="min-height: 200px;">
                    <div class="skeleton skeleton-image"></div>
                    <div class="skeleton skeleton-line title"></div>
                    <div class="skeleton skeleton-line subtitle"></div>
                </div>
            `);
        } else if (type === 'table-row') {
            skeletons.push(`
                <tr>
                    <td><div class="skeleton skeleton-line short" style="margin: 0;"></div></td>
                    <td><div class="skeleton skeleton-line medium" style="margin: 0;"></div></td>
                    <td><div class="skeleton skeleton-line short" style="margin: 0;"></div></td>
                </tr>
            `);
        }
    }
    return skeletons.join('');
}

async function promptRenameSession(sessionId, currentName) {
    const newName = prompt("Enter new session name:", currentName);
    if (newName && newName !== currentName) {
        try {
            await apiCall(`/api/sessions/${sessionId}/rename`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_name: newName })
            });
            showToast("Session renamed!", "success");

            // Allow DB update time roughly
            setTimeout(() => {
                viewSession(sessionId);
            }, 200);
        } catch (e) {
            showToast("Rename failed: " + e.message, "error");
        }
    }
}

// Phase 8: Diagnostics UI
function generateDiagnosticsPanel(session) {
    if (!session.analysis || !session.analysis.diagnostics) return '';
    const d = session.analysis.diagnostics;
    if (d.error) return ''; // Fail silently or show error?

    // Color Logic for Consistency
    let scoreColor = '#4CAF50';
    if (d.consistency_score < 90) scoreColor = '#FFC107'; // Amber
    if (d.consistency_score < 75) scoreColor = '#F44336'; // Red

    // Hotspots List
    const hotspots = d.variance_hotspots || [];
    const hotspotHTML = hotspots.map(h => `
        <div class="hotspot-item" style="background: rgba(255, 193, 7, 0.1); padding: 0.5rem; border-radius: 4px; border-left: 3px solid #ffc107; margin-bottom: 0.5rem;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: bold;">${h.sector_label}</span>
                <span style="font-family: monospace; color: #ffc107;">Cv: ${h.cv_percent}%</span>
            </div>
            <div style="font-size: 0.8em; opacity: 0.8;">High Variance detected</div>
        </div>
    `).join('');

    const id = 'diag-' + Math.random().toString(36).substr(2, 9);

    return `
        <div class="card" style="margin-bottom: 2rem; border-left: 4px solid ${scoreColor};">
            <div class="card-header" style="cursor: pointer;" onclick="document.getElementById('${id}').style.display = document.getElementById('${id}').style.display === 'none' ? 'grid' : 'none'">
                <div style="display: flex; align-items: center; gap: 1rem;">
                    <h3 style="margin: 0;">Session Diagnostics</h3>
                    <span class="badge" style="background: ${scoreColor}22; color: ${scoreColor}; border: 1px solid ${scoreColor};">
                        ${d.consistency_label || 'Analysis'}
                    </span>
                </div>
                <span style="font-size: 1.5em; opacity: 0.5;">▾</span>
            </div>
            
            <div id="${id}" style="display: none; grid-template-columns: 1fr 2fr; gap: 2rem; align-items: start; margin-top: 1rem; border-top: 1px solid var(--border); padding-top: 1rem;">
                <!-- Left: Score -->
                <div style="text-align: center;">
                    <div style="font-size: 3em; font-weight: bold; color: ${scoreColor}; line-height: 1;">
                        ${d.consistency_score !== null ? d.consistency_score : '--'}
                    </div>
                    <div style="font-size: 0.9em; opacity: 0.7;">Consistency Score</div>
                </div>

                <!-- Right: Hotspots -->
                <div>
                    <h4 style="margin-top: 0; margin-bottom: 0.5rem; font-size: 0.9em; text-transform: uppercase; color: var(--text-secondary);">Variance Hotspots</h4>
                    ${hotspots.length ? hotspotHTML : '<div class="help-text">No significant variance detected. Good consistency!</div>'}
                </div>
            </div>
        </div>
    `;
}

// Fixed (always visible) version of diagnostics panel
function generateDiagnosticsPanelFixed(session) {
    if (!session.analysis || !session.analysis.diagnostics) return '';
    const d = session.analysis.diagnostics;
    if (d.error) return '';

    // Color Logic for Consistency
    let scoreColor = '#4CAF50';
    if (d.consistency_score < 90) scoreColor = '#FFC107';
    if (d.consistency_score < 75) scoreColor = '#F44336';

    // Hotspots List
    const hotspots = d.variance_hotspots || [];
    const hotspotHTML = hotspots.length > 0 ? hotspots.map(h => `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0.75rem; background: rgba(255, 193, 7, 0.08); border-radius: 6px; border-left: 3px solid #ffc107;">
            <span style="font-weight: 600;">${h.sector_label}</span>
            <span style="font-family: monospace; color: #ffc107; font-size: 0.85rem;">CV: ${h.cv_percent}%</span>
        </div>
    `).join('') : '<div class="help-text" style="text-align: center; padding: 1rem;">✓ No significant variance detected. Good consistency!</div>';

    return `
        <div class="card" style="margin-bottom: 1.5rem; border-left: 4px solid ${scoreColor};">
            <h3 style="margin: 0 0 1rem 0; display: flex; align-items: center; justify-content: space-between;">
                <span style="display: flex; align-items: center; gap: 0.5rem;">
                    <span style="color: ${scoreColor};">🎯</span> Session Diagnostics
                </span>
                <span class="badge" style="background: ${scoreColor}15; color: ${scoreColor}; border: 1px solid ${scoreColor}; padding: 0.25rem 0.75rem; border-radius: 12px; font-size: 0.8rem;">
                    ${d.consistency_label || 'Analysis'}
                </span>
            </h3>
            
            <div style="display: grid; grid-template-columns: auto 1fr; gap: 2rem; align-items: start;">
                <!-- Left: Score -->
                <div style="text-align: center; padding: 1rem; background: ${scoreColor}10; border-radius: 8px; min-width: 120px;">
                    <div style="font-size: 2.5em; font-weight: bold; color: ${scoreColor}; line-height: 1;">
                        ${d.consistency_score !== null ? d.consistency_score : '--'}
                    </div>
                    <div style="font-size: 0.8em; opacity: 0.7; margin-top: 0.25rem;">Consistency</div>
                </div>

                <!-- Right: Hotspots -->
                <div>
                    <h4 style="margin: 0 0 0.75rem 0; font-size: 0.85em; text-transform: uppercase; color: var(--text-secondary); letter-spacing: 0.5px;">Variance Hotspots</h4>
                    <div style="display: flex; flex-direction: column; gap: 0.5rem;">
                        ${hotspotHTML}
                    </div>
                </div>
            </div>
        </div>
    `;
}

// Sector Comparison Chart - Visual bar chart comparing sectors across laps
function generateSectorComparisonChart(laps, sectorCount, sectorBests) {
    if (!laps || laps.length < 2) return '';

    const validLaps = laps.filter(l => l.valid && l.lap_time > 0).slice(0, 10); // Limit to 10 laps for readability
    if (validLaps.length === 0) return '';

    const chartWidth = 700;
    const chartHeight = 200;
    const barHeight = 20;
    const gap = 8;
    const labelWidth = 50;
    const legendWidth = 80;

    // Color palette for sectors
    const sectorColors = ['#ff6b35', '#4CAF50', '#2196F3', '#9C27B0', '#FF9800', '#00BCD4', '#E91E63'];

    // Find max lap time for scaling
    const maxLapTime = Math.max(...validLaps.map(l => l.lap_time));

    // Generate bars
    const bars = validLaps.map((lap, i) => {
        const y = i * (barHeight + gap) + 30;
        let xOffset = labelWidth;

        const segments = lap.sector_times.map((t, si) => {
            const width = (t / maxLapTime) * (chartWidth - labelWidth - legendWidth);
            const segment = `<rect x="${xOffset}" y="${y}" width="${width}" height="${barHeight}" fill="${sectorColors[si % sectorColors.length]}" rx="2"/>`;
            xOffset += width;
            return segment;
        }).join('');

        const lapLabel = `<text x="5" y="${y + barHeight - 5}" font-size="12" fill="#aaa">Lap ${lap.lap_number}</text>`;
        const timeLabel = `<text x="${chartWidth - 5}" y="${y + barHeight - 5}" font-size="11" fill="#fff" text-anchor="end" font-family="monospace">${formatTime(lap.lap_time)}</text>`;
        const isBest = lap.is_session_best ? `<text x="${chartWidth - 70}" y="${y + barHeight - 5}" font-size="10" fill="#4CAF50">★</text>` : '';

        return lapLabel + segments + timeLabel + isBest;
    }).join('');

    // Legend
    const legend = Array(sectorCount).fill(0).map((_, i) => {
        const x = labelWidth + i * 60;
        return `<rect x="${x}" y="8" width="12" height="12" fill="${sectorColors[i % sectorColors.length]}" rx="2"/>
                <text x="${x + 16}" y="18" font-size="10" fill="#aaa">S${i + 1}</text>`;
    }).join('');

    const svgHeight = validLaps.length * (barHeight + gap) + 40;

    return `
        <div class="card" style="margin-bottom: 1.5rem;">
            <h3 style="margin: 0 0 1rem 0; display: flex; align-items: center; gap: 0.5rem;">
                <span style="color: var(--primary);">📈</span> Sector Comparison
            </h3>
            <div style="overflow-x: auto;">
                <svg width="${chartWidth}" height="${svgHeight}" style="min-width: ${chartWidth}px;">
                    ${legend}
                    ${bars}
                </svg>
            </div>
        </div>
    `;
}

// Save session notes
async function saveSessionNotes(sessionId) {
    const textarea = document.getElementById('sessionNotes');
    if (!textarea) return;

    const notes = textarea.value;

    try {
        await apiCall(`/api/sessions/${sessionId}/notes`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ notes })
        });
        showToast('Notes saved', 'success');
    } catch (error) {
        console.error('Failed to save notes:', error);
        // Don't show error toast - might not have endpoint yet
    }
}

// ----------------------------------------------------------------------------
// RAW FILE VIEW (Phase 8 Extension)
// ===========================================
async function viewRawFile(filename) {
    const modal = document.getElementById('rawFileModal');
    const title = document.getElementById('rawFileTitle');
    const content = document.getElementById('rawFileContent');

    title.textContent = `Raw View: ${filename}`;
    content.innerHTML = '<span style="color:#888">Loading...</span>'; // Use innerHTML
    modal.classList.add('active');

    try {
        const res = await apiCall(`/api/learning/${filename}/raw?lines=100`);
        if (res.error) {
            content.textContent = "Error: " + res.error;
            content.style.color = "var(--error)";
            return;
        }

        // Colorization Logic
        const lines = res.lines;
        if (!lines || lines.length === 0) {
            content.textContent = "Empty File";
            return;
        }

        // 1. Process Header
        const headerLine = lines[0].trim();
        const headers = headerLine.split(',');

        let html = `<div style="margin-bottom:0.5rem; border-bottom:1px solid #333; padding-bottom:0.2rem; color:#fff; font-weight:bold;">${headerLine}</div>`;

        // 2. Process Rows
        for (let i = 1; i < lines.length; i++) {
            const line = lines[i].trim();
            if (!line) continue;

            const vals = line.split(',');
            const rowHtml = vals.map((val, idx) => {
                const header = headers[idx] ? headers[idx].toLowerCase().trim() : '';
                let color = '#ccc'; // Default

                if (header.includes('timestamp') || header.includes('time')) color = '#888'; // Gray
                else if (header.includes('lat') || header.includes('lon')) color = '#0ff'; // Cyan
                else if (header.includes('speed')) color = '#0f0'; // Green
                else if (header.includes('imu') || header.includes('accel') || header.includes('gyro')) color = '#f90'; // Orange
                else if (header.includes('sat')) color = '#ff0'; // Yellow

                return `<span style="color:${color}">${val}</span>`;
            }).join('<span style="color:#444">,</span> '); // Dim commas

            html += `<div>${rowHtml}</div>`;
        }

        content.innerHTML = html;
        content.style.color = ""; // Reset base color

    } catch (e) {
        content.textContent = "Request Failed";
        content.style.color = "var(--error)";
    }
}

function closeRawFileModal() {
    document.getElementById('rawFileModal').classList.remove('active');
}


// ===========================================
// GEO PATH VISUALIZATION
// ===========================================
async function viewGeoPath(filename) {
    const modal = document.getElementById('geoModal');
    const svg = document.getElementById('geoSvg');
    const stats = document.getElementById('geoStats');

    document.getElementById('geoTitle').textContent = `Path: ${filename}`;
    stats.textContent = "Loading...";
    svg.innerHTML = '';
    modal.classList.add('active');

    try {
        const res = await apiCall(`/api/learning/${filename}/geo`);
        if (res.error) {
            stats.textContent = "Error: " + res.error;
            stats.style.color = "var(--error)";
            return;
        }

        const points = res.points;
        if (!points || points.length < 2) {
            stats.textContent = "Not enough GPS data points.";
            return;
        }

        // Normalize
        const lats = points.map(p => p[0]);
        const lons = points.map(p => p[1]);
        const minLat = Math.min(...lats);
        const maxLat = Math.max(...lats);
        const minLon = Math.min(...lons);
        const maxLon = Math.max(...lons);

        // Scaling to 400x300 box with room for axes
        const w = 400, h = 300;
        const padL = 50, padR = 20, padT = 20, padB = 30;

        const latDiff = maxLat - minLat || 0.0001;
        const lonDiff = maxLon - minLon || 0.0001;

        // Aspect Ratio Correction
        const avgLatRad = (minLat + maxLat) / 2 * (Math.PI / 180);
        const mPerDegLon = 111139 * Math.cos(avgLatRad);
        const mPerDegLat = 111139;

        const totalWidthMeters = lonDiff * mPerDegLon;
        const totalHeightMeters = latDiff * mPerDegLat;

        // Determine drawing scale to fit in box while maintaining aspect ratio
        const drawW = w - padL - padR;
        const drawH = h - padT - padB;

        // Scale factors (Pixels per Degree)
        let scaleX_deg = drawW / lonDiff;
        let scaleY_deg = drawH / latDiff;

        // Correct aspect ratio by limiting the larger scale to match real world
        // Aspect ratio of data (Width/Height in meters)
        const dataAspect = totalWidthMeters / totalHeightMeters;
        const screenAspect = drawW / drawH;

        if (dataAspect > screenAspect) {
            // Limited by width, reduce Y scale (add vertical padding)
            scaleY_deg = scaleX_deg * (mPerDegLon / mPerDegLat); // Match pixel/meter ratio
        } else {
            // Limited by height, reduce X scale
            scaleX_deg = scaleY_deg * (mPerDegLat / mPerDegLon);
        }

        // Project Function: Lon/Lat -> Pixels
        const projectX = (lon) => padL + (lon - minLon) * scaleX_deg;
        const projectY = (lat) => h - padB - (lat - minLat) * scaleY_deg; // Invert Y

        const pathData = points.map((p, i) => {
            const cmd = i === 0 ? 'M' : 'L';
            return `${cmd} ${projectX(p[1])},${projectY(p[0])}`;
        }).join(' ');

        // AXES & TICKS
        // Select good tick interval (e.g. 10m, 50m, 100m)
        const maxDist = Math.max(totalWidthMeters, totalHeightMeters);
        const magnitudes = [1, 5, 10, 25, 50, 100, 200, 500, 1000, 2000, 5000];
        let tickStep = magnitudes[0];
        for (let m of magnitudes) {
            if (maxDist / m < 8) { // Aim for max 8 ticks
                tickStep = m;
                break;
            }
            tickStep = m;
        }

        let axesSvg = '';

        // X Steps
        for (let m = 0; m <= totalWidthMeters; m += tickStep) {
            const px = padL + (m / totalWidthMeters) * (totalWidthMeters / mPerDegLon) * scaleX_deg;
            if (px > w - padR) break;
            axesSvg += `
                <line x1="${px}" y1="${h - padB}" x2="${px}" y2="${h - padB + 5}" stroke="#666" />
                <text x="${px}" y="${h - padB + 16}" font-size="10" fill="#888" text-anchor="middle">${Math.round(m)}m</text>
                <line x1="${px}" y1="${padT}" x2="${px}" y2="${h - padB}" stroke="#333" stroke-dasharray="2,4" opacity="0.3" />
             `;
        }

        // Y Steps
        for (let m = 0; m <= totalHeightMeters; m += tickStep) {
            const py = h - padB - (m / totalHeightMeters) * (totalHeightMeters / mPerDegLat) * scaleY_deg;
            if (py < padT) break;
            axesSvg += `
                <line x1="${padL - 5}" y1="${py}" x2="${padL}" y2="${py}" stroke="#666" />
                <text x="${padL - 8}" y="${py + 3}" font-size="10" fill="#888" text-anchor="end">${Math.round(m)}m</text>
                <line x1="${padL}" y1="${py}" x2="${w - padR}" y2="${py}" stroke="#333" stroke-dasharray="2,4" opacity="0.3" />
             `;
        }

        // Draw Frame
        svg.innerHTML = `
            <!-- Grid & Axes -->
            ${axesSvg}
            <line x1="${padL}" y1="${h - padB}" x2="${w - padR}" y2="${h - padB}" stroke="#666" /> <!-- X Axis -->
            <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${h - padB}" stroke="#666" /> <!-- Y Axis -->

            <!-- Path -->
            <path d="${pathData}" fill="none" stroke="var(--primary)" stroke-width="2" />
            
            <!-- Endpoints -->
            <circle cx="${projectX(lons[0])}" cy="${projectY(lats[0])}" r="4" fill="#4CAF50" title="Start" />
            <circle cx="${projectX(lons[lons.length - 1])}" cy="${projectY(lats[lats.length - 1])}" r="4" fill="#F44336" title="End" />
        `;

        stats.textContent = `Points: ${points.length} (Sampled from ${res.total_recorded})`;
        stats.style.color = "var(--text-dim)";

    } catch (e) {
        stats.textContent = "Request Failed";
        stats.style.color = "var(--error)";
    }
}

function closeGeoModal() {
    document.getElementById('geoModal').classList.remove('active');
}

// ============================================================================
// LIVE TELEMETRY PLAYBACK
// ============================================================================

let pbState = {
    active: false,
    playing: false,
    data: null,
    session: null,
    currentIndex: 0,
    startTime: 0,
    duration: 0,
    laps: [],

    // Canvas
    canvas: null,
    ctx: null,
    scale: 1,
    offsetX: 0,
    offsetY: 0,
    width: 0,
    height: 0,

    // Heatmap Cache
    pathCache: null,
    mapMode: 'speed', // speed, accel, clean
    bounds: null
};

async function openPlayback(sessionId, shareToken = null) {
    const modal = document.getElementById('playbackModal');

    // 1. Reset State
    pbState = {
        ...pbState,
        active: true,
        playing: false,
        currentIndex: 0,
        mapMode: 'speed'
    };

    // 2. Show Modal (Loading)
    modal.classList.add('active');
    document.getElementById('pbPlayPause').textContent = '...';

    try {
        // 3. Fetch Data
        let endpoint = `/api/sessions/${sessionId}`;
        let teleEndpoint = `/api/sessions/${sessionId}/telemetry`;

        if (shareToken) {
            endpoint = `/api/shared/${shareToken}`;
            teleEndpoint = `/api/shared/${shareToken}/telemetry`;
        }

        const [session, telemetry] = await Promise.all([
            apiCall(endpoint),
            apiCall(teleEndpoint)
        ]);

        pbState.session = session;
        pbState.data = telemetry;
        pbState.laps = session.laps;

        // Load Annotations
        loadAnnotations(sessionId);

        if (telemetry.time && telemetry.time.length > 0) {
            pbState.duration = telemetry.time[telemetry.time.length - 1] - telemetry.time[0];
            pbState.startTime = telemetry.time[0];
        } else {
            throw new Error("Telemetry data empty or format invalid");
        }

        // 4. Init UI
        initPlaybackUI();

        // 5. Pre-calculate Map
        fitTrackMap();

        // 6. Ready
        togglePlayback(true);

    } catch (e) {
        console.error(e);
        closePlaybackModal();
        showToast("Playback Unavailable: " + e.message, "error");
    }
}

function closePlaybackModal() {
    pbState.active = false;
    pbState.playing = false;
    document.getElementById('playbackModal').classList.remove('active');
}

function initPlaybackUI() {
    // Canvas
    const container = document.getElementById('pbTrackCanvas').parentElement;
    pbState.canvas = document.getElementById('pbTrackCanvas');
    pbState.ctx = pbState.canvas.getContext('2d');

    // Slider
    const slider = document.getElementById('pbSeek');
    if (pbState.data && pbState.data.time) {
        slider.max = pbState.data.time.length - 1;
        slider.value = 0;
    }

    // Laps Dropdown
    const sel = document.getElementById('pbLapSelect');
    sel.innerHTML = '<option value="all">Session Overview</option>';
    if (pbState.laps) {
        pbState.laps.forEach(l => {
            sel.innerHTML += `<option value="${l.lap_number}">Lap ${l.lap_number} (${formatTime(l.lap_time)})</option>`;
        });
    }

    // Buttons
    document.getElementById('pbPlayPause').textContent = '▶';
}

function fitTrackMap() {
    if (!pbState.data || !pbState.active) return;

    const container = pbState.canvas.parentElement;
    const w = container.clientWidth || 800;
    const h = container.clientHeight || 500;

    pbState.canvas.width = w;
    pbState.canvas.height = h;
    pbState.width = w;
    pbState.height = h;

    // Calculate Bounds
    const lats = pbState.data.lat;
    const lons = pbState.data.lon;
    if (!lats || !lons || lats.length === 0) return;

    let minLat = 90, maxLat = -90, minLon = 180, maxLon = -180;

    // Sampling for performance
    const step = Math.ceil(lats.length / 2000) || 1;
    for (let i = 0; i < lats.length; i += step) {
        if (lats[i] < minLat) minLat = lats[i];
        if (lats[i] > maxLat) maxLat = lats[i];
        if (lons[i] < minLon) minLon = lons[i];
        if (lons[i] > maxLon) maxLon = lons[i];
    }

    if (minLat === maxLat) { minLat -= 0.001; maxLat += 0.001; }
    if (minLon === maxLon) { minLon -= 0.001; maxLon += 0.001; }

    const padding = 20;
    const availW = w - padding * 2;
    const availH = h - padding * 2;

    const latSpan = maxLat - minLat;
    const lonSpan = maxLon - minLon;

    // Aspect Correction
    const latCorrection = Math.cos(minLat * Math.PI / 180);
    const correctedLonSpan = lonSpan * latCorrection;

    const scaleX = availW / correctedLonSpan;
    const scaleY = availH / latSpan;

    pbState.scale = Math.min(scaleX, scaleY);

    const usedW = correctedLonSpan * pbState.scale;
    const usedH = latSpan * pbState.scale;

    pbState.offsetX = padding + (availW - usedW) / 2;
    pbState.offsetY = padding + (availH - usedH) / 2;

    pbState.bounds = { minLat, maxLat, minLon, maxLon, latCorrection };

    renderStaticMap();
}

function project(lat, lon) {
    if (!pbState.bounds) return { x: 0, y: 0 };
    const b = pbState.bounds;

    const x = ((lon - b.minLon) * b.latCorrection * pbState.scale) + pbState.offsetX;
    const y = ((b.maxLat - lat) * pbState.scale) + pbState.offsetY;

    return { x, y };
}

function renderStaticMap() {
    if (!pbState.pathCache) {
        pbState.pathCache = document.createElement('canvas');
    }
    pbState.pathCache.width = pbState.width;
    pbState.pathCache.height = pbState.height;
    const ctx = pbState.pathCache.getContext('2d');

    const data = pbState.data;
    const count = data.lat.length;

    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.lineWidth = 3;

    // Draw segments in chunks
    const step = 1;

    ctx.beginPath();

    // If mapMode is 'clean', we can do one fast stroke
    // If mapMode is 'speed' or 'accel', we need colored segments

    if (pbState.mapMode === 'clean') {
        ctx.strokeStyle = '#555';
        for (let i = 0; i < count - 1; i += 2) { // 2x stride for perf
            const p = project(data.lat[i], data.lon[i]);
            if (i === 0) ctx.moveTo(p.x, p.y);
            else ctx.lineTo(p.x, p.y);
        }
        ctx.stroke();
    } else {
        // Colored segments
        for (let i = 0; i < count - step; i += step) {
            const p1 = project(data.lat[i], data.lon[i]);
            const p2 = project(data.lat[i + step], data.lon[i + step]);

            ctx.beginPath();
            ctx.moveTo(p1.x, p1.y);
            ctx.lineTo(p2.x, p2.y);

            if (pbState.mapMode === 'speed') {
                const s = data.speed[i] || 0;
                ctx.strokeStyle = getHeatmapColor(s, 40, 200);
            } else if (pbState.mapMode === 'accel') {
                const ax = data.aligned_accel_x ? data.aligned_accel_x[i] : (data.ax ? data.ax[i] : 0);
                if (ax > 0.1) ctx.strokeStyle = `rgba(0, 255, 0, ${Math.min(ax / 0.5, 1)})`; // Green
                else if (ax < -0.1) ctx.strokeStyle = `rgba(255, 0, 0, ${Math.min(Math.abs(ax) / 0.8, 1)})`; // Red
                else ctx.strokeStyle = '#444';
            }
            ctx.stroke();
        }
    }
}

function getHeatmapColor(val, min, max) {
    let t = (val - min) / (max - min);
    if (t < 0) t = 0;
    if (t > 1) t = 1;
    // 120 (Green) -> 0 (Red)
    const hue = 120 - (t * 120);
    return `hsl(${hue}, 100%, 50%)`;
}

function updateHeatmapMode() {
    const modes = document.getElementsByName('pbMapMode');
    for (let m of modes) {
        if (m.checked) pbState.mapMode = m.value;
    }
    renderStaticMap();
    if (!pbState.playing) drawFrame();
}

function togglePlayback(forceState = null) {
    if (forceState !== null) pbState.playing = forceState;
    else pbState.playing = !pbState.playing;

    const btn = document.getElementById('pbPlayPause');
    if (btn) btn.textContent = pbState.playing ? '⏸' : '▶';

    if (pbState.playing) {
        pbState.lastTick = performance.now();
        // Initialize playbackTime if needed
        if (pbState.data && pbState.data.time) {
            const t = pbState.data.time[pbState.currentIndex];
            // If undefined or drifted significantly (manual seek), resync
            if (!pbState.playbackTime || Math.abs(pbState.playbackTime - t) > 0.5) {
                pbState.playbackTime = t;
            }
        }
        pbAnimationLoop();
    }
}

function seekPlayback(val) {
    pbState.currentIndex = parseInt(val);
    if (pbState.data && pbState.data.time) {
        pbState.playbackTime = pbState.data.time[pbState.currentIndex];
    }
    drawFrame();
}

function jumpToLap(val) {
    if (val === 'all') {
        pbState.currentIndex = 0;
    } else {
        const lapNum = parseInt(val);
        const lap = pbState.laps.find(l => l.lap_number === lapNum);
        if (lap) {
            const idx = pbState.data.time.findIndex(t => t >= lap.start_time);
            if (idx !== -1) {
                pbState.currentIndex = idx;
                const slider = document.getElementById('pbSeek');
                if (slider) slider.value = idx;
            }
        }
    }
    // Sync Time
    if (pbState.data) pbState.playbackTime = pbState.data.time[pbState.currentIndex];
    drawFrame();
}

function nextLapPlay() {
    const curTime = pbState.data.time[Math.floor(pbState.currentIndex)];
    const curLap = pbState.laps.find(l => curTime >= l.start_time && curTime < (l.start_time + l.lap_time));

    if (curLap) {
        const nextLapNum = curLap.lap_number + 1;
        const nextLap = pbState.laps.find(l => l.lap_number === nextLapNum);
        if (nextLap) {
            const idx = pbState.data.time.findIndex(t => t >= nextLap.start_time);
            if (idx !== -1) pbState.currentIndex = idx;
        } else {
            pbState.currentIndex = 0;
            togglePlayback(false);
        }
    } else {
        jumpToLap(1);
    }
    // Sync Time
    if (pbState.data) pbState.playbackTime = pbState.data.time[pbState.currentIndex];
    drawFrame();
}

function pbAnimationLoop() {
    if (!pbState.active || !pbState.playing) return;

    const now = performance.now();
    const dt = (now - pbState.lastTick) / 1000; // seconds
    pbState.lastTick = now;

    if (dt > 1.0) {
        // Lag spike (e.g. tab background), do not jump
        requestAnimationFrame(pbAnimationLoop);
        return;
    }

    pbState.playbackTime += dt;

    const times = pbState.data.time;
    // Advance index to match playbackTime
    while (pbState.currentIndex < times.length - 1 && times[pbState.currentIndex + 1] <= pbState.playbackTime) {
        pbState.currentIndex++;
    }

    if (pbState.currentIndex >= times.length - 1) {
        pbState.currentIndex = 0;
        pbState.playbackTime = times[0];
    }

    drawFrame();

    const slider = document.getElementById('pbSeek');
    if (slider) slider.value = pbState.currentIndex;

    requestAnimationFrame(pbAnimationLoop);
}

function drawFrame() {
    const i = Math.floor(pbState.currentIndex);
    const data = pbState.data;
    if (!data || !data.lat[i]) return;

    const ctx = pbState.ctx;
    ctx.clearRect(0, 0, pbState.width, pbState.height);

    if (pbState.pathCache) {
        ctx.drawImage(pbState.pathCache, 0, 0);
    }

    const p = project(data.lat[i], data.lon[i]);

    // Dot
    ctx.beginPath();
    ctx.arc(p.x, p.y, 8, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
    ctx.fill();

    ctx.beginPath();
    ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
    ctx.fillStyle = '#fff';
    ctx.fill();

    // Time
    // Time
    const t = data.time[i] - pbState.startTime;
    const timeEl = document.getElementById('pbTime');
    if (timeEl) timeEl.textContent = formatDuration(t);

    // ===== LAP TIME & DELTA =====
    // Find current lap
    let currentLapNum = 1;
    let lapStartTime = pbState.startTime;
    let lapEndTime = null;
    let bestLapTime = null;

    if (pbState.laps && pbState.laps.length > 0) {
        for (let li = 0; li < pbState.laps.length; li++) {
            const lap = pbState.laps[li];
            if (data.time[i] >= lap.start_time && (!lap.end_time || data.time[i] <= lap.end_time)) {
                currentLapNum = lap.lap_number || (li + 1);
                lapStartTime = lap.start_time;
                lapEndTime = lap.end_time;
                break;
            }
        }

        // Find best lap time
        const validLaps = pbState.laps.filter(l => l.lap_time && l.lap_time > 0);
        if (validLaps.length > 0) {
            bestLapTime = Math.min(...validLaps.map(l => l.lap_time));
        }
    }

    // Current lap time
    const currentLapTime = data.time[i] - lapStartTime;
    const lapTimeEl = document.getElementById('pbLapTime');
    if (lapTimeEl) {
        lapTimeEl.textContent = formatLapTime(currentLapTime);
    }

    // Lap number display
    const lapNumEl = document.getElementById('pbLapNumber');
    if (lapNumEl) {
        const totalLaps = pbState.laps ? pbState.laps.length : 1;
        lapNumEl.textContent = `${currentLapNum}/${totalLaps}`;
    }

    // Delta calculation (vs best lap at same distance progress)
    const deltaEl = document.getElementById('pbDeltaText');
    const deltaFillEl = document.getElementById('pbDeltaFill');
    if (deltaEl && deltaFillEl && bestLapTime) {
        // Estimate progress through lap (0-1)
        const lapProgress = lapEndTime ?
            (data.time[i] - lapStartTime) / (lapEndTime - lapStartTime) :
            Math.min(currentLapTime / bestLapTime, 1);

        // Expected time at this progress
        const expectedTime = lapProgress * bestLapTime;
        const delta = currentLapTime - expectedTime;

        // Update display
        deltaEl.textContent = (delta >= 0 ? '+' : '') + delta.toFixed(1) + 's';

        // Color and bar
        const color = delta < 0 ? '#4caf50' : '#f44336';
        deltaFillEl.style.background = color;

        // Width: Map delta to bar (max 3 seconds each direction = 50% width)
        const pct = Math.min(Math.abs(delta) / 3.0, 1) * 50;
        deltaFillEl.style.width = pct + '%';

        // Position: ahead = left of center, behind = right of center
        if (delta < 0) {
            deltaFillEl.style.left = (50 - pct) + '%';
        } else {
            deltaFillEl.style.left = '50%';
        }
    } else if (deltaEl) {
        deltaEl.textContent = '+0.0s';
    }

    // ===== SECTOR TIMES =====
    // For now, show placeholders - sectors need to be defined in track data
    // TODO: Implement sector detection from track definition
    const s1El = document.getElementById('pbS1Time');
    const s2El = document.getElementById('pbS2Time');
    const s3El = document.getElementById('pbS3Time');
    const s1Box = document.getElementById('pbS1');
    const s2Box = document.getElementById('pbS2');
    const s3Box = document.getElementById('pbS3');

    // Simple 3-way split for demo
    if (s1El && s2El && s3El && lapEndTime) {
        const lapDuration = lapEndTime - lapStartTime;
        const s1End = lapStartTime + lapDuration * 0.33;
        const s2End = lapStartTime + lapDuration * 0.66;

        const currentTime = data.time[i];

        // Highlight current sector
        [s1Box, s2Box, s3Box].forEach(b => b.style.borderColor = 'transparent');

        if (currentTime < s1End) {
            const s1Time = currentTime - lapStartTime;
            s1El.textContent = s1Time.toFixed(1);
            s1Box.style.borderColor = '#fff';
            s2El.textContent = '--.-';
            s3El.textContent = '--.-';
        } else if (currentTime < s2End) {
            s1El.textContent = (s1End - lapStartTime).toFixed(1);
            const s2Time = currentTime - s1End;
            s2El.textContent = s2Time.toFixed(1);
            s2Box.style.borderColor = '#fff';
            s3El.textContent = '--.-';
        } else {
            s1El.textContent = (s1End - lapStartTime).toFixed(1);
            s2El.textContent = (s2End - s1End).toFixed(1);
            const s3Time = currentTime - s2End;
            s3El.textContent = s3Time.toFixed(1);
            s3Box.style.borderColor = '#fff';
        }
    }

    // Speed
    const speed = data.speed[i] || 0;
    const speedVal = Math.round(speed);
    const speedEl = document.getElementById('pbSpeed');
    if (speedEl) speedEl.textContent = speedVal;

    // Lean Angle
    // Priority: Explicit Lean > Roll > Derived from Gyro/Speed > 0
    let lean = 0;
    if (data.lean_angle && data.lean_angle[i] !== undefined) {
        lean = data.lean_angle[i];
    } else if (data.roll && data.roll[i] !== undefined) {
        lean = data.roll[i];
    } else if (data.raw_gx && data.raw_gx[i] !== undefined) {
        // Fallback: Estimate lean from gyro X (ROLL axis, not Z which is yaw)
        // Raw gyro values are 16-bit signed, scale by 131 LSB/deg/s for ±250°/s
        const rawGx = data.raw_gx[i];
        const gxScale = Math.abs(rawGx) > 100 ? 131.0 : 1.0; // Auto-detect raw vs scaled
        const rollRate = rawGx / gxScale; // deg/s

        const v = speed / 3.6; // m/s
        const g = 9.81;

        // At steady state: tan(lean) = v * yaw_rate / g
        // But we only have roll rate, so use physics approximation
        // Lean ≈ integrate(roll_rate) with decay, or estimate from speed
        if (speed > 10 && data.raw_gz) {
            // Use yaw rate from GPS heading derivative if available
            const w = data.raw_gz[i] / gxScale * (Math.PI / 180); // rad/s
            const rad = Math.atan((v * w) / g);
            lean = rad * (180 / Math.PI);
        }
    }

    const leanEl = document.getElementById('pbLean');
    if (leanEl) {
        // Show lean with direction indicator
        const leanDir = lean > 0 ? 'R' : (lean < 0 ? 'L' : '');
        leanEl.textContent = `${Math.abs(Math.round(lean))}° ${leanDir}`;
    }

    const bikeEl = document.getElementById('pbLeanBike');
    if (bikeEl) {
        // CSS rotate: positive = clockwise = rider's right lean
        // Negate to match visual expectation (positive lean = lean right = visual tilt right)
        bikeEl.style.transform = `rotate(${-lean}deg)`;
        bikeEl.style.backgroundColor = Math.abs(lean) > 45 ? '#ff0000' : 'var(--secondary)';
    }

    // G-Force
    // Priority: Aligned > Raw
    // Note: Aligned X = Long, Aligned Y = Lat.
    // Raw X = Long (usually), Raw Y = Lat (usually).
    let gx = 0, gy = 0;

    if (data.ax && data.ax[i] !== undefined) gx = data.ax[i];
    else if (data.raw_ax && data.raw_ax[i] !== undefined) gx = data.raw_ax[i];

    if (data.ay && data.ay[i] !== undefined) gy = data.ay[i];
    else if (data.raw_ay && data.raw_ay[i] !== undefined) gy = data.raw_ay[i];

    const gxEl = document.getElementById('pbGX');
    const gyEl = document.getElementById('pbGY');
    if (gxEl) gxEl.textContent = gx.toFixed(2);
    if (gyEl) gyEl.textContent = gy.toFixed(2);

    const maxG = 1.5;
    const dotX = 50 + (gy / maxG) * 50;
    // Invert X for display (Brake = Top = Neg?, Accel = Bot = Pos?)
    // Conventional G-G diagram: Braking (Long G > 0 or < 0 depending on frame) is usually Up.
    // Datalogger: Accel > 0 (Green). Brake < 0 (Red). 
    // Visualization: Up = Brake. Down = Accel. 
    // So if Brake (<0), we want y < 50 (Top). 
    // 50 + (-Brake * 50). Wait.
    // If val is -1 (Brake). 50 + (-1 * 50) = 0 (Top). Correct.
    // If val is +1 (Accel). 50 + (1 * 50) = 100 (Bot). Correct.
    const dotY = 50 + (gx / maxG) * 50;

    const gDot = document.getElementById('pbGDot');
    if (gDot) {
        gDot.style.left = Math.max(0, Math.min(100, dotX)) + '%';
        gDot.style.top = Math.max(0, Math.min(100, dotY)) + '%';
    }

    // Bars
    const accelBar = document.getElementById('pbAccelBar');
    const brakeBar = document.getElementById('pbBrakeBar');
    const speedBar = document.getElementById('pbSpeedBar');

    if (speedBar) speedBar.style.width = Math.min((speed / 250) * 100, 100) + '%';

    if (accelBar && brakeBar) {
        accelBar.style.height = '0%';
        brakeBar.style.height = '0%';

        if (gx > 0.1) {
            accelBar.style.height = Math.min((gx / 0.8) * 100, 100) + '%';
        } else if (gx < -0.1) {
            brakeBar.style.height = Math.min((Math.abs(gx) / 1.2) * 100, 100) + '%';
        }
    }
}
// ============================================================================
// WIFI SYNC
// ============================================================================

async function syncFromDevice(forcePrompt = false) {
    let ip = await autoDetectDeviceIP();

    if (!ip || forcePrompt) {
        const defaultIP = ip || '192.168.4.1';
        ip = prompt("Enter ESP32 IP Address:\n(Or cancel to Scan Network)", defaultIP);
        if (!ip) {
            // User cancelled prompt, offer scan?
            if (confirm("Scan local network for Datalogger instead?")) {
                scanDevicesAndSync();
            }
            return;
        }
    }

    localStorage.setItem('lastDeviceIP', ip);
    await performSync(ip);
}

async function performSync(ip) {
    const btn = document.querySelector('button[onclick="syncFromDevice()"]');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Syncing...';
    btn.disabled = true;

    showToast(`Connecting to ${ip}...`, 'info');

    try {
        const res = await apiCall('/api/sync/device', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ip })
        });

        if (res.success) {
            const count = res.synced.length;
            if (count > 0) {
                showToast(`Successfully synced ${count} files!`, 'success');
                loadLearningFiles();
            } else {
                showToast('Connected! No new files.', 'success');
            }
            if (res.failed.length > 0) showToast(`Warning: ${res.failed.length} failed`, 'warning');

            // Update connection status immediately
            checkDeviceConnection();
        } else if (res.error) {
            // If connection failed, ask user
            if (confirm(`Connection to ${ip} failed. Scan for device?`)) {
                scanDevicesAndSync();
            } else {
                showToast(res.error, 'error');
            }
        }
    } catch (error) {
        if (confirm(`Connection to ${ip} failed. Scan for device?`)) {
            scanDevicesAndSync();
        } else {
            showToast('Sync Failed', 'error');
        }
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

async function scanDevicesAndSync() {
    const btn = document.querySelector('button[onclick="scanDevicesAndSync()"]');
    const originalIcon = btn ? btn.innerHTML : '';
    if (btn) {
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        btn.disabled = true;
    }

    showToast('Scanning network...', 'info');

    // Clear previous IP context
    if (document.getElementById('devConfigIP')) document.getElementById('devConfigIP').value = '';
    localStorage.removeItem('lastDeviceIP');

    const startTime = Date.now();

    try {
        const res = await apiCall('/api/device/scan');

        // Ensure at least 3 seconds for visual feedback
        const elapsed = Date.now() - startTime;
        if (elapsed < 3000) {
            await new Promise(resolve => setTimeout(resolve, 3000 - elapsed));
        }

        const devices = res.devices || [];

        if (devices.length === 0) {
            showToast("No Datalogger devices found on network.", 'warning');
        } else if (devices.length === 1) {
            const newIP = devices[0].ip;
            showToast(`Device found at ${newIP}!`, 'success');

            // Update stored IP and input field
            localStorage.setItem('lastDeviceIP', newIP);
            if (document.getElementById('devConfigIP')) {
                document.getElementById('devConfigIP').value = newIP;
            }

            // Force immediate status update
            await checkDeviceConnection();

        } else {
            // Multiple
            const ips = devices.map(d => d.ip).join(', ');
            showToast(`Found ${devices.length} devices: ${ips}`, 'info');
            // Save first one
            localStorage.setItem('lastDeviceIP', devices[0].ip);
            await checkDeviceConnection();
        }
    } catch (e) {
        showToast('Scan failed: ' + e.message, 'error');
        console.error('[Scan] Error:', e);
    } finally {
        if (btn) {
            btn.innerHTML = originalIcon;
            btn.disabled = false;
        }
    }
}

// ============================================================================
// DEVICE CONFIG
// ============================================================================

async function configureDeviceWifi() {
    const ip = document.getElementById('devConfigIP').value.trim();
    const ssid = document.getElementById('devConfigSSID').value.trim();
    const password = document.getElementById('devConfigPass').value.trim();

    if (!ip || !ssid || !password) {
        showToast('Please fill all fields', 'warning');
        return;
    }

    const btn = document.querySelector('button[onclick="configureDeviceWifi()"]');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
    btn.disabled = true;

    // Save IP to localStorage immediately
    localStorage.setItem('lastDeviceIP', ip);

    try {
        // Try direct call to ESP32 first (works when browser is on hotspot)
        console.log(`[WiFi Config] Trying direct call to http://${ip}/wifi/add`);
        const directResponse = await fetch(`http://${ip}/wifi/add`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ssid, password }),
            mode: 'cors'
        });

        if (directResponse.ok) {
            const data = await directResponse.json();
            if (data.success) {
                showToast('Success! Device is rebooting to connect to ' + ssid, 'success');
                return;
            }
        }
    } catch (directError) {
        console.log('[WiFi Config] Direct call failed (expected if not on hotspot):', directError.message);
        // Fall through to try backend proxy
    }

    try {
        // Fallback: Try via backend (works when backend is on same network as ESP32)
        console.log('[WiFi Config] Trying via backend proxy /api/device/configure');
        const res = await apiCall('/api/device/configure', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ip, ssid, password })
        });

        if (res.success) {
            showToast('Success! Device is rebooting...', 'success');
        } else if (res.error) {
            showToast('Failed: ' + res.error, 'error');
        }
    } catch (error) {
        showToast('Configuration Failed. Make sure you are connected to ESP32 or same network.', 'error');
        console.error('[WiFi Config] Both methods failed:', error);
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// Helper: Load saved IP into config box on load
document.addEventListener('DOMContentLoaded', () => {
    const savedIP = localStorage.getItem('lastDeviceIP');
    if (savedIP && document.getElementById('devConfigIP')) {
        document.getElementById('devConfigIP').value = savedIP;
    }
    // Fast initial check with direct fetch
    fastConnectCheck();
    // Background polling every 30s
    setInterval(checkDeviceConnection, 30000);
});

// Fast connect - tries direct fetch to last known IP first
async function fastConnectCheck() {
    const ip = localStorage.getItem('lastDeviceIP');
    const badge = document.getElementById('connectionStatus');
    const text = document.getElementById('connText');

    if (!badge || !text) return;

    if (!ip) {
        badge.className = 'status-badge offline';
        text.textContent = 'No Device';
        return;
    }

    badge.className = 'status-badge checking';
    text.textContent = 'Checking...';

    try {
        const response = await fetch(`http://${ip}/status`, {
            mode: 'cors',
            signal: AbortSignal.timeout(2000)
        });

        if (response.ok) {
            const data = await response.json();
            badge.className = 'status-badge online';
            text.textContent = `Connected: ${ip}`;
            updateStorageIndicator(data);
            console.log('[FastCheck] Direct connection success:', ip);
            return;
        }
    } catch (e) {
        console.log('[FastCheck] Direct fetch failed, trying backend...');
    }

    checkDeviceConnection();
}

/**
 * Auto-detects the device IP using BLE (if connected) or network scan.
 * Stores the found IP in localStorage.
 * @returns {Promise<string|null>} Found IP or null
 */
async function autoDetectDeviceIP() {
    // 1. Check BLE if connected
    if (bleConnector && bleConnector.isConnected()) {
        try {
            const status = await bleConnector.getWifiStatus();
            if (status.connected && status.ip && status.ip !== '0.0.0.0') {
                console.log('[AutoDetect] Found IP via BLE:', status.ip);
                localStorage.setItem('lastDeviceIP', status.ip);
                return status.ip;
            }
        } catch (e) {
            console.warn('[AutoDetect] Failed to get IP via BLE', e);
        }
    }

    // 2. Check localStorage
    const savedIP = localStorage.getItem('lastDeviceIP');
    if (savedIP) return savedIP;

    // 3. Fallback to network scan
    try {
        console.log('[AutoDetect] Falling back to network scan...');
        const res = await apiCall('/api/device/scan', { displayError: false });
        if (res.devices && res.devices.length > 0) {
            const ip = res.devices[0].ip;
            console.log('[AutoDetect] Found IP via scan:', ip);
            localStorage.setItem('lastDeviceIP', ip);
            return ip;
        }
    } catch (e) {
        console.warn('[AutoDetect] Network scan failed', e);
    }

    return null;
}

async function checkDeviceConnection() {
    const ip = localStorage.getItem('lastDeviceIP');
    const badge = document.getElementById('connectionStatus');
    const text = document.getElementById('connText');

    // New UI Elements
    const scanBadge = document.getElementById('scanStatusBadge');
    const scanText = document.getElementById('scanStatusText');
    const scanIp = document.getElementById('scanIpText');

    if (!badge || !text) return; // Elements not ready yet

    if (!ip) {
        badge.className = 'status-badge offline';
        text.textContent = 'No Device IP';
        if (scanBadge) scanBadge.className = 'status-dot error';
        if (scanText) { scanText.textContent = 'Disconnected'; scanText.style.color = 'var(--text-primary)'; }
        if (scanIp) scanIp.textContent = '---';
        return;
    }

    try {
        const res = await apiCall(`/api/device/check?ip=${ip}`);
        if (res && res.reachable) {
            badge.className = 'status-badge online';
            text.textContent = `Connected: ${ip}`;

            if (scanBadge) scanBadge.className = 'status-dot success';
            if (scanText) { scanText.textContent = 'Connected'; scanText.style.color = 'var(--success)'; }
            if (scanIp) scanIp.textContent = ip;

            console.log('[Status] Device connected:', ip);

            // Check compatibility
            const warningBadge = document.getElementById('versionWarning');
            if (warningBadge) {
                if (res.compatible === false) {
                    warningBadge.style.display = 'inline-block';
                    warningBadge.title = `Firmware Mismatch: Device has v${res.info.version}, server requires v${res.min_required}`;
                    warningBadge.onclick = () => {
                        showView('settings');
                        showToast(`Firmware v${res.info.version} is outdated. Update to v${res.min_required} in settings.`, 'warning');
                    };
                } else {
                    warningBadge.style.display = 'none';
                }
            }

            // Use storage info from backend response
            if (res.info) {
                updateStorageIndicator(res.info);
            }
        } else {
            badge.className = 'status-badge offline';
            text.textContent = 'Device Offline';

            if (scanBadge) scanBadge.className = 'status-dot warning';
            if (scanText) { scanText.textContent = 'Offline'; scanText.style.color = 'var(--warning)'; }
            if (scanIp) scanIp.textContent = ip;

            console.log('[Status] Device offline:', ip);
            updateStorageIndicator({});  // Hide indicator
        }
    } catch (err) {
        badge.className = 'status-badge offline';
        text.textContent = 'Check Failed';

        if (scanBadge) scanBadge.className = 'status-dot error';
        if (scanText) { scanText.textContent = 'Error'; scanText.style.color = 'var(--error)'; }

        console.error('[Status] Check failed:', err);

        // Hide storage indicator when offline
        const storageEl = document.getElementById('storageIndicator');
        if (storageEl) storageEl.style.display = 'none';
    }
}

// Update storage indicator
function updateStorageIndicator(data) {
    const storageEl = document.getElementById('storageIndicator');
    const barFill = document.getElementById('storageBarFill');
    const storageText = document.getElementById('storageText');

    if (!storageEl || !barFill || !storageText) return;

    if (data.storage_used_pct !== undefined) {
        const pct = data.storage_used_pct;
        storageEl.style.display = 'flex';
        barFill.style.width = pct + '%';
        storageText.textContent = pct + '%';

        // Update color class based on usage
        storageEl.classList.remove('low', 'medium', 'high');
        if (pct < 50) {
            storageEl.classList.add('low');
        } else if (pct < 80) {
            storageEl.classList.add('medium');
        } else {
            storageEl.classList.add('high');
        }

        // Update tooltip
        const usedKB = data.storage_used_kb || 0;
        const totalKB = data.storage_total_kb || 0;
        storageEl.title = `ESP32 Flash: ${usedKB} KB / ${totalKB} KB (${pct}%)`;
    } else {
        storageEl.style.display = 'none';
    }
}

// ============================================================================
// ESP32 WIFI MANAGEMENT - Direct Communication
// ============================================================================

// Get device IP from input or localStorage
function getDeviceIP() {
    const ipInput = document.getElementById('devConfigIP');
    return ipInput ? ipInput.value.trim() : localStorage.getItem('lastDeviceIP') || '192.168.4.1';
}

// Test connection to device
async function testDeviceConnection() {
    const ip = getDeviceIP();
    showToast(`Testing connection to ${ip}...`, 'info');

    try {
        const response = await fetch(`http://${ip}/status`, {
            method: 'GET',
            mode: 'cors',
            signal: AbortSignal.timeout(3000)
        });

        if (response.ok) {
            const data = await response.json();
            showToast(`✓ Connected! Mode: ${data.wifi_mode || 'Unknown'}, Networks: ${data.networks_stored || 0}`, 'success');
            localStorage.setItem('lastDeviceIP', ip);
            return data;
        } else {
            showToast(`Device responded with error ${response.status}`, 'error');
            return null;
        }
    } catch (e) {
        showToast(`Cannot reach ${ip}. Check connection.`, 'error');
        console.error('[Test]', e);
        return null;
    }
}

// Scan state
let scanInProgress = false;

// Show persistent scan toast with progress bar
function showScanProgress(message, progress) {
    const toast = document.getElementById('toast');
    if (!toast) return;

    let html = `<i class="fas fa-spinner fa-spin" style="margin-right: 0.5rem;"></i>${message}`;
    if (progress !== null && progress !== undefined) {
        html += `<div style="margin-top: 0.5rem; background: rgba(255,255,255,0.2); height: 4px; border-radius: 2px; overflow: hidden;">
            <div style="width: ${progress}%; height: 100%; background: var(--primary); transition: width 0.3s;"></div>
        </div>`;
    }

    toast.innerHTML = html;
    toast.className = 'toast active info';
}

function hideScanProgress() {
    const toast = document.getElementById('toast');
    if (toast) toast.className = 'toast';
}

// Scan for ESP32 device with progress feedback
async function scanForDevice() {
    if (scanInProgress) {
        showToast('Scan already running', 'warning');
        return;
    }

    scanInProgress = true;
    const btn = document.getElementById('scanBtn');
    if (btn) {
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        btn.disabled = true;
    }

    // Phase 1: Check last known IP (fastest)
    const lastIP = localStorage.getItem('lastDeviceIP');
    if (lastIP) {
        showScanProgress(`Checking ${lastIP}...`, 10);
        try {
            const response = await fetch(`http://${lastIP}/status`, {
                mode: 'cors',
                signal: AbortSignal.timeout(2000)
            });
            if (response.ok) {
                const data = await response.json();
                finishScanSuccess(lastIP, data, btn);
                return;
            }
        } catch (e) {
            console.log('[Scan] Last IP not responding');
        }
    }

    // Phase 2: Check AP mode IP
    showScanProgress('Checking AP mode (192.168.4.1)...', 25);
    try {
        const apResponse = await fetch('http://192.168.4.1/status', {
            mode: 'cors',
            signal: AbortSignal.timeout(2000)
        });
        if (apResponse.ok) {
            const data = await apResponse.json();
            finishScanSuccess('192.168.4.1', data, btn);
            return;
        }
    } catch (e) {
        console.log('[Scan] AP mode not available');
    }

    // Phase 3: Backend network scan
    showScanProgress('Scanning network...', 50);
    try {
        const res = await apiCall('/api/device/scan');
        const devices = res.devices || [];

        if (devices.length === 1) {
            const ip = devices[0].ip;
            const info = devices[0].info;
            finishScanSuccess(ip, info, btn);
            return;
        } else if (devices.length > 1) {
            hideScanProgress();
            // Show selection dialog
            const ips = devices.map(d => d.ip);
            const selection = prompt(`Multiple devices found:\n${ips.join('\n')}\n\nEnter the IP to connect to:`, ips[0]);
            if (selection && ips.includes(selection)) {
                const device = devices.find(d => d.ip === selection);
                finishScanSuccess(device.ip, device.info, btn);
            } else {
                finishScan(btn);
            }
            return;
        }
    } catch (e) {
        console.log('[Scan] Backend scan error:', e);
    }

    // Phase 4: Quick subnet scan
    showScanProgress('Deep scan (common IPs)...', 80);
    const commonIPs = ['192.168.1.2', '192.168.1.100', '192.168.0.2', '192.168.0.100'];
    for (const ip of commonIPs) {
        try {
            const response = await fetch(`http://${ip}/status`, {
                mode: 'cors',
                signal: AbortSignal.timeout(1000)
            });
            if (response.ok) {
                const data = await response.json();
                if (data.storage_used_pct !== undefined || data.status === 'running') {
                    finishScanSuccess(ip, data, btn);
                    return;
                }
            }
        } catch (e) { }
    }

    // Scan complete - no device found
    hideScanProgress();
    showToast('No Datalogger found. Is it powered on?', 'warning');

    const scanBadge = document.getElementById('scanStatusBadge');
    const scanText = document.getElementById('scanStatusText');
    if (scanBadge) scanBadge.className = 'status-dot error';
    if (scanText) { scanText.textContent = 'Not Found'; scanText.style.color = 'var(--error)'; }

    finishScan(btn);
}

function finishScanSuccess(ip, data, btn) {
    hideScanProgress();
    showToast(`✓ Found at ${ip}`, 'success');

    // Update hidden input for compatibility
    const hiddenInput = document.getElementById('devConfigIP');
    if (hiddenInput) hiddenInput.value = ip;
    localStorage.setItem('lastDeviceIP', ip);

    // Update Scan Card UI
    const scanBadge = document.getElementById('scanStatusBadge');
    const scanText = document.getElementById('scanStatusText');
    const scanIp = document.getElementById('scanIpText');

    if (scanBadge && scanText && scanIp) {
        scanBadge.className = 'status-dot success';
        scanText.textContent = 'Connected';
        scanText.style.color = 'var(--success)';
        scanIp.textContent = ip;
    }

    // Update Header Status
    const badge = document.getElementById('connectionStatus');
    const text = document.getElementById('connText');
    if (badge && text) {
        badge.className = 'status-badge online';
        text.textContent = `Connected: ${ip}`;
    }
    updateStorageIndicator(data);
    finishScan(btn);
}

function finishScan(btn) {
    scanInProgress = false;
    if (btn) {
        btn.innerHTML = '<i class="fas fa-search"></i> Scan';
        btn.disabled = false;
    }
}

// Load stored networks from device
async function loadStoredNetworks() {
    const ip = getDeviceIP();
    const container = document.getElementById('storedNetworksList');

    if (!container) return;

    container.innerHTML = '<span style="color: var(--text-muted);"><i class="fas fa-spinner fa-spin"></i> Loading...</span>';

    try {
        const response = await fetch(`http://${ip}/wifi/list`, {
            method: 'GET',
            mode: 'cors',
            signal: AbortSignal.timeout(5000)
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        const networks = data.networks || [];

        if (networks.length === 0) {
            container.innerHTML = '<span style="color: var(--text-muted);">No networks stored. Add one below.</span>';
        } else {
            container.innerHTML = networks.map(ssid => `
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem; background: var(--bg-primary); border-radius: 4px; margin-bottom: 0.25rem;">
                    <span><i class="fas fa-wifi" style="margin-right: 0.5rem; color: var(--primary);"></i>${ssid}</span>
                    <button class="btn btn-danger btn-sm" onclick="removeWifiNetwork('${ssid}')" style="padding: 0.25rem 0.5rem;">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            `).join('');
        }
    } catch (e) {
        container.innerHTML = `<span style="color: var(--danger);">Failed to load: ${e.message}</span>`;
        console.error('[WiFi List]', e);
    }
}

// Add WiFi network to device
async function addWifiNetwork() {
    const ip = getDeviceIP();
    const ssid = document.getElementById('devConfigSSID').value.trim();
    const password = document.getElementById('devConfigPass').value;

    if (!ssid) {
        showToast('Please enter SSID', 'warning');
        return;
    }

    showToast(`Adding ${ssid}...`, 'info');

    try {
        const response = await fetch(`http://${ip}/wifi/add`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            mode: 'cors',
            body: JSON.stringify({ ssid, password }),
            signal: AbortSignal.timeout(10000)
        });

        if (response.ok) {
            const data = await response.json();
            showToast(`✓ Added ${ssid}. Device rebooting...`, 'success');

            // Clear form
            document.getElementById('devConfigSSID').value = '';
            document.getElementById('devConfigPass').value = '';

            // Reload list after reboot delay
            setTimeout(() => loadStoredNetworks(), 5000);
        } else {
            const err = await response.text();
            showToast(`Failed: ${err}`, 'error');
        }
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
        console.error('[Add WiFi]', e);
    }
}

// Remove WiFi network from device
async function removeWifiNetwork(ssid) {
    if (!confirm(`Remove "${ssid}" from stored networks?`)) return;

    const ip = getDeviceIP();

    try {
        const response = await fetch(`http://${ip}/wifi/remove`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            mode: 'cors',
            body: JSON.stringify({ ssid }),
            signal: AbortSignal.timeout(5000)
        });

        if (response.ok) {
            showToast(`Removed ${ssid}`, 'success');
            loadStoredNetworks();
        } else {
            showToast('Failed to remove', 'error');
        }
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}


// ============================================================================
// ESP32 FIRMWARE MANAGEMENT
// ============================================================================

async function checkEspVersionManual() {
    const ip = localStorage.getItem('lastDeviceIP');
    if (!ip) {
        document.getElementById('espCurrentVersion').textContent = 'No Device IP';
        return;
    }

    try {
        const res = await apiCall(`/api/device/version-check?ip=${ip}`);
        if (res.error) throw new Error(res.error);

        document.getElementById('espCurrentVersion').textContent = `v${res.device_version}`;
        document.getElementById('espServerVersion').textContent = `v${res.server_version}`;

        const updateArea = document.getElementById('espUpdateArea');
        if (res.update_available) {
            updateArea.style.display = 'block';
            document.getElementById('espUpdateMsg').innerHTML = `<i class="fas fa-exclamation-triangle"></i> Update Available: v${res.server_version}`;
        } else {
            updateArea.style.display = 'none';
        }
    } catch (e) {
        console.error('Failed to check version:', e);
        document.getElementById('espCurrentVersion').textContent = 'Offline?';
    }
}

async function flashLatestEspWifi() {
    const ip = localStorage.getItem('lastDeviceIP');
    if (!ip) return;

    if (!confirm("Are you sure you want to flash the latest firmware over WiFi?\n\nThe device will reboot after completion.")) {
        return;
    }

    const btn = document.getElementById('btnEspUpdate');
    const progressBar = document.getElementById('espOtaProgress');
    const barFill = document.getElementById('espOtaBar');
    const statusText = document.getElementById('espOtaStatus');

    btn.disabled = true;
    progressBar.style.display = 'block';
    barFill.style.width = '0%';
    statusText.textContent = 'Preparing files...';

    try {
        statusText.textContent = 'Uploading firmware files...';
        // Give some visual feedback earlier
        setTimeout(() => { if (barFill.style.width === '0%') barFill.style.width = '15%'; }, 500);

        const res = await apiCall('/api/device/update-ota', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ip })
        });

        if (res.success) {
            barFill.style.width = '100%';
            statusText.textContent = 'Update Complete! Device rebooting...';
            showToast('Firmware pushed successfully!', 'success');

            // Wait for reboot
            setTimeout(() => {
                progressBar.style.display = 'none';
                btn.disabled = false;
                checkDeviceConnection();
                checkEspVersionManual();
            }, 6000);
        } else {
            throw new Error(res.failed ? res.failed.join(', ') : 'Unknown error');
        }
    } catch (e) {
        btn.disabled = false;
        statusText.textContent = 'Update Failed';
        showToast(`Flash Failed: ${e.message}`, 'error');
    }
}

// ============================================================================
// BLE PROVISIONING INTEGRATION
// ============================================================================

let bleConnector = null;

/**
 * AUTO-SHARE WIFI LOGIC
 */
const WIFI_CRED_KEY = 'racesense_wifi_vault';

function getWifiVault() {
    try {
        const vault = localStorage.getItem(WIFI_CRED_KEY);
        // Simple obfuscation (b64) to prevent plain text scraping, not for high security
        return vault ? JSON.parse(atob(vault)) : {};
    } catch (e) { return {}; }
}

function saveToWifiVault(ssid, pass) {
    if (!document.getElementById('autoShareWifiToggle').checked) return;
    const vault = getWifiVault();
    vault[ssid] = pass;
    localStorage.setItem(WIFI_CRED_KEY, btoa(JSON.stringify(vault)));
}

function toggleAutoShareWifi() {
    const enabled = document.getElementById('autoShareWifiToggle').checked;
    localStorage.setItem('autoShareWifiEnabled', enabled);
    if (!enabled) {
        if (confirm("Clear saved WiFi vault?")) {
            localStorage.removeItem(WIFI_CRED_KEY);
        }
    }
}

async function attemptAutoWifiShare(visibleNetworks) {
    if (!document.getElementById('autoShareWifiToggle').checked) return false;

    const vault = getWifiVault();
    // Prioritize networks by vault presence
    const match = visibleNetworks.find(ssid => vault[ssid]);

    if (match) {
        showToast(`Auto-configuring WiFi: ${match}...`, 'info');
        try {
            await bleConnector.configureWifi(match, vault[match]);
            return true;
        } catch (e) {
            console.error('[AutoShare] Failed', e);
        }
    }
    return false;
}

function initBleSupportCheck() {
    console.log('Checking Web Bluetooth support...');
    const warning = document.getElementById('bleSupportWarning');
    const connectBtn = document.getElementById('btnBleConnect');

    // Check if DataloggerBLE class is loaded
    if (typeof DataloggerBLE === 'undefined') {
        console.warn('DataloggerBLE class not found. Skipping BLE check.');
        if (warning) {
            warning.style.display = 'block';
            warning.innerHTML = '<i class="fas fa-exclamation-circle"></i> BLE Module failed to load';
        }
        if (connectBtn) connectBtn.disabled = true;
        return;
    }

    // Restore Auto-Share toggle state
    const autoShareEnabled = localStorage.getItem('autoShareWifiEnabled') !== 'false';
    const toggle = document.getElementById('autoShareWifiToggle');
    if (toggle) toggle.checked = autoShareEnabled;

    if (!DataloggerBLE.isSupported()) {
        if (warning) warning.style.display = 'block';
        if (connectBtn) connectBtn.disabled = true;
    } else {
        bleConnector = new DataloggerBLE();
        setupBleCallbacks();
    }
}

function setupBleCallbacks() {
    if (!bleConnector) return;

    bleConnector.onConnect = () => {
        updateBleUiState('connected');
        showToast('Bluetooth Connected!', 'success');
        // Automatically scan for networks on connect
        handleBleWifiScan();
        // Try to auto-detect IP if already on WiFi
        autoDetectDeviceIP().then(ip => {
            if (ip) checkDeviceConnection();
        });
    };

    bleConnector.onDisconnect = () => {
        updateBleUiState('disconnected');
        showToast('Bluetooth Disconnected', 'warning');
    };

    bleConnector.onStatusChange = (status) => {
        console.log('[BLE] Status Change:', status);
        if (status.connected && status.ip !== '0.0.0.0') {
            // Update app state with device IP
            localStorage.setItem('lastDeviceIP', status.ip);
            const ipInput = document.getElementById('devConfigIP');
            if (ipInput) ipInput.value = status.ip;

            showToast(`WiFi Connected! Device IP: ${status.ip}`, 'success');

            // Re-check connection via HTTP now
            checkDeviceConnection();
        }
    };

    bleConnector.onDeviceInfoChange = (info) => {
        console.log('[BLE] Device Info:', info);
        // Could update UI elements here
    };
}

async function handleBleConnect() {
    if (!bleConnector) return;
    try {
        await bleConnector.connect();
    } catch (e) {
        if (e.name !== 'NotFoundError' && e.name !== 'AbortError') {
            showToast(`BLE Connect Failed: ${e.message}`, 'error');
        }
    }
}

async function handleBleWifiScan() {
    if (!bleConnector || !bleConnector.isConnected()) return;

    const select = document.getElementById('bleWifiSelect');
    select.innerHTML = '<option value="">Scanning...</option>';

    try {
        const networks = await bleConnector.scanNetworks();
        if (networks.length === 0) {
            select.innerHTML = '<option value="">No networks found</option>';
        } else {
            select.innerHTML = networks.map(ssid => `<option value="${ssid}">${ssid}</option>`).join('');

            // ATTEMPT AUTO-SHARE
            const autoSuccess = await attemptAutoWifiShare(networks);
            if (autoSuccess) {
                showToast('Auto-share successful! Device is connecting...', 'success');
            }
        }
    } catch (e) {
        showToast('WiFi scan failed over BLE', 'error');
        select.innerHTML = '<option value="">Scan failed</option>';
    }
}

async function handleBleWifiConfig() {
    if (!bleConnector || !bleConnector.isConnected()) return;

    const ssid = document.getElementById('bleWifiSelect').value;
    const password = document.getElementById('bleWifiPass').value;

    if (!ssid) {
        showToast('Please select a network', 'warning');
        return;
    }

    // Save to vault if enabled
    saveToWifiVault(ssid, password);

    showToast(`Configuring ${ssid}...`, 'info');
    try {
        await bleConnector.configureWifi(ssid, password);

        // Start polling for status
        showToast('Waiting for device to connect to WiFi...', 'info');

        let attempts = 0;
        const maxAttempts = 20;

        const pollInterval = setInterval(async () => {
            if (!bleConnector || !bleConnector.isConnected()) {
                clearInterval(pollInterval);
                return;
            }
            attempts++;
            try {
                const status = await bleConnector.getWifiStatus();
                if (status.connected && status.ip && status.ip !== '0.0.0.0') {
                    clearInterval(pollInterval);
                    localStorage.setItem('lastDeviceIP', status.ip);

                    const ipInput = document.getElementById('devConfigIP');
                    if (ipInput) ipInput.value = status.ip;

                    showToast(`WiFi Connected! IP: ${status.ip}`, 'success');

                    // Trigger device connection check
                    checkDeviceConnection();

                    // Optionally auto-disconnect BLE to save power after a small delay
                    setTimeout(() => {
                        if (bleConnector && bleConnector.isConnected()) {
                            console.log('[BLE] Auto-disconnecting to save power');
                            bleConnector.disconnect();
                        }
                    }, 3000);
                }
            } catch (e) {
                console.error('Error polling BLE status:', e);
            }

            if (attempts >= maxAttempts) {
                clearInterval(pollInterval);
                showToast('WiFi connection timeout. Check credentials.', 'warning');
            }
        }, 1000);

    } catch (e) {
        showToast('Failed to send WiFi config', 'error');
    }
}

async function handleBleStartAP() {
    if (!bleConnector || !bleConnector.isConnected()) return;

    if (!confirm('Start AP mode? You will need to connect to the "Datalogger-Setup" WiFi.')) return;

    try {
        await bleConnector.startAPMode();
        showToast('AP Mode started on device', 'success');
        // Give heads up about Mac network behavior
        alert('Please connect your computer to the "Datalogger-Setup" WiFi. Note: You might lose internet while connected.');
    } catch (e) {
        showToast('Failed to start AP', 'error');
    }
}

function updateBleUiState(state) {
    const dot = document.getElementById('bleStatusDot');
    const text = document.getElementById('bleStatusText');
    const btn = document.getElementById('btnBleConnect');
    const setupArea = document.getElementById('bleWifiSetup');

    if (state === 'connected') {
        dot.className = 'status-dot connected';
        text.textContent = 'Bluetooth: Connected';
        btn.textContent = 'Disconnect';
        btn.onclick = () => bleConnector.disconnect();
        setupArea.style.display = 'block';
    } else {
        dot.className = 'status-dot offline';
        text.textContent = 'Bluetooth: Not Connected';
        btn.innerHTML = '<i class="fab fa-bluetooth-b"></i> Connect';
        btn.onclick = handleBleConnect;
        setupArea.style.display = 'none';
    }
}

/**
 * UI Cleanup: Collapsible section helper
 */
function toggleDetailsSection(sectionId) {
    const section = document.getElementById(sectionId);
    if (section) {
        section.classList.toggle('collapsed');
    }
}


// ============================================================================
// HYBRID BURST SYNC LOGIC
// ============================================================================

async function startHybridSync() {
    const overlay = document.getElementById('syncOverlay');
    const title = document.getElementById('syncStatusTitle');
    const details = document.getElementById('syncStatusDetails');
    const icon = document.getElementById('syncIcon');
    const progressFill = document.getElementById('syncProgressFill');
    const progressBar = document.getElementById('syncProgressBar');
    const closeBtn = document.getElementById('syncCloseBtn');

    // Show overlay
    overlay.classList.add('active');
    closeBtn.style.display = 'none';
    progressBar.style.display = 'none';
    icon.innerHTML = '<i class="fas fa-sync fa-spin"></i>';
    icon.style.color = 'var(--primary)';
    title.textContent = 'Syncing Data';
    details.textContent = 'Initializing connection...';

    try {
        window.hybridBurstService.setProgressCallback(({ step, details: stepDetails }) => {
            details.textContent = stepDetails;

            switch (step) {
                case 'BLE_CONNECTING':
                    title.textContent = 'Connecting...';
                    break;
                case 'STARTING_AP':
                    title.textContent = 'Activating WiFi';
                    break;
                case 'JOINING_WIFI':
                    title.textContent = 'Joining Network';
                    break;
                case 'DOWNLOADING':
                    title.textContent = 'Downloading CSVs';
                    progressBar.style.display = 'block';
                    // Update progress bar if stepDetails contains "X/Y"
                    const match = stepDetails.match(/(\d+)\/(\d+)/);
                    if (match) {
                        const current = parseInt(match[1]);
                        const total = parseInt(match[2]);
                        progressFill.style.width = `${(current / total) * 100}%`;
                    }
                    break;
                case 'AP_STOPPING':
                    title.textContent = 'Wrapping Up';
                    progressFill.style.width = '100%';
                    break;
                case 'SYNC_COMPLETE':
                    title.textContent = 'Sync Success!';
                    icon.innerHTML = '<i class="fas fa-check-circle"></i>';
                    icon.style.color = 'var(--success)';
                    closeBtn.style.display = 'block';
                    showToast('Sync completed successfully!', 'success');
                    // Refresh data
                    loadHomeData();
                    break;
                case 'ERROR':
                    title.textContent = 'Sync Failed';
                    icon.innerHTML = '<i class="fas fa-exclamation-triangle"></i>';
                    icon.style.color = 'var(--error)';
                    closeBtn.style.display = 'block';
                    showToast('Sync failed: ' + stepDetails, 'error');
                    break;
            }
        });

        await window.hybridBurstService.startSync();
    } catch (error) {
        console.error('Hybrid sync failed:', error);
        title.textContent = 'Sync Failed';
        details.textContent = error.message;
        icon.innerHTML = '<i class="fas fa-exclamation-triangle"></i>';
        icon.style.color = 'var(--error)';
        closeBtn.style.display = 'block';
    }
}

function closeSyncOverlay() {
    const overlay = document.getElementById('syncOverlay');
    overlay.classList.remove('active');
}
