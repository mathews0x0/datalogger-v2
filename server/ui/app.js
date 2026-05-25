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

// initialization
let tracks = [];
let sessions = [];
let pendingSessionTrackFilter = null;
let activeTrackId = null;  // Track identified by ESP32 status
let lastSyncedTrackId = null; // Track we last pushed to ESP32
let isDeviceConnected = false; // True only when device is confirmed reachable
let isCloudConnected = false;  // True when device is seen via Cloud Heartbeat
let currentView = localStorage.getItem('ui:lastView') || 'home';
let currentSessionTab = localStorage.getItem('ui:sessionTab') || 'sessions';
let currentCommunityTab = localStorage.getItem('ui:communityTab') || 'explore';
let trackSearchQuery = localStorage.getItem('ui:tracksSearch') || '';
let sessionSearchQuery = localStorage.getItem('ui:sessionSearch') || '';
let communitySearchQuery = localStorage.getItem('ui:communitySearch') || '';
let adminUsersData = [];
let adminTracksData = [];
let adminUnmatchedTracks = [];
let adminSettings = {};
let adminCurrentPage = 1;
let adminPerPage = 50;
let pendingAdminTrackDeleteId = null;
let deviceTokensCache = [];
let hasRestoredInitialView = false;
let processUploadSummary = null;
let isHeaderDeviceDetailsOpen = false;
let playbackResizeHandler = null;
let pairingTutorialCurrentSlide = 0;
let pairingTutorialMode = 'hotspot';
let ledTutorialCurrentSlide = 0;
let onboardingTutorialFlow = false;
let headerMetricsObserver = null;

function saveUiState(key, value) {
    if (value === undefined || value === null || value === '') {
        localStorage.removeItem(key);
        return;
    }
    localStorage.setItem(key, String(value));
}

function readUiState(key, fallback = '') {
    const value = localStorage.getItem(key);
    return value === null ? fallback : value;
}

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', async () => {
    console.log('Datalogger Companion App loaded');

    updateResponsiveChromeMetrics();
    const header = document.getElementById('appHeader');
    if (header && 'ResizeObserver' in window) {
        headerMetricsObserver?.disconnect?.();
        headerMetricsObserver = new ResizeObserver(() => updateResponsiveChromeMetrics());
        headerMetricsObserver.observe(header);
    }
    window.addEventListener('resize', updateResponsiveChromeMetrics);
    initUiAccessibility();
    bindTutorialTriggers();

    // Start cloud heartbeat polling
    pollCloudHeartbeat();

    // Set up navigation
    setupNavigation();

    // Check Auth before loading user-dependent home state
    await checkAuth();

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

    if (currentUser) {
        await loadDeviceTokens();
        await loadHomeData();
    }
});

function updateResponsiveChromeMetrics() {
    const header = document.getElementById('appHeader');
    if (!header) return;

    const headerHeight = Math.ceil(header.getBoundingClientRect().height);
    document.documentElement.style.setProperty('--header-offset', `${headerHeight}px`);
}

function initUiAccessibility() {
    document.querySelectorAll('.modal-close').forEach(el => {
        el.setAttribute('role', 'button');
        el.setAttribute('tabindex', '0');
        if (!el.getAttribute('aria-label')) el.setAttribute('aria-label', 'Close dialog');
        el.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                el.click();
            }
        });
    });

    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape') return;
        const activeModal = document.querySelector('.modal.active');
        if (activeModal) {
            activeModal.classList.remove('active');
            return;
        }

        const overlay = document.getElementById('profilePanelOverlay');
        const panel = document.getElementById('profilePanel');
        if (overlay?.classList.contains('active') || panel?.classList.contains('active')) {
            closeProfilePanel();
        }
    });
}

function bindTutorialTriggers() {
    const tutorialTriggers = [
        { id: 'deviceStatusSetupTutorialBtn', action: () => openPairingTutorial(false) },
        { id: 'deviceStatusLedTutorialBtn', action: () => openLedTutorial(false) },
        { id: 'setupTutorialCard', action: () => openPairingTutorial(false) },
        { id: 'ledTutorialCard', action: () => openLedTutorial(false) }
    ];

    tutorialTriggers.forEach(({ id, action }) => {
        const el = document.getElementById(id);
        if (!el || el.dataset.boundTutorialTrigger === 'true') return;

        el.addEventListener('click', (event) => {
            if (event) {
                event.preventDefault();
                event.stopPropagation();
            }
            action();
        });

        if (el.getAttribute('role') === 'button') {
            el.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    action();
                }
            });
        }

        el.dataset.boundTutorialTrigger = 'true';
    });
}

function formatStorageCompact(kbValue, unit) {
    if (!kbValue || kbValue <= 0) return `${unit} --`;
    if (unit === 'SD') {
        return `SD ${(kbValue / 1024).toFixed(1)}G`;
    }
    return `Flash ${(kbValue / 1024).toFixed(1)}M`;
}

function formatStorageDetail(usedKb, totalKb, unit) {
    if (!totalKb || totalKb <= 0) return unit === 'SD' ? 'No SD card detected' : 'Flash details unavailable';
    const divisor = 1024;
    const suffix = unit === 'SD' ? 'GB' : 'MB';
    return `${(usedKb / divisor).toFixed(1)} / ${(totalKb / divisor).toFixed(1)} ${suffix} used`;
}

function toggleHeaderDeviceDetails(forceOpen = null) {
    const details = document.getElementById('headerDeviceDetails');
    const trigger = document.getElementById('connectionStatus');
    if (!details || !trigger) return;

    const nextState = typeof forceOpen === 'boolean' ? forceOpen : !isHeaderDeviceDetailsOpen;
    isHeaderDeviceDetailsOpen = nextState;
    details.classList.toggle('is-open', nextState);
    trigger.setAttribute('aria-expanded', nextState ? 'true' : 'false');
}

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
        saveUiState('ui:lastView', viewName);

        // Load data for view
        switch (viewName) {
            case 'home':
                loadHomeData();
                break;
            case 'tracks':
                loadTracks();
                break;
            case 'sessions':
                switchSessionTab(currentSessionTab);
                break;
            case 'community':
                switchCommunityTab(currentCommunityTab);
                break;
            case 'teams':
                loadTeams();
                break;
            case 'admin':
                loadAdminUsers();
                loadAdminTrackData();
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
                if (currentUser) loadDeviceTokens();
                break;
        }
    }

    requestAnimationFrame(updateResponsiveChromeMetrics);
}

// ============================================================================
// API CALLS
// ============================================================================

function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return null;
}

async function apiCall(endpoint, options = {}) {
    try {
        // Prevent caching
        const separator = endpoint.includes('?') ? '&' : '?';
        const url = `${API_BASE}${endpoint}${separator}_t=${Date.now()}`;

        // Ensure credentials are included for cross-origin or same-origin cookie based calls
        options.credentials = 'include';

        // Handle JWT CSRF Protection (Required for non-GET requests in production)
        const method = (options.method || 'GET').toUpperCase();
        if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
            const csrfToken = getCookie('csrf_access_token');
            if (csrfToken) {
                options.headers = options.headers || {};
                options.headers['X-CSRF-TOKEN'] = csrfToken;
            }
        }

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
            } else if (endpoint === '/api/auth/login') {
                throw new Error(errorData.error);
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
        if (options.displayError !== false) {
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
        const user = await apiCall('/api/auth/me', { displayError: false });
        if (user) {
            currentUser = user;
            if (currentUser.active_track_id) {
                activeTrackId = currentUser.active_track_id;
            }
            updateAuthUI();
        } else {
            // No user - show landing page
            currentUser = null;
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
    const tierBadge = document.getElementById('tierBadge');
    const adminNavBtn = document.getElementById('adminNavBtn');
    const landingPage = document.getElementById('landingPage');
    const appContent = document.getElementById('appContent');
    const headerStatusBadges = document.getElementById('headerStatusBadges');

    if (currentUser) {
        // Show app, hide landing page
        if (landingPage) landingPage.style.display = 'none';
        if (appContent) appContent.style.display = 'block';
        if (headerStatusBadges) headerStatusBadges.style.display = 'flex';

        if (loginBtn) loginBtn.style.display = 'none';
        if (userProfileHeader) userProfileHeader.style.display = 'flex';
        if (headerUserName) headerUserName.textContent = currentUser.name || currentUser.email;

        if (tierBadge) {
            tierBadge.textContent = (currentUser.subscription_tier || 'FREE').toUpperCase();
            tierBadge.className = `tier-badge ${currentUser.subscription_tier || 'free'}`;
        }

        // Admin nav
        const isAdmin = !!currentUser.is_admin;
        if (adminNavBtn) adminNavBtn.style.display = isAdmin ? 'flex' : 'none';

        // Populate profile panel fields
        const nameInput = document.getElementById('profileName');
        const emailInput = document.getElementById('profileEmail');
        const bikeInput = document.getElementById('profileBike');
        const trackInput = document.getElementById('profileHomeTrack');
        if (nameInput) nameInput.value = currentUser.name || '';
        if (emailInput) emailInput.value = currentUser.email || '';
        if (bikeInput) bikeInput.value = currentUser.bike_info || '';
        if (trackInput) trackInput.value = currentUser.home_track || '';

        // Profile photo
        setProfileAvatars(currentUser);

        // My Devices section visibility
        const myDevicesCard = document.getElementById('myDevicesCard');
        if (myDevicesCard) myDevicesCard.style.display = 'block';

        if (!hasRestoredInitialView) {
            hasRestoredInitialView = true;
            const initialView = readUiState('ui:lastView', 'home');
            if (initialView && initialView !== 'home') {
                requestAnimationFrame(() => showView(initialView));
            }
        }
    } else {
        // Show landing page, hide app
        if (landingPage) landingPage.style.display = 'block';
        if (appContent) appContent.style.display = 'none';
        if (headerStatusBadges) headerStatusBadges.style.display = 'none';

        if (loginBtn) loginBtn.style.display = 'block';
        if (userProfileHeader) userProfileHeader.style.display = 'none';
        toggleHeaderDeviceDetails(false);

        // Hide devices card
        const myDevicesCard = document.getElementById('myDevicesCard');
        if (myDevicesCard) myDevicesCard.style.display = 'none';
    }

    updateDeviceSetupChecklist();
    requestAnimationFrame(updateResponsiveChromeMetrics);
}

// === PASSWORD MODAL ===
function openChangePasswordModal() {
    closeProfilePanel();
    const modal = document.getElementById('changePasswordModal');
    if (modal) modal.classList.add('active');
}

function closeChangePasswordModal() {
    const modal = document.getElementById('changePasswordModal');
    if (modal) modal.classList.remove('active');
}

// === PROFILE PHOTO ===
function setProfileAvatars(user) {
    const headerImg = document.getElementById('headerAvatarImg');
    const headerIcon = document.getElementById('headerAvatarIcon');
    const panelImg = document.getElementById('profilePanelAvatar');
    const panelIcon = document.getElementById('profilePanelAvatarIcon');
    const removeBtn = document.getElementById('removePhotoBtn');

    if (user && user.profile_photo) {
        const photoUrl = `${API_BASE}/api/users/${user.id}/photo?t=${Date.now()}`;
        if (headerImg) { headerImg.src = photoUrl; headerImg.style.display = 'block'; }
        if (headerIcon) headerIcon.style.display = 'none';
        if (panelImg) { panelImg.src = photoUrl; panelImg.style.display = 'block'; }
        if (panelIcon) panelIcon.style.display = 'none';
        if (removeBtn) removeBtn.style.display = 'inline';
    } else {
        if (headerImg) { headerImg.src = ''; headerImg.style.display = 'none'; }
        if (headerIcon) headerIcon.style.display = 'inline';
        if (panelImg) { panelImg.src = ''; panelImg.style.display = 'none'; }
        if (panelIcon) panelIcon.style.display = 'inline';
        if (removeBtn) removeBtn.style.display = 'none';
    }
}

async function uploadProfilePhoto(input) {
    if (!input.files || !input.files[0]) return;
    const file = input.files[0];

    // Max 2MB
    if (file.size > 2 * 1024 * 1024) {
        showToast('Photo must be under 2MB', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('photo', file);

    try {
        const res = await fetch(`${API_BASE}/api/auth/profile/photo`, {
            method: 'POST',
            credentials: 'include',
            body: formData
        });
        const data = await res.json();
        if (res.ok && data.user) {
            currentUser = data.user;
            setProfileAvatars(currentUser);
            showToast('Profile photo updated', 'success');
        } else {
            showToast(data.error || 'Upload failed', 'error');
        }
    } catch (e) {
        showToast('Upload failed', 'error');
    }
    input.value = ''; // Reset file input
}

async function removeProfilePhoto() {
    try {
        const res = await fetch(`${API_BASE}/api/auth/profile/photo`, {
            method: 'DELETE',
            credentials: 'include'
        });
        const data = await res.json();
        if (res.ok && data.user) {
            currentUser = data.user;
            setProfileAvatars(currentUser);
            showToast('Profile photo removed', 'info');
        }
    } catch (e) {
        showToast('Failed to remove photo', 'error');
    }
}

// === PROFILE PANEL ===
function openProfilePanel() {
    const overlay = document.getElementById('profilePanelOverlay');
    const panel = document.getElementById('profilePanel');
    if (overlay) overlay.classList.add('active');
    if (panel) panel.classList.add('active');
}

function closeProfilePanel() {
    const overlay = document.getElementById('profilePanelOverlay');
    const panel = document.getElementById('profilePanel');
    if (overlay) overlay.classList.remove('active');
    if (panel) panel.classList.remove('active');
}

// Close profile panel on Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeProfilePanel();
});

async function changePassword() {
    console.log('[Auth] Change Password triggered');
    const oldPassword = document.getElementById('oldPassword').value;
    const newPassword = document.getElementById('newPassword').value;
    const confirmNewPassword = document.getElementById('confirmNewPassword').value;

    if (!oldPassword || !newPassword || !confirmNewPassword) {
        showToast('Please fill in all password fields', 'error');
        return;
    }

    if (newPassword !== confirmNewPassword) {
        showToast('New passwords do not match', 'error');
        return;
    }

    if (newPassword.length < 8) {
        showToast('New password must be at least 8 characters', 'error');
        return;
    }

    // Check strength matches backend: at least one number or uppercase
    if (newPassword.toLowerCase() === newPassword && !/\d/.test(newPassword)) {
        showToast('Password must contain at least one number or uppercase letter', 'error');
        return;
    }

    try {
        const result = await apiCall('/api/auth/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                old_password: oldPassword,
                new_password: newPassword
            })
        });

        if (result && result.success) {
            showToast('Password updated successfully!', 'success');
            // Clear inputs
            document.getElementById('oldPassword').value = '';
            document.getElementById('newPassword').value = '';
            document.getElementById('confirmNewPassword').value = '';
        }
    } catch (e) {
        showToast(e.message, 'error');
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
    const actionBtn = document.getElementById('upgradeActionBtn');

    if (featureName) {
        title.textContent = "Unlock " + featureName;
        message.innerHTML = `
            <p>The <strong>${featureName}</strong> feature is available on our Pro plan.</p>
            <p style="margin-top: 1rem;">To upgrade your account, please contact:</p>
            <a href="mailto:support@racesense.v2" class="upgrade-contact-btn">📧 support@racesense.v2</a>
        `;
    } else {
        title.textContent = "Upgrade to Pro";
        message.innerHTML = `
            <p>Get unlimited session storage, CSV exports, and advanced telemetry features.</p>
            <p style="margin-top: 1rem;">To unlock Pro, contact our team:</p>
            <a href="mailto:support@racesense.v2" class="upgrade-contact-btn">📧 support@racesense.v2</a>
        `;
    }

    // Hide the old upgrade button since we're using inline email link
    if (actionBtn) actionBtn.style.display = 'none';

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

// ============================================================================
// DEVICE TOKEN MANAGEMENT
// ============================================================================

async function toggleAutoAnalyse(tokenId, checked) {
    try {
        await apiCall(`/api/devices/${tokenId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ auto_analyse: checked })
        });
        showToast('Auto Analyse preference saved', 'success');
        // Cache update
        const device = deviceTokensCache.find(d => d.id === tokenId);
        if (device) device.auto_analyse = checked;
    } catch (e) {
        showToast('Failed to update Auto Analyse: ' + e.message, 'error');
        loadDeviceTokens(); // Revert toggle state
    }
}

async function loadDeviceTokens() {
    const container = document.getElementById('deviceTokensList');

    try {
        const devices = await apiCall('/api/devices');
        deviceTokensCache = devices || [];
        updateDeviceSetupChecklist();
        if (!container) return;
        if (!devices || devices.length === 0) {
            container.innerHTML = '<span style="color: var(--text-muted); font-size: 0.85rem;">No devices registered. Generate a token above.</span>';
            return;
        }

        container.innerHTML = devices.map(d => {
            const now = new Date();
            let isOnline = false;
            if (d.last_sync) {
                const lastSyncTime = new Date(d.last_sync);
                if (Math.abs(now - lastSyncTime) < 60000) {
                    isOnline = true;
                }
            }

            const uidText = d.device_uid ? `<span style="margin-left: 0.75rem; color: var(--text-muted); font-size: 0.75rem; font-family: monospace;">UID ${d.device_uid.slice(-6)}</span>` : '';
            const batteryText = d.vbatt_sense ? `<span style="margin-left: 0.75rem; color: var(--text-muted); font-size: 0.75rem;"><i class="fas fa-battery-half"></i> ${d.vbatt_sense.toFixed(2)}V</span>` : '';
            const sdText = d.storage_sd_free !== null && d.storage_sd_free !== undefined ? `<span style="margin-left: 0.75rem; color: var(--text-muted); font-size: 0.75rem;"><i class="fas fa-sd-card"></i> ${d.storage_sd_free} MB free</span>` : '';
            const flashText = d.storage_flash_free !== null && d.storage_flash_free !== undefined ? `<span style="margin-left: 0.75rem; color: var(--text-muted); font-size: 0.75rem;"><i class="fas fa-microchip"></i> ${d.storage_flash_free} KB free</span>` : '';

            const isAutoAnalyse = d.auto_analyse !== false; // Default true

            return `
            <div style="display: flex; flex-direction: column; padding: 0.75rem; background: var(--bg-secondary); border-radius: 8px; margin-bottom: 0.5rem; border: 1px solid var(--border);">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem;">
                    <div>
                        <span style="font-weight: 600;">${d.device_name}</span>
                        <span style="font-size: 0.75rem; color: var(--text-muted); margin-left: 0.5rem; font-family: monospace;">rsk_••••${d.token ? d.token.slice(-4) : '????'}</span>
                        ${d.revoked ? '<span style="color: var(--error); font-size: 0.7rem; margin-left: 0.5rem;">REVOKED</span>' : (isOnline ? '<span style="color: var(--success); font-size: 0.7rem; margin-left: 0.5rem;">ONLINE</span>' : '<span style="color: var(--text-muted); font-size: 0.7rem; margin-left: 0.5rem;">OFFLINE</span>')}
                        <div style="margin-top: 0.25rem;">
                            ${uidText}${batteryText}${sdText}${flashText}
                        </div>
                    </div>
                    ${!d.revoked ? `<button class="btn btn-danger btn-sm" onclick="revokeDeviceToken(${d.id})" style="padding: 0.25rem 0.75rem; font-size: 0.75rem;">Revoke</button>` : ''}
                </div>
                ${!d.revoked ? `
                <div style="display: flex; align-items: center; justify-content: space-between; padding-top: 0.5rem; border-top: 1px solid rgba(255,255,255,0.05);">
                    <div style="font-size: 0.8rem; color: var(--text-muted);">
                        <i class="fas fa-magic"></i> Auto Analyse
                        <span class="info-tooltip" tabindex="0"><i class="fas fa-info-circle"></i><span class="info-tooltip-text">Auto analyses and processes session data whenever a new file is synced.</span></span>
                    </div>
                    <label class="toggle-switch" style="transform: scale(0.85); transform-origin: right center;">
                        <input type="checkbox" onchange="toggleAutoAnalyse(${d.id}, this.checked)" ${isAutoAnalyse ? 'checked' : ''}>
                        <span class="toggle-slider"></span>
                    </label>
                </div>` : ''}
            </div>
            `;
        }).join('');
    } catch (e) {
        deviceTokensCache = [];
        updateDeviceSetupChecklist();
        if (container) {
            container.innerHTML = '<span style="color: var(--error); font-size: 0.85rem;">Failed to load devices.</span>';
        }
    }
}

function updateDeviceSetupChecklist() {
    const heartbeatEl = document.getElementById('checklistHeartbeat');
    const tokenEl = document.getElementById('checklistToken');
    const syncEl = document.getElementById('checklistSync');
    if (!heartbeatEl || !tokenEl || !syncEl) return;

    const hasHeartbeat = !!isCloudConnected;
    const hasToken = Array.isArray(deviceTokensCache) && deviceTokensCache.some(device => !device.revoked);
    const hasSyncPath = hasToken;

    heartbeatEl.classList.toggle('is-complete', hasHeartbeat);
    tokenEl.classList.toggle('is-complete', hasToken);
    syncEl.classList.toggle('is-complete', hasSyncPath);
}

async function generateDeviceToken() {
    const nameInput = document.getElementById('newDeviceName');
    const deviceName = nameInput.value.trim() || 'RS-Core';

    try {
        const result = await apiCall('/api/devices/token', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_name: deviceName })
        });

        if (result && result.token) {
            // Show token once
            const display = document.getElementById('newTokenDisplay');
            const tokenInput = document.getElementById('newTokenValue');
            display.style.display = 'block';
            tokenInput.value = result.token;

            // Add "Provision" button to token display
            const provisionContainer = document.getElementById('tokenActionBtns');
            if (provisionContainer) {
                provisionContainer.innerHTML = `
                    <button class="btn btn-primary" onclick="openHotspotSetup('${result.token}')" style="flex: 1;">
                        <i class="fas fa-magic"></i> Auto-Setup Device
                    </button>
                    <button class="btn secondary" onclick="copyDeviceToken()" style="flex: 1;">
                        <i class="fas fa-copy"></i> Copy Token
                    </button>
                `;
            }

            nameInput.value = '';
            showToast('Device token generated!', 'success');
            deviceTokensCache = [{ id: 'new', revoked: false }, ...deviceTokensCache];
            updateDeviceSetupChecklist();
            loadDeviceTokens();
        }
    } catch (e) {
        showToast('Failed to generate token: ' + e.message, 'error');
    }
}

function copyDeviceToken() {
    const tokenInput = document.getElementById('newTokenValue');
    tokenInput.select();
    document.execCommand('copy');
    showToast('Token copied to clipboard!', 'success');
}

async function revokeDeviceToken(tokenId) {
    if (!confirm('Revoke this device token? The device will no longer be able to upload data.')) return;

    try {
        await apiCall(`/api/devices/${tokenId}`, { method: 'DELETE' });
        showToast('Token revoked', 'info');
        loadDeviceTokens();
    } catch (e) {
        showToast('Failed to revoke: ' + e.message, 'error');
    }
}

// ============================================================================
// MAGIC LINK PROVISIONING (Zero-Typing Setup)
// ============================================================================

function openHotspotSetup(token) {
    const modal = document.getElementById('hotspotSetupModal');
    if (!modal) return;

    // Pre-fill from localStorage if available
    const savedSsid = localStorage.getItem('provision_ssid') || '';
    const savedPass = localStorage.getItem('provision_pass') || '';

    document.getElementById('setupToken').value = token;
    document.getElementById('setupSsid').value = savedSsid;
    document.getElementById('setupPass').value = savedPass;

    modal.classList.add('active');
}

function closeHotspotSetup() {
    document.getElementById('hotspotSetupModal').classList.remove('active');
}

function generateMagicLink() {
    const ssid = document.getElementById('setupSsid').value.trim();
    const pass = document.getElementById('setupPass').value.trim();
    const token = document.getElementById('setupToken').value.trim();

    if (!ssid || !token) {
        showToast('SSID and Token are required', 'warning');
        return;
    }

    // Save for next time
    localStorage.setItem('provision_ssid', ssid);
    localStorage.setItem('provision_pass', pass);

    // Build Magic Link (using DNS setup.racesense as discussed)
    // IMPORTANT: We must explicitly pass the api_url so the device knows how to reach this specific production environment
    const targetApiUrl = API_BASE + '/api/upload';
    const magicUrl = `http://setup.racesense/setup?ssid=${encodeURIComponent(ssid)}&pass=${encodeURIComponent(pass)}&token=${encodeURIComponent(token)}&api_url=${encodeURIComponent(targetApiUrl)}`;

    // Update UI to show instructions
    document.getElementById('hotspotPrepSection').style.display = 'none';
    document.getElementById('hotspotLinkSection').style.display = 'block';

    const linkBtn = document.getElementById('magicLinkBtn');
    linkBtn.href = magicUrl;

    console.log('[Provisioning] Magic Link generated:', magicUrl);
}

function resetProvisioningUI() {
    document.getElementById('hotspotPrepSection').style.display = 'block';
    document.getElementById('hotspotLinkSection').style.display = 'none';
}

function getPairingTutorialSeenKey() {
    return currentUser ? `pairingTutorialSeen:${currentUser.id}` : 'pairingTutorialSeen:guest';
}

function getLedTutorialSeenKey() {
    return currentUser ? `ledTutorialSeen:${currentUser.id}` : 'ledTutorialSeen:guest';
}

function hasPairedDevice() {
    return Array.isArray(deviceTokensCache) && deviceTokensCache.some(device => !device.revoked && (device.device_uid || device.last_sync));
}

function shouldRunFirstTimeTutorials() {
    if (!currentUser) return false;
    const seenPairing = localStorage.getItem(getPairingTutorialSeenKey()) === 'true';
    const seenLed = localStorage.getItem(getLedTutorialSeenKey()) === 'true';
    if (seenPairing || seenLed) return false;
    return !hasPairedDevice();
}

function maybeOpenPairingTutorial() {
    if (!shouldRunFirstTimeTutorials()) return;
    const pairingModal = document.getElementById('pairingTutorialModal');
    const ledModal = document.getElementById('ledTutorialModal');
    if (pairingModal?.classList.contains('active') || ledModal?.classList.contains('active')) return;
    onboardingTutorialFlow = true;
    openPairingTutorial(true);
}

function openPairingTutorial(markSeen = false) {
    const modal = document.getElementById('pairingTutorialModal');
    const track = document.getElementById('pairingTutorialTrack');
    if (!modal || !track) return;

    modal.classList.add('active');
    pairingTutorialCurrentSlide = 0;
    selectPairingMode(pairingTutorialMode, false);

    if (!track.dataset.bound) {
        track.addEventListener('scroll', handlePairingTutorialScroll, { passive: true });
        track.dataset.bound = 'true';
    }

    goToPairingTutorialSlide(0, 'auto');
}

function closePairingTutorial() {
    const modal = document.getElementById('pairingTutorialModal');
    if (modal) modal.classList.remove('active');
    
    const dismissCb = document.getElementById('pairingTutorialDismissForever');
    if (dismissCb && dismissCb.checked && currentUser) {
        localStorage.setItem(getPairingTutorialSeenKey(), 'true');
        localStorage.setItem(getLedTutorialSeenKey(), 'true');
    }

    if (onboardingTutorialFlow) {
        if (dismissCb && dismissCb.checked) {
            onboardingTutorialFlow = false;
        } else {
            setTimeout(() => openLedTutorial(true), 120);
        }
    } else {
        onboardingTutorialFlow = false;
    }
}

function handlePairingTutorialScroll() {
    const track = document.getElementById('pairingTutorialTrack');
    if (!track) return;
    const slideWidth = track.clientWidth || 1;
    const nextIndex = Math.round(track.scrollLeft / slideWidth);
    if (nextIndex !== pairingTutorialCurrentSlide) {
        pairingTutorialCurrentSlide = nextIndex;
        updatePairingTutorialUI();
    }
}

function goToPairingTutorialSlide(index, behavior = 'smooth') {
    const track = document.getElementById('pairingTutorialTrack');
    if (!track) return;
    const slides = track.querySelectorAll('.pairing-slide');
    const clampedIndex = Math.max(0, Math.min(index, slides.length - 1));
    pairingTutorialCurrentSlide = clampedIndex;
    track.scrollTo({
        left: track.clientWidth * clampedIndex,
        behavior
    });
    updatePairingTutorialUI();
}

function stepPairingTutorial(direction) {
    const track = document.getElementById('pairingTutorialTrack');
    if (!track) return;
    const slides = track.querySelectorAll('.pairing-slide');
    if (!slides.length) return;

    if (pairingTutorialCurrentSlide >= slides.length - 1 && direction > 0) {
        closePairingTutorial();
        return;
    }

    goToPairingTutorialSlide(pairingTutorialCurrentSlide + direction);
}

function updatePairingTutorialUI() {
    const track = document.getElementById('pairingTutorialTrack');
    if (!track) return;

    const slides = Array.from(track.querySelectorAll('.pairing-slide'));
    slides.forEach((slide, index) => {
        slide.classList.toggle('is-active', index === pairingTutorialCurrentSlide);
    });

    document.querySelectorAll('[data-pairing-dot]').forEach((dot, index) => {
        dot.classList.toggle('active', index === pairingTutorialCurrentSlide);
    });

    const prevBtn = document.getElementById('pairingTutorialPrev');
    const nextBtn = document.getElementById('pairingTutorialNext');
    if (prevBtn) prevBtn.disabled = pairingTutorialCurrentSlide === 0;
    if (nextBtn) {
        nextBtn.textContent = pairingTutorialCurrentSlide === slides.length - 1 ? 'Done' : 'Next';
    }
}

function selectPairingMode(mode, jumpToSlide = true) {
    pairingTutorialMode = mode === 'wifi' ? 'wifi' : 'hotspot';

    const hotspotCard = document.getElementById('pairingModeHotspot');
    const wifiCard = document.getElementById('pairingModeWifi');
    hotspotCard?.classList.toggle('is-selected', pairingTutorialMode === 'hotspot');
    wifiCard?.classList.toggle('is-selected', pairingTutorialMode === 'wifi');

    const summary = document.getElementById('pairingModeSummary');
    if (summary) {
        if (pairingTutorialMode === 'wifi') {
            summary.innerHTML = `
                <div class="pairing-summary-head">Track or home WiFi works best when you return to the same place.</div>
                <div class="pairing-summary-body">Use this if the device usually comes back to one paddock, garage, or workshop network. The downside is that once you leave that WiFi range, sync stops until you pair another network.</div>
            `;
        } else {
            summary.innerHTML = `
                <div class="pairing-summary-head">Phone hotspot keeps things portable.</div>
                <div class="pairing-summary-body">Use this if you travel often, want the same setup everywhere, and don’t mind enabling hotspot only when you want sessions uploaded.</div>
            `;
        }
    }

    if (jumpToSlide) {
        goToPairingTutorialSlide(1);
    }
}

function openLedTutorial(markSeen = false) {
    const modal = document.getElementById('ledTutorialModal');
    const track = document.getElementById('ledTutorialTrack');
    if (!modal || !track) return;

    modal.classList.add('active');
    ledTutorialCurrentSlide = 0;

    if (!track.dataset.bound) {
        track.addEventListener('scroll', handleLedTutorialScroll, { passive: true });
        track.dataset.bound = 'true';
    }

    goToLedTutorialSlide(0, 'auto');
}

function closeLedTutorial() {
    const modal = document.getElementById('ledTutorialModal');
    if (modal) modal.classList.remove('active');
    
    const dismissCb = document.getElementById('ledTutorialDismissForever');
    if (dismissCb && dismissCb.checked && currentUser) {
        localStorage.setItem(getLedTutorialSeenKey(), 'true');
        localStorage.setItem(getPairingTutorialSeenKey(), 'true');
    }
    onboardingTutorialFlow = false;
}

function handleLedTutorialScroll() {
    const track = document.getElementById('ledTutorialTrack');
    if (!track) return;
    const slideWidth = track.clientWidth || 1;
    const nextIndex = Math.round(track.scrollLeft / slideWidth);
    if (nextIndex !== ledTutorialCurrentSlide) {
        ledTutorialCurrentSlide = nextIndex;
        updateLedTutorialUI();
    }
}

function goToLedTutorialSlide(index, behavior = 'smooth') {
    const track = document.getElementById('ledTutorialTrack');
    if (!track) return;
    const slides = track.querySelectorAll('.pairing-slide');
    const clampedIndex = Math.max(0, Math.min(index, slides.length - 1));
    ledTutorialCurrentSlide = clampedIndex;
    track.scrollTo({
        left: track.clientWidth * clampedIndex,
        behavior
    });
    updateLedTutorialUI();
}

function stepLedTutorial(direction) {
    const track = document.getElementById('ledTutorialTrack');
    if (!track) return;
    const slides = track.querySelectorAll('.pairing-slide');
    if (!slides.length) return;

    if (ledTutorialCurrentSlide >= slides.length - 1 && direction > 0) {
        closeLedTutorial();
        return;
    }

    goToLedTutorialSlide(ledTutorialCurrentSlide + direction);
}

function updateLedTutorialUI() {
    const track = document.getElementById('ledTutorialTrack');
    if (!track) return;

    const slides = Array.from(track.querySelectorAll('.pairing-slide'));
    slides.forEach((slide, index) => {
        slide.classList.toggle('is-active', index === ledTutorialCurrentSlide);
    });

    document.querySelectorAll('[data-led-dot]').forEach((dot, index) => {
        dot.classList.toggle('active', index === ledTutorialCurrentSlide);
    });

    const prevBtn = document.getElementById('ledTutorialPrev');
    const nextBtn = document.getElementById('ledTutorialNext');
    if (prevBtn) prevBtn.disabled = ledTutorialCurrentSlide === 0;
    if (nextBtn) {
        nextBtn.textContent = ledTutorialCurrentSlide === slides.length - 1 ? 'Done' : 'Next';
    }
}

function showAuthModal(mode) {
    const modal = document.getElementById('authModal');
    if (modal) {
        modal.style.display = 'flex';
        toggleAuthMode(mode || 'login');
    }
}

function closeAuthModal() {
    const modal = document.getElementById('authModal');
    if (modal) modal.style.display = 'none';
}

function toggleAuthMode(mode) {
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');
    const regSuccessPanel = document.getElementById('regSuccessPanel');
    if (mode === 'login') {
        if (loginForm) loginForm.style.display = 'block';
        if (registerForm) registerForm.style.display = 'none';
        if (regSuccessPanel) regSuccessPanel.style.display = 'none';
        // Clear any previous login errors
        const loginError = document.getElementById('loginError');
        if (loginError) { loginError.style.display = 'none'; loginError.textContent = ''; }
    } else if (mode === 'register') {
        if (loginForm) loginForm.style.display = 'none';
        if (registerForm) registerForm.style.display = 'block';
        if (regSuccessPanel) regSuccessPanel.style.display = 'none';
        // Clear any previous register errors
        const regError = document.getElementById('regError');
        if (regError) { regError.style.display = 'none'; regError.textContent = ''; }
    }
}

window.toggleDetailsSection = function (sectionId) {
    const el = document.getElementById(sectionId);
    if (!el) return;
    el.classList.toggle('collapsed');
};

async function submitLogin() {
    const email = document.getElementById('loginEmail')?.value || '';
    const password = document.getElementById('loginPassword')?.value || '';
    const errorEl = document.getElementById('loginError');

    try {
        const result = await apiCall('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
            displayError: false
        });
        if (result && result.success) {
            currentUser = result.user;
            await loadDeviceTokens();
            updateAuthUI();
            closeAuthModal();
            showToast('Logged in successfully', 'success');
            // Refresh data for current view
            showView(currentView);
            maybeOpenPairingTutorial();
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
            body: JSON.stringify({ name, email, password }),
            displayError: false
        });
        if (result && result.success) {
            // Show the registration success / pending approval panel
            const loginForm = document.getElementById('loginForm');
            const registerForm = document.getElementById('registerForm');
            const regSuccessPanel = document.getElementById('regSuccessPanel');
            if (loginForm) loginForm.style.display = 'none';
            if (registerForm) registerForm.style.display = 'none';
            if (regSuccessPanel) regSuccessPanel.style.display = 'block';
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
    deviceTokensCache = [];
    closeProfilePanel();
    updateAuthUI();
    showToast('Logged out', 'info');
}

/**
 * Ensures the full track metadata from Pi is pushed to the ESP32
 */
async function ensureTrackSynced(trackId, deviceIP) {
    try {
        console.log(`[Sync] Setting active track ${trackId} in cloud...`);
        const resp = await apiCall(`/api/tracks/${trackId}/active`, { method: 'POST' });
        if (resp && resp.success) {
            console.log(`[Sync] Track ${trackId} active in cloud`);
            lastSyncedTrackId = trackId;
            activeTrackId = trackId;
            if (currentUser) {
                currentUser.active_track_id = trackId;
            }
        }
    } catch (err) {
        console.error(`[Sync] Failed to set active track ${trackId}:`, err);
    }
}

// ============================================================================
// SOCIAL & COMMUNITY FEATURES
// ============================================================================

function switchCommunityTab(tab, skipViewLoad = false) {
    currentCommunityTab = tab;
    saveUiState('ui:communityTab', tab);

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

    if (skipViewLoad) return;

    // Load data
    if (tab === 'explore') {
        loadCommunitySessions();
    } else if (tab === 'following') {
        loadFollowingFeed();
    } else if (tab === 'leaderboards') {
        loadLeaderboardTracks().then(() => {
            if (readUiState('ui:leaderboardTrack', '')) loadLeaderboard();
        });
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
    if (!select) return;

    try {
        if (select.options.length <= 1) {
            const data = await apiCall('/api/tracks');
            select.innerHTML = '<option value="">Select Track...</option>' +
                data.tracks.map(t => `<option value="${t.track_id}">${t.track_name}</option>`).join('');
        }
        const savedTrackId = readUiState('ui:leaderboardTrack', '');
        const savedPeriod = readUiState('ui:leaderboardPeriod', 'all');
        if (savedTrackId) select.value = savedTrackId;
        const periodSelect = document.getElementById('lbPeriodSelect');
        if (periodSelect) periodSelect.value = savedPeriod;
    } catch (e) { }
}

async function loadLeaderboard() {
    const trackId = document.getElementById('lbTrackSelect').value;
    const period = document.getElementById('lbPeriodSelect').value;
    const container = document.getElementById('leaderboardContent');
    saveUiState('ui:leaderboardTrack', trackId || '');
    saveUiState('ui:leaderboardPeriod', period || 'all');

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
            <div class="table-responsive leaderboard-table">
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
            <div class="leaderboard-cards">
                ${leaderboard.map(entry => {
                    let rankDisplay = entry.rank;
                    if (entry.rank === 1) rankDisplay = '🥇';
                    else if (entry.rank === 2) rankDisplay = '🥈';
                    else if (entry.rank === 3) rankDisplay = '🥉';

                    return `
                        <div class="leaderboard-card" onclick="viewSession('${entry.session_id}', true)">
                            <div class="card-head-inline">
                                <span class="leaderboard-rank">${rankDisplay}</span>
                                <span class="leaderboard-time">${formatTime(entry.lap_time)}</span>
                            </div>
                            <div class="leaderboard-rider" onclick="event.stopPropagation(); showUserProfile(${entry.user_id})">${entry.user_name}</div>
                            <div class="leaderboard-meta">
                                <span>${entry.bike_info || 'Bike not set'}</span>
                                <span>${formatDateShort(entry.date)}</span>
                            </div>
                        </div>
                    `;
                }).join('')}
            </div>
        `;
    } catch (error) {
        container.innerHTML = renderErrorState('Failed to load leaderboard.');
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
                
                ${currentUser && currentUser.id == userId ? `
                    <div style="margin-bottom: 1.5rem;">
                        <button class="btn btn-secondary btn-sm" onclick="showView('settings')">
                            <i class="fas fa-cog"></i> Edit Profile & Security
                        </button>
                    </div>
                ` : ''}

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
            const canCreate = currentUser && (currentUser.subscription_tier === 'team');
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

function normalizeQuery(value) {
    return (value || '').trim().toLowerCase();
}

function handleTrackSearchInput() {
    const input = document.getElementById('tracksSearchInput');
    trackSearchQuery = input ? input.value : '';
    saveUiState('ui:tracksSearch', trackSearchQuery);
    renderTracksGrid(tracks);
}

function handleSessionSearchInput() {
    const input = document.getElementById('sessionSearchInput');
    sessionSearchQuery = input ? input.value : '';
    saveUiState('ui:sessionSearch', sessionSearchQuery);
    renderSessionsList(sessions);
}

function handleCommunitySearchInput() {
    const input = document.getElementById('communitySearchInput');
    communitySearchQuery = input ? input.value : '';
    saveUiState('ui:communitySearch', communitySearchQuery);
    const trackId = document.getElementById('communityTrackFilter')?.value || '';
    saveUiState('ui:communityTrackFilter', trackId);
    loadCommunitySessions();
}

function renderErrorState(message) {
    return `<div class="empty-state"><div class="empty-state-icon">!</div><div class="empty-state-title">Something went wrong</div><div class="empty-state-message">${message}</div></div>`;
}

function refreshHomeContextBanner() {
    updateHomeContextBanner(Array.isArray(sessions) ? sessions.length : 0);
}

async function loadHomeData() {
    if (!currentUser) return;

    try {
        // Load tracks and sessions
        const [tracksData, sessionsData] = await Promise.all([
            apiCall('/api/tracks'),
            apiCall('/api/sessions')
        ]);

        tracks = tracksData.tracks || [];
        sessions = sessionsData || [];

        // === GREETING ===
        updateHomeGreeting();

        // === CONTEXT BANNER ===
        refreshHomeContextBanner();
        maybeOpenPairingTutorial();

        // === STATS with count-up animation ===
        animateCountUp('totalTracks', tracks.length);
        animateCountUp('totalSessions', sessions.length);

        if (sessions.length > 0) {
            const lastSession = sessions[0];
            const lastDate = new Date(lastSession.start_time);
            const daysDiff = Math.floor((Date.now() - lastDate) / (1000 * 60 * 60 * 24));
            let timeAgo;
            if (daysDiff === 0) timeAgo = 'Today';
            else if (daysDiff === 1) timeAgo = 'Yesterday';
            else if (daysDiff < 7) timeAgo = `${daysDiff} days ago`;
            else timeAgo = lastDate.toLocaleDateString();

            document.getElementById('recentSession').textContent = timeAgo;
            const trackEl = document.getElementById('recentSessionTrack');
            if (trackEl) trackEl.textContent = lastSession.track_name || '';
        } else {
            document.getElementById('recentSession').textContent = 'None yet';
            const trackEl = document.getElementById('recentSessionTrack');
            if (trackEl) trackEl.textContent = 'Head to Sync Data to get started';
        }

        // Show recent sessions (last 5)
        renderRecentSessions(sessions.slice(0, 5));

    } catch (error) {
        console.error('Failed to load home data:', error);
    }
}

// === HOME GREETING ===
function updateHomeGreeting() {
    const greetingEl = document.getElementById('greetingText');
    const subEl = document.getElementById('greetingSub');
    if (!greetingEl) return;

    const hour = new Date().getHours();
    const name = (currentUser && currentUser.name) ? currentUser.name.split(' ')[0] : '';

    let greeting, sub;
    if (hour < 5) {
        greeting = name ? `Burning the midnight oil, ${name}?` : 'Late night session?';
        sub = 'Reviewing data while the world sleeps.';
    } else if (hour < 12) {
        greeting = name ? `Good morning, ${name} 🏍️` : 'Good morning 🏍️';
        sub = 'Ready to review your rides?';
    } else if (hour < 17) {
        greeting = name ? `Good afternoon, ${name}` : 'Good afternoon';
        sub = "Let's see how you're doing on track.";
    } else if (hour < 21) {
        greeting = name ? `Good evening, ${name}` : 'Good evening';
        sub = 'Time to analyze the day\'s laps.';
    } else {
        greeting = name ? `Hey ${name}, still at it?` : 'Evening rider';
        sub = 'Reviewing telemetry before bed?';
    }

    greetingEl.textContent = greeting;
    if (subEl) subEl.textContent = sub;
}

// === HOME CONTEXT BANNER ===
function updateHomeContextBanner(sessionCount) {
    const banner = document.getElementById('homeContextBanner');
    const icon = document.getElementById('contextBannerIcon');
    const title = document.getElementById('contextBannerTitle');
    const detail = document.getElementById('contextBannerDetail');
    const action = document.getElementById('contextBannerAction');
    if (!banner) return;

    const isConnected = isDeviceConnected;
    const hasKnownDevice = Array.isArray(deviceTokensCache) && deviceTokensCache.some(device => !device.revoked);

    if (isConnected) {
        // Device is connected
        banner.style.display = 'block';
        banner.className = 'home-context-banner context-connected';
        icon.innerHTML = '<i class="fas fa-satellite-dish"></i>';
        title.textContent = 'Auto synced and processed from RS core';
        detail.textContent = 'Your device is online and automatically syncing telemetry.';
        action.innerHTML = '';
    } else if (sessionCount === 0) {
        // Brand new user
        banner.style.display = 'block';
        banner.className = 'home-context-banner context-welcome';
        icon.innerHTML = '<i class="fas fa-rocket"></i>';
        title.textContent = 'Welcome to RaceSense!';
        detail.textContent = 'Pair your RS-Core first, then your first synced session will show up here.';
        action.innerHTML = '<button class="btn btn-sm btn-primary" onclick="openPairingTutorial(true)"><i class="fas fa-link"></i> How To Pair</button>';
    } else if (!hasKnownDevice) {
        // Has sessions but no device token configured
        banner.style.display = 'block';
        banner.className = 'home-context-banner context-nodevice';
        icon.innerHTML = '<i class="fas fa-plug"></i>';
        title.textContent = 'No RS-Core detected';
        detail.textContent = 'Generate a device token and complete pairing to sync new sessions.';
        action.innerHTML = '<button class="btn btn-sm secondary" onclick="showView(\'settings\')"><i class="fas fa-cog"></i> Device Settings</button>';
    } else {
        // Device token exists but no recent heartbeat
        banner.style.display = 'block';
        banner.className = 'home-context-banner context-offline';
        icon.innerHTML = '<i class="fas fa-wifi" style="opacity: 0.5;"></i>';
        title.textContent = 'RS-Core is offline';
        detail.textContent = 'Your module will auto-sync when it reconnects.';
        action.innerHTML = '';
    }
}

// === COUNT-UP ANIMATION ===
function animateCountUp(elementId, target) {
    const el = document.getElementById(elementId);
    if (!el) return;

    const duration = 800; // ms
    const start = 0;
    const startTime = performance.now();

    if (target === 0) {
        el.textContent = '0';
        return;
    }

    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        // Ease-out cubic
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = Math.round(start + (target - start) * eased);
        el.textContent = current;
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

function renderRecentSessions(recentSessions) {
    const container = document.getElementById('recentSessionsList');

    if (!recentSessions || recentSessions.length === 0) {
        container.innerHTML = renderEmptyState(
            '🏁',
            'No sessions yet',
            'Head to Sync Data to upload your first ride, or connect your RS-Core to auto-upload.',
            'Go to Sync Data',
            "showView('process')"
        );
        return;
    }

    const session = recentSessions[0];
    
    let greetingMsg = "Solid riding!";
    let detailMsg = `Your session at ${session.track_name || 'the track'} is ready to view.`;
    
    if (session.tbl_improved) {
        greetingMsg = "New TBL!";
        detailMsg = `Incredible! You set a new TBL at ${session.track_name}.`;
    } else if (session.is_personal_best) {
        greetingMsg = "New Personal Best!";
        detailMsg = `You clocked your fastest lap at ${session.track_name}.`;
    } else if (session.best_lap_time) {
        greetingMsg = `Best lap: ${formatTime(session.best_lap_time)}`;
        detailMsg = `Nice consistent lines at ${session.track_name}.`;
    }

    // Dynamic banner with neon styling matching the app's aesthetic
    container.innerHTML = `
        <div class="session-card greeting-card" style="padding: 2.5rem 1.5rem; text-align: center; border: 1px solid rgba(0, 255, 170, 0.3); background: linear-gradient(135deg, rgba(20,20,20,0.9) 0%, rgba(0,255,170,0.05) 100%); cursor: pointer; transition: transform 0.2s, box-shadow 0.2s;" onclick="viewSession('${session.session_id}')" onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 8px 24px rgba(0,255,170,0.15)';" onmouseout="this.style.transform='none'; this.style.boxShadow='none';">
            <div style="font-size: 3rem; margin-bottom: 1rem; color: var(--primary);"><i class="fas fa-flag-checkered"></i></div>
            <h3 style="margin-bottom: 0.5rem; color: #fff; font-size: 1.5rem;">${greetingMsg}</h3>
            <p style="color: var(--text-muted); margin-bottom: 1.5rem; font-size: 0.95rem;">${detailMsg}</p>
            <button class="btn btn-primary" style="padding: 0.6rem 1.5rem; font-weight: 600;"><i class="fas fa-chart-line" style="margin-right: 0.5rem;"></i> View Dashboard</button>
        </div>
    `;
}

// ============================================================================
// TRACKS VIEW
// ============================================================================

async function loadTracks() {
    const container = document.getElementById('tracksList');
    const searchInput = document.getElementById('tracksSearchInput');
    if (searchInput) searchInput.value = trackSearchQuery;
    container.innerHTML = renderSkeletonCards(4, 'track');

    try {
        const data = await apiCall('/api/tracks');
        tracks = data.tracks || [];
        renderTracksGrid(tracks);
    } catch (error) {
        container.innerHTML = renderErrorState('Failed to load tracks.');
    }
}

function renderTracksGrid(trackList) {
    const container = document.getElementById('tracksList');
    if (!container) return;

    const query = normalizeQuery(trackSearchQuery);
    const filteredTracks = (trackList || []).filter(track => {
        if (!query) return true;
        return `${track.track_name || ''} ${track.location || ''}`.toLowerCase().includes(query);
    });

    if (!trackList || trackList.length === 0) {
        container.innerHTML = renderEmptyState(
            '🗺️',
            'No tracks yet',
            'Tracks are auto-detected when you analyze ride sessions. Head to Sync Data to import your first ride.',
            'Go to Sync Data',
            "showView('process')"
        );
        return;
    }

    if (filteredTracks.length === 0) {
        container.innerHTML = renderEmptyState(
            '🔎',
            'No matching tracks',
            'Try a different track name or clear the search.'
        );
        return;
    }

    container.innerHTML = filteredTracks.map(track => {
        const isActive = activeTrackId == track.track_id;
        const isGlobal = track.track_scope === 'global';
        const mapMarkup = isGlobal
            ? `<div id="trackCardMap${track.track_id}" class="track-map"><div class="loading">Loading track map...</div></div>`
            : `<img src="${API_BASE}/api/tracks/${track.track_id}/map" 
                 alt="${track.track_name}" 
                 class="track-map"
                 onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22300%22 height=%22200%22%3E%3Crect fill=%22%232a2a2a%22 width=%22300%22 height=%22200%22/%3E%3Ctext x=%2250%25%22 y=%2250%25%22 fill=%22%23666%22 text-anchor=%22middle%22%3ENo Map%3C/text%3E%3C/svg%3E'">`;
        return `
        <div class="track-card ${isActive ? 'active' : ''}" onclick="viewTrack(${track.track_id})">
            ${mapMarkup}
            <div class="track-info">
                <div class="card-head-inline">
                    <div class="track-name">${track.track_name}</div>
                    ${isActive ? '<span class="badge success compact-badge">ACTIVE</span>' : ''}
                </div>
                <div class="track-meta">
                    <span><i class="fas fa-database"></i> ${isGlobal ? 'Shared Track' : 'Private Fallback'}</span>
                    <span><i class="fas fa-history"></i> ${track.sessions_count || 0} sessions</span>
                    <span><i class="fas fa-vector-square"></i> ${isGlobal ? 'Canonical layout' : 'Session geometry'}</span>
                </div>
                <div class="track-actions">
                    ${!isActive ? `
                    <button class="btn btn-primary btn-sm" onclick="event.stopPropagation(); setActiveTrack(${track.track_id})">
                        <i class="fas fa-bolt"></i> Set Active
                    </button>` : ''}
                    ${isGlobal ? '' : `
                    <button class="btn small" onclick="event.stopPropagation(); renameTrack(${track.track_id}, '${track.track_name}')">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-danger btn-sm" onclick="event.stopPropagation(); deleteTrack(${track.track_id}, '${track.track_name}')">
                        <i class="fas fa-trash"></i>
                    </button>`}
                </div>
            </div>
        </div>
        `;
    }).join('');

    loadTracksGridCanonicalMaps(filteredTracks);
}

async function loadTracksGridCanonicalMaps(trackList) {
    const globalTracks = (trackList || []).filter(track => track.track_scope === 'global' && track.has_canonical_layout);
    await Promise.all(globalTracks.map(async track => {
        const slot = document.getElementById(`trackCardMap${track.track_id}`);
        if (!slot) return;
        try {
            const layout = await apiCall(`/api/tracks/${track.track_id}/layout`, { displayError: false });
            slot.outerHTML = generateCanonicalTrackSVG(layout, null, { compact: true, maxHeight: 220, hideFrame: true });
        } catch (error) {
            slot.outerHTML = `<img src="${API_BASE}/api/tracks/${track.track_id}/map" 
                 alt="${track.track_name}" 
                 class="track-map"
                 onerror="this.src='data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22300%22 height=%22200%22%3E%3Crect fill=%22%232a2a2a%22 width=%22300%22 height=%22200%22/%3E%3Ctext x=%2250%25%22 y=%2250%25%22 fill=%22%23666%22 text-anchor=%22middle%22%3ENo Map%3C/text%3E%3C/svg%3E'">`;
        }
    }));
}

function projectTelemetryToCanonicalRaw(layout, telemetry) {
    if (!layout || !telemetry || !telemetry.lats || !telemetry.lons) return [];
    const ref = layout.geo_reference;
    const align = layout.auto_align;
    if (!ref) return [];
    const affineFit = layout.affine_fit;

    return telemetry.lats.map((lat, index) => {
        const lon = telemetry.lons[index];
        if (lat == null || lon == null || !Number.isFinite(lat) || !Number.isFinite(lon)) {
            return null;
        }
        const localX = (lon - ref.lon0) * ref.metersPerDegLon;
        const localY = (ref.lat0 - lat) * ref.metersPerDegLat;
        if (affineFit?.x_coeffs?.length === 3 && affineFit?.y_coeffs?.length === 3) {
            return {
                x: affineFit.x_coeffs[0] * localX + affineFit.x_coeffs[1] * localY + affineFit.x_coeffs[2],
                y: affineFit.y_coeffs[0] * localX + affineFit.y_coeffs[1] * localY + affineFit.y_coeffs[2],
            };
        }
        if (!align) return { x: localX, y: localY };
        const theta = (align.rotationDeg || 0) * Math.PI / 180;
        const cosT = Math.cos(theta);
        const sinT = Math.sin(theta);
        const scale = align.scale || 1;
        const rotX = localX * cosT - localY * sinT;
        const rotY = localX * sinT + localY * cosT;
        return {
            x: rotX * scale + align.translateX,
            y: rotY * scale + align.translateY,
        };
    });
}

function projectLatLonToCanonical(layout, lat, lon) {
    if (!layout || !Number.isFinite(lat) || !Number.isFinite(lon)) return null;
    const projected = projectTelemetryToCanonicalRaw(layout, { lats: [lat], lons: [lon] });
    return projected?.[0] || null;
}

function canonicalSectorMarkers(layout) {
    if (!layout?.sectors?.length) return [];
    return layout.sectors
        .map((sector, index) => {
            const point = projectLatLonToCanonical(layout, Number(sector.end_lat), Number(sector.end_lon));
            if (!point) return null;
            const sectorIndex = Number(sector.sector_index);
            return {
                id: sector.id || `S${index + 1}`,
                label: Number.isFinite(sectorIndex) && sectorIndex > 0 ? `S${sectorIndex}` : (sector.id || `S${index + 1}`),
                x: point.x,
                y: point.y,
            };
        })
        .filter(Boolean);
}

function rotatePointAround(point, center, angleRad) {
    const dx = point.x - center.x;
    const dy = point.y - center.y;
    const cosA = Math.cos(angleRad);
    const sinA = Math.sin(angleRad);
    return {
        x: center.x + dx * cosA - dy * sinA,
        y: center.y + dx * sinA + dy * cosA,
    };
}

function nearestPointDistance(point, cloud) {
    let best = Number.POSITIVE_INFINITY;
    for (let i = 0; i < cloud.length; i += 1) {
        const dx = point.x - cloud[i].x;
        const dy = point.y - cloud[i].y;
        const dist = dx * dx + dy * dy;
        if (dist < best) best = dist;
    }
    return best;
}

function estimateCanonicalCorrection(layout, projectedPoints) {
    const template = (layout?.sampled_points || [])
        .map(point => point?.canonical)
        .filter(point => point && Number.isFinite(point.x) && Number.isFinite(point.y));
    const validProjected = (projectedPoints || []).filter(point => point && Number.isFinite(point.x) && Number.isFinite(point.y));
    if (template.length < 12 || validProjected.length < 12) return null;

    const sampleStep = Math.max(1, Math.floor(validProjected.length / 240));
    const samples = validProjected.filter((_, index) => index % sampleStep === 0);
    const templateCenter = template.reduce((acc, point) => ({ x: acc.x + point.x, y: acc.y + point.y }), { x: 0, y: 0 });
    templateCenter.x /= template.length;
    templateCenter.y /= template.length;

    const sampleCenter = samples.reduce((acc, point) => ({ x: acc.x + point.x, y: acc.y + point.y }), { x: 0, y: 0 });
    sampleCenter.x /= samples.length;
    sampleCenter.y /= samples.length;

    let best = {
        angle: 0,
        tx: templateCenter.x - sampleCenter.x,
        ty: templateCenter.y - sampleCenter.y,
        error: Number.POSITIVE_INFINITY,
    };

    const evaluate = (angleDeg, tx, ty) => {
        const angleRad = angleDeg * Math.PI / 180;
        let error = 0;
        for (let i = 0; i < samples.length; i += 1) {
            const rotated = rotatePointAround(samples[i], sampleCenter, angleRad);
            const adjusted = { x: rotated.x + tx, y: rotated.y + ty };
            error += nearestPointDistance(adjusted, template);
        }
        return error / samples.length;
    };

    const pass = (angleRange, angleStep, shiftRange, shiftStep, seed) => {
        let localBest = seed;
        for (let angle = seed.angle - angleRange; angle <= seed.angle + angleRange; angle += angleStep) {
            for (let tx = seed.tx - shiftRange; tx <= seed.tx + shiftRange; tx += shiftStep) {
                for (let ty = seed.ty - shiftRange; ty <= seed.ty + shiftRange; ty += shiftStep) {
                    const error = evaluate(angle, tx, ty);
                    if (error < localBest.error) {
                        localBest = { angle, tx, ty, error };
                    }
                }
            }
        }
        return localBest;
    };

    best = pass(8, 1, 90, 15, best);
    best = pass(1.5, 0.25, 18, 3, best);

    return best;
}

function applyCanonicalCorrection(points, correction) {
    if (!correction) return points;
    const validPoints = points.filter(point => point && Number.isFinite(point.x) && Number.isFinite(point.y));
    if (!validPoints.length) return points;
    const center = validPoints.reduce((acc, point) => ({ x: acc.x + point.x, y: acc.y + point.y }), { x: 0, y: 0 });
    center.x /= validPoints.length || 1;
    center.y /= validPoints.length || 1;
    const angleRad = correction.angle * Math.PI / 180;
    return points.map(point => {
        if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y)) return null;
        const rotated = rotatePointAround(point, center, angleRad);
        return {
            x: rotated.x + correction.tx,
            y: rotated.y + correction.ty,
        };
    });
}

function projectTelemetryToCanonical(layout, telemetry) {
    const projected = projectTelemetryToCanonicalRaw(layout, telemetry);
    if (!projected.length) return projected;
    if (layout?.affine_fit?.x_coeffs?.length === 3 && layout?.affine_fit?.y_coeffs?.length === 3) {
        return projected;
    }
    const correction = estimateCanonicalCorrection(layout, projected);
    return applyCanonicalCorrection(projected, correction);
}

function generateCanonicalTrackSVG(layout, telemetry = null, options = {}) {
    const baseSvg = layout?.preview_svg_data_url || layout?.svg_data_url;
    if (!layout || !baseSvg) {
        return '<p class="help-text">Canonical layout unavailable</p>';
    }

    const width = layout.layout_width || 1200;
    const height = layout.layout_height || 800;
    const points = telemetry ? projectTelemetryToCanonical(layout, telemetry) : [];
    const pathData = points.length
        ? `M ${points.map(point => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(' L ')}`
        : '';
    const stroke = options.stroke || '#c85b12';
    const strokeWidth = options.strokeWidth || 8;
    const sectorMarkers = canonicalSectorMarkers(layout);
    const markerRadius = Math.max(10, strokeWidth * 1.1);
    const markerFontSize = Math.max(16, strokeWidth * 1.35);
    const frameStyle = options.hideFrame
        ? ''
        : `background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:${options.compact ? '0.5rem' : '1rem'}; margin:${options.title ? '1rem 0' : '0'};`;

    return `
        <div class="${options.hideFrame ? 'track-map' : ''}" style="${frameStyle}">
            ${options.title ? `<h3 style="margin:0 0 1rem 0;">${options.title}</h3>` : ''}
            <svg viewBox="0 0 ${width} ${height}" style="width:100%; height:auto; max-height:${options.maxHeight || 520}px;">
                <image href="${baseSvg}" x="0" y="0" width="${width}" height="${height}" preserveAspectRatio="xMidYMid meet"></image>
                ${sectorMarkers.map(marker => `
                    <g>
                        <circle cx="${marker.x.toFixed(2)}" cy="${marker.y.toFixed(2)}" r="${markerRadius}" fill="rgba(20,108,67,0.95)" stroke="#f3efe7" stroke-width="3"></circle>
                        <text x="${(marker.x + markerRadius + 8).toFixed(2)}" y="${(marker.y - markerRadius + 4).toFixed(2)}" text-anchor="start" font-size="${markerFontSize}" font-weight="800" fill="#ffffff" stroke="rgba(0,0,0,0.85)" stroke-width="5" paint-order="stroke fill">${marker.label}</text>
                    </g>
                `).join('')}
                ${pathData ? `<path d="${pathData}" fill="none" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round" opacity="0.95"></path>` : ''}
                ${points.length ? `<circle cx="${points[0].x}" cy="${points[0].y}" r="${Math.max(5, strokeWidth * 0.75)}" fill="#4CAF50" stroke="#111" stroke-width="2"></circle>` : ''}
            </svg>
        </div>
    `;
}

function telemetryToSimpleArrays(telemetry) {
    if (!telemetry) return null;
    if (Array.isArray(telemetry)) {
        return {
            lats: telemetry.map(point => point.lat),
            lons: telemetry.map(point => point.lon),
            speeds: telemetry.map(point => point.speed),
            times: telemetry.map(point => point.time)
        };
    }
    return {
        lats: telemetry.lat || telemetry.lats || [],
        lons: telemetry.lon || telemetry.lons || [],
        speeds: telemetry.speed || telemetry.speeds || [],
        times: telemetry.time || telemetry.times || []
    };
}

function generateCanonicalComparisonSVG(layout, telemetryA, telemetryB, options = {}) {
    const baseSvg = layout?.preview_svg_data_url || layout?.svg_data_url;
    if (!layout || !baseSvg) return '<p class="help-text">Canonical layout unavailable</p>';

    const width = layout.layout_width || 1200;
    const height = layout.layout_height || 800;
    const first = projectTelemetryToCanonical(layout, telemetryToSimpleArrays(telemetryA));
    const second = projectTelemetryToCanonical(layout, telemetryToSimpleArrays(telemetryB));
    const pathA = first.length ? `M ${first.map(point => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(' L ')}` : '';
    const pathB = second.length ? `M ${second.map(point => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(' L ')}` : '';
    const sectorMarkers = canonicalSectorMarkers(layout);

    return `
        <div style="background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:${options.compact ? '0.5rem' : '1rem'};">
            <svg viewBox="0 0 ${width} ${height}" style="width:100%; height:auto; max-height:${options.maxHeight || 520}px;">
                <image href="${baseSvg}" x="0" y="0" width="${width}" height="${height}" preserveAspectRatio="xMidYMid meet"></image>
                ${sectorMarkers.map(marker => `
                    <g>
                        <circle cx="${marker.x.toFixed(2)}" cy="${marker.y.toFixed(2)}" r="${Math.max(11, (options.strokeWidth || 10) * 1.05)}" fill="rgba(20,108,67,0.9)" stroke="#f3efe7" stroke-width="3"></circle>
                        <text x="${marker.x.toFixed(2)}" y="${(marker.y + 4).toFixed(2)}" text-anchor="middle" font-size="${Math.max(16, (options.strokeWidth || 10) * 1.25)}" font-weight="700" fill="#ffffff">${marker.label}</text>
                    </g>
                `).join('')}
                ${pathA ? `<path d="${pathA}" fill="none" stroke="#4CAF50" stroke-width="${options.strokeWidth || 10}" stroke-linecap="round" stroke-linejoin="round" opacity="0.92"></path>` : ''}
                ${pathB ? `<path d="${pathB}" fill="none" stroke="#F44336" stroke-width="${options.strokeWidth || 10}" stroke-linecap="round" stroke-linejoin="round" opacity="0.92"></path>` : ''}
            </svg>
        </div>
    `;
}

/**
 * Manually set the active track in user profile
 */
async function setActiveTrack(trackId) {
    try {
        await apiCall(`/api/tracks/${trackId}/active`, { method: 'POST' });

        // Update local state and UI immediately
        activeTrackId = trackId;
        const result = await apiCall('/api/auth/me'); // Refresh profile silently
        if (result) currentUser = result;

        showToast('Track set as active (Device will sync on next heartbeat)', 'success');
        loadTracks(); // Refresh tracks view to show active state
    } catch (err) {
        showToast('Failed to set track', 'error');
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
        if (track.track_scope === 'global' && track.has_canonical_layout) {
            try {
                const layout = await apiCall(`/api/tracks/${trackId}/layout`, { displayError: false });
                mapDisplay = generateCanonicalTrackSVG(layout, null, { maxHeight: 640 });
            } catch (e) {
                mapDisplay = `<img src="${API_BASE}/api/tracks/${trackId}/map" 
                    alt="${track.track_name}" 
                    style="width: 100%; max-width: 800px; border-radius: 8px; margin: 1rem 0;"
                    onerror="this.style.display='none'">`;
            }
        } else {
            try {
                const geometry = await apiCall(`/api/tracks/${trackId}/geometry`, { displayError: false });
                mapDisplay = generateTrackMapSVG(geometry, null, null, { title: '' });
            } catch (e) {
                mapDisplay = `<img src="${API_BASE}/api/tracks/${trackId}/map" 
                     alt="${track.track_name}" 
                     style="width: 100%; max-width: 600px; border-radius: 8px; margin: 1rem 0;"
                     onerror="this.style.display='none'">`;
            }
        }

        const isActive = activeTrackId == trackId;
        container.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <h2>${track.track_name}</h2>
                <div>
                ${isActive ? '<span class="badge success">ACTIVE ON DEVICE</span>' : `
                    <button class="btn btn-primary" onclick="setActiveTrack(${trackId})">
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
                        <div class="stat-label">Track Type</div>
                        <div class="stat-value" style="font-size: 1rem;">${track.track_scope === 'global' ? 'Shared Package' : 'Private Fallback'}</div>
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
        `;
    } catch (error) {
        container.innerHTML = '<p class="help-text">Failed to load track</p>';
    }
}

function viewTrackSessions(trackId) {
    pendingSessionTrackFilter = trackId != null ? String(trackId) : null;
    currentSessionTab = 'sessions';
    saveUiState('ui:sessionTab', 'sessions');
    showView('sessions');
    switchSessionTab('sessions');
}

// ============================================================================
// SESSIONS VIEW
// ============================================================================

function sessionTrackFilterLabel(track) {
    const baseName = track?.track_name || 'Unknown Track';
    const scopeLabel = track?.track_scope === 'global' ? 'Canonical' : 'Fallback';
    return `${baseName} (${scopeLabel})`;
}

function populateSessionTrackFilterOptions(filterSelect, trackItems, selectedTrackId = '') {
    if (!filterSelect) return;
    filterSelect.innerHTML = '<option value="">All Tracks</option>' +
        (trackItems || []).map(track =>
            `<option value="${track.track_id}">${sessionTrackFilterLabel(track)}</option>`
        ).join('');
    filterSelect.value = selectedTrackId ? String(selectedTrackId) : '';
}

async function loadSessions(filterTrackId = null) {
    const container = document.getElementById('sessionsList');
    const filterSelect = document.getElementById('trackFilter');
    const searchInput = document.getElementById('sessionSearchInput');
    if (searchInput) searchInput.value = sessionSearchQuery;

    container.innerHTML = renderSkeletonCards(3, 'session');

    try {
        const endpoint = filterTrackId ? `/api/sessions?track_id=${filterTrackId}` : '/api/sessions';
        const [tracksData, sessionsData] = await Promise.all([
            apiCall('/api/tracks'),
            apiCall(endpoint),
        ]);

        populateSessionTrackFilterOptions(filterSelect, tracksData?.tracks || [], filterTrackId || '');
        filterSelect.onchange = (e) => {
            const trackId = e.target.value ? parseInt(e.target.value, 10) : null;
            loadSessions(trackId);
        };

        sessions = sessionsData || [];
        renderSessionsList(sessions);

    } catch (error) {
        container.innerHTML = renderErrorState('Failed to load sessions.');
    }
}

function renderSessionQuickActions(session, isPublicView = false) {
    if (isPublicView) {
        return '';
    }

    return `
        <div class="session-quick-actions">
            <button class="btn small" onclick="event.stopPropagation(); openPlayback('${session.session_id}')">
                <i class="fas fa-play"></i> Playback
            </button>
            <button class="btn small secondary" onclick="event.stopPropagation(); shareSession('${session.session_id}')">
                <i class="fas fa-share-alt"></i> Share
            </button>
        </div>
    `;
}

function renderSessionsList(sessionList) {
    const container = document.getElementById('sessionsList');
    if (!container) return;

    if (!sessionList || sessionList.length === 0) {
        container.innerHTML = renderEmptyState(
            '📊',
            'No sessions yet',
            'Upload a CSV from your RS-Core in the Sync Data tab, then analyze it to see your sessions here.',
            'Go to Sync Data',
            "showView('process')"
        );
        return;
    }

    const query = normalizeQuery(sessionSearchQuery);
    const filteredSessions = sessionList.filter(session => {
        if (!query) return true;
        return `${session.track_name || ''} ${formatDateTimeAbbreviated(session.start_time)}`.toLowerCase().includes(query);
    });

    if (filteredSessions.length === 0) {
        container.innerHTML = renderEmptyState(
            '🔎',
            'No matching sessions',
            'Try a different track name or clear the search.'
        );
        return;
    }

    const grouped = groupSessionsByDate(filteredSessions);

    container.innerHTML = Object.entries(grouped).map(([date, dateSessions]) => `
        <div class="session-date-group">
            <h3>${date}</h3>
            ${dateSessions.map(session => `
                <div class="session-card" onclick="viewSession('${session.session_id}')">
                    <div class="session-header">
                        <div class="session-title">${session.track_name}</div>
                        <div class="session-time">${formatTime24h(session.start_time)}</div>
                    </div>
                    <div class="session-stats">
                        <div class="session-stat">
                            <span>Laps</span>
                            <strong>${session.total_laps}</strong>
                        </div>
                        <div class="session-stat">
                            <span>Best</span>
                            <strong>${formatTime(session.best_lap_time)}</strong>
                        </div>
                        <div class="session-stat">
                            <span>Duration</span>
                            <strong>${formatDuration(session.duration_sec)}</strong>
                        </div>
                        ${session.is_public ? '<span class="badge status-pill-public"><i class="fas fa-globe"></i> Public</span>' : ''}
                        ${session.tbl_improved ? '<span class="badge success">New TBL!</span>' : ''}
                    </div>
                    ${renderSessionQuickActions(session)}
                </div>
            `).join('')}
        </div>
    `).join('');
}

// ============================================================================
// COMMUNITY VIEW
// ============================================================================

async function loadCommunitySessions() {
    const container = document.getElementById('communitySessionsList');
    const filterSelect = document.getElementById('communityTrackFilter');
    const searchInput = document.getElementById('communitySearchInput');
    if (searchInput) searchInput.value = communitySearchQuery;

    container.innerHTML = renderSkeletonCards(3, 'session');

    try {
        // Populate filter dropdown if empty
        if (filterSelect.options.length <= 1) {
            const tracksData = await apiCall('/api/tracks');
            filterSelect.innerHTML = '<option value="">All Tracks</option>' +
                tracksData.tracks.map(t => `<option value="${t.track_id}">${t.track_name}</option>`).join('');
            const savedTrackId = readUiState('ui:communityTrackFilter', '');
            if (savedTrackId) filterSelect.value = savedTrackId;
        }

        const trackId = filterSelect.value ? parseInt(filterSelect.value) : null;
        const endpoint = trackId ? `/api/public/sessions?track_id=${trackId}` : '/api/public/sessions';
        const publicSessions = await apiCall(endpoint);

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

        const query = normalizeQuery(communitySearchQuery);
        const filteredSessions = publicSessions.filter(session => {
            if (!query) return true;
            return `${session.track_name || ''} ${session.owner_name || ''}`.toLowerCase().includes(query);
        });

        if (filteredSessions.length === 0) {
            container.innerHTML = renderEmptyState(
                '🔎',
                'No matching public sessions',
                'Try a different rider or track search.'
            );
            return;
        }

        saveUiState('ui:communityTrackFilter', filterSelect.value || '');

        container.innerHTML = filteredSessions.map(session => `
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
                ${renderSessionQuickActions(session, true)}
            </div>
        `).join('');

    } catch (error) {
        container.innerHTML = renderErrorState('Failed to load community sessions.');
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
    currentSessionTab = tab;
    saveUiState('ui:sessionTab', tab);

    // Update tab buttons
    document.querySelectorAll('[data-tab]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tab);
    });

    // Show/hide panels
    document.getElementById('sessionsPanel').style.display = tab === 'sessions' ? 'block' : 'none';
    document.getElementById('trackdaysPanel').style.display = tab === 'trackdays' ? 'block' : 'none';

    // Load data
    if (tab === 'trackdays') {
        loadTrackdays();
    } else {
        const explicitTrackId = pendingSessionTrackFilter;
        pendingSessionTrackFilter = null;
        loadSessions(explicitTrackId ? parseInt(explicitTrackId, 10) : null);
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

        const sectorCount = td.sector_count || 7;

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
        const track = await apiCall(`/api/tracks/${trackId}`, { displayError: false });
        if (track?.track_scope === 'global' && track?.has_canonical_layout) {
            const layout = await apiCall(`/api/tracks/${trackId}/layout`, { displayError: false });
            mapContainer.innerHTML = generateCanonicalTrackSVG(layout, null, { maxHeight: 420 });
            return;
        }
        const geometry = await apiCall(`/api/tracks/${trackId}/geometry`);
        mapContainer.innerHTML = generateTrackMapSVG(geometry, null, null, { title: '' });
    } catch (e) {
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
        window.currentComparisonSession = session;

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
        saveUiState('ui:archivesView', toggle.checked ? '1' : '');
        loadLearningFiles();
    }
}

async function loadLearningFiles() {
    const container = document.getElementById('learningFilesList');
    const toggle = document.getElementById('showArchivesToggle');
    if (toggle) toggle.checked = readUiState('ui:archivesView', '') === '1';
    isArchivesView = !!toggle?.checked;
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
        updateProcessQueueCount({
            totalFiles: files.length,
            processedFiles: processedList.length,
            archivedView: isArchivesView
        });
        renderFileTable();
    } catch (error) {
        updateProcessQueueCount({
            totalFiles: 0,
            processedFiles: 0,
            archivedView: isArchivesView
        });
        container.innerHTML = renderEmptyState(
            '📁',
            isArchivesView ? 'No archived files found' : 'No files found',
            isArchivesView
                ? 'Archived files will appear here when you move items out of the active queue.'
                : 'Uploaded CSV files will appear here when they are ready to analyze.'
        );
    }
}

function updateProcessQueueCount(summary) {
    processUploadSummary = summary;
    const pill = document.getElementById('processQueueCount');
    const value = document.getElementById('processQueueCountValue');
    if (!pill || !value) return;

    pill.style.display = 'inline-flex';
    pill.classList.toggle('is-archive', !!summary?.archivedView);
    value.textContent = String(summary?.totalFiles ?? 0);
}

function renderFileTable() {
    const container = document.getElementById('learningFilesList');
    const files = window.currentFiles || [];
    const processedFiles = window.processedFiles || new Set();
    const limit = window.sessionLimit;

    if (files.length === 0) {
        container.innerHTML = renderEmptyState(
            '📁',
            isArchivesView ? 'No archived files found' : 'No files found',
            isArchivesView
                ? 'Archived files will appear here when you move them out of the active queue.'
                : 'Your RS-Core uploads will appear here. You can also import a CSV manually if you need to backfill data.'
        );
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
        const processBtn = `<button class="btn small" ${isLimitReached ? 'disabled title="Session limit reached. Upgrade to Pro."' : ''} onclick="processFile('${f.filename}')">${isProcessed ? 'Re-analyze' : 'Analyze'}</button>`;

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
                🚀 Analyze All${unprocessedCount > 0 ? ` (${unprocessedCount})` : ''}
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
            processBtn.textContent = `🚀 Analyze All${unprocessedCount > 0 ? ` (${unprocessedCount})` : ''}`;
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
    const isProcessed = window.processedFiles && window.processedFiles.has(filename);
    let isForce = false;

    if (isProcessed) {
        if (!confirm(`Warning: This session has already been analyzed. Re-analyzing may cause duplicate sessions if the old one is not already deleted.\n\nProceed with processing?`)) {
            return;
        }
        isForce = true;
    }

    showToast('Queuing session...', 'info');
    updateProcessQueueCount({
        totalFiles: window.currentFiles?.length || 0,
        processedFiles: window.processedFiles?.size || 0,
        archivedView: isArchivesView,
        message: `Queued ${filename} for analysis.`
    });

    try {
        const result = await apiCall('/api/process', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: filename, force: isForce })
        });

        if (result && result.status === 'already_processed') {
            showToast(result.message || 'Already analyzed', 'info');
            return;
        }

        if (result && result.job_id) {
            showToast('Analysis processing...', 'info');

            // Poll for completion
            let isComplete = false;
            while (!isComplete) {
                await new Promise(res => setTimeout(res, 2000));
                try {
                    const statusRes = await apiCall(`/api/jobs/${result.job_id}`);
                    if (statusRes.status === 'complete') {
                        isComplete = true;
                        showToast('Session processed successfully!', 'success');
                        updateProcessQueueCount({
                            totalFiles: window.currentFiles?.length || 0,
                            processedFiles: (window.processedFiles?.size || 0) + 1,
                            archivedView: isArchivesView,
                            message: `${filename} finished analyzing successfully.`
                        });
                    } else if (statusRes.status === 'failed') {
                        isComplete = true;
                        showToast('Analysis failed: ' + statusRes.error, 'error');
                        updateProcessQueueCount({
                            totalFiles: window.currentFiles?.length || 0,
                            processedFiles: window.processedFiles?.size || 0,
                            archivedView: isArchivesView,
                            isError: true,
                            message: `${filename} failed to analyze. Please retry.`
                        });
                    }
                } catch (e) {
                    console.error("Polling error", e);
                }
            }
        } else {
            showToast('Session processed!', 'success');
        }

        // Refresh data
        setTimeout(() => {
            loadLearningFiles(); // Refresh to show checkmark
        }, 1000);

    } catch (error) {
        showToast('Analysis failed', 'error');
    }
}

async function processAllFiles() {
    const processedFiles = window.processedFiles || new Set();
    const files = window.currentFiles || [];

    // Check if there's a selection - if so, only process selected unprocessed files
    const selectedCheckboxes = document.querySelectorAll('.file-sel:checked');
    let filesToProcess = [];

    if (selectedCheckboxes.length > 0) {
        // Process only selected non-analyzed files
        filesToProcess = Array.from(selectedCheckboxes)
            .map(cb => cb.value)
            .filter(filename => !processedFiles.has(filename));
    } else {
        // Process all non-analyzed files
        filesToProcess = files
            .map(f => f.filename)
            .filter(filename => !processedFiles.has(filename));
    }

    if (filesToProcess.length === 0) {
        showToast('No unprocessed files to process', 'info');
        return;
    }

    // No confirm() — first-time analysis is non-destructive and confirm() breaks on mobile Safari

    showToast(`Analyzing ${filesToProcess.length} files...`, 'info');

    try {
        const result = await apiCall('/api/process/all', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ files: filesToProcess, force: false })
        });

        if (result.status === 'queued') {
            showToast(`Queued ${result.queued} files for background processing!`, 'info');

            if (result.details && result.details.job_ids) {
                let pendingJobs = [...result.details.job_ids];
                while (pendingJobs.length > 0) {
                    await new Promise(res => setTimeout(res, 3000));

                    for (let i = pendingJobs.length - 1; i >= 0; i--) {
                        try {
                            const statusRes = await apiCall(`/api/jobs/${pendingJobs[i]}`);
                            if (statusRes.status === 'complete' || statusRes.status === 'failed') {
                                pendingJobs.splice(i, 1);
                            }
                        } catch (e) {
                            pendingJobs.splice(i, 1);
                        }
                    }
                    if (pendingJobs.length > 0) {
                        showToast(`Still processing ${pendingJobs.length} files...`, 'info');
                    }
                    loadLearningFiles(); // Load files as they complete
                }
                showToast(`All queued files finished processing!`, 'success');
            }
        } else if (result.skipped > 0 && result.queued === 0) {
            showToast('All files were already processed', 'info');
        }

        if (result.failed > 0) {
            showToast(`${result.failed} file(s) failed to queue`, 'warning');
            console.error('Queue failures:', result.details?.failed);
        }

        // Full refresh at the end
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
            let teleEndpoint = `/api/sessions/${sessionId}/telemetry`;
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

        let canonicalLapMap = null;
        let canonicalLayout = null;
        if (session.track.track_scope === 'global' && session.track.has_canonical_layout) {
            try {
                const layout = await apiCall(`/api/tracks/${session.track.track_id}/layout`, { displayError: false });
                canonicalLayout = layout;
                canonicalLapMap = generateCanonicalTrackSVG(layout, subset, { compact: true, stroke: '#ffffff', strokeWidth: 10, maxHeight: 340 });
            } catch (e) {
                canonicalLapMap = null;
                canonicalLayout = null;
            }
        }

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
                    ${canonicalLapMap || generateColorMapSVG(subset, 'imu', { small: true })}
                    <p class="help-text" style="margin-top:0.5rem; font-size:0.8rem;">${canonicalLapMap ? 'Canonical track package with projected lap line' : 'Accel(Grn) • Brake(Red) • Lat(Glow)'}</p>
                </div>
                
                <!-- Speed Tooltip & Card -->
                <div class="card" onclick="openLapModal('speed')" style="cursor:pointer; transition: transform 0.2s;" 
                     onmouseover="this.style.borderColor='var(--primary)'; this.style.transform='scale(1.01)'" 
                     onmouseout="this.style.borderColor='var(--border)'; this.style.transform='scale(1)'"
                     title="Click to Expand">
                    <h3 style="margin-top:0; font-size:1rem; display:flex; justify-content:space-between;">
                         Speed Map <span style="font-size:0.8em; opacity:0.6">⤢ Expand</span>
                    </h3>
                    ${canonicalLapMap || generateColorMapSVG(subset, 'speed', { small: true })}
                    <p class="help-text" style="margin-top:0.5rem; font-size:0.8rem;">${canonicalLapMap ? 'Shared canonical layout with accurate projected racing line' : 'Fast(Green) • Slow(Red)'}</p>
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
        window._currentLapData = { subset, lap, canonicalLayout };

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
    const { subset, lap, canonicalLayout } = window._currentLapData;

    let html = '';

    if (mode === 'dynamics') {
        html = `
            <div class="card" style="margin-bottom:1rem; border:1px solid var(--primary);">
                <h2 style="text-align:center; margin:0 0 1rem 0;">Rider Dynamics (Full View)</h2>
                ${canonicalLayout ? generateCanonicalTrackSVG(canonicalLayout, subset, { stroke: '#ffffff', strokeWidth: 12, maxHeight: 620 }) : generateColorMapSVG(subset, 'imu', { small: false, sectors: lap.sector_times })}
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
                ${canonicalLayout ? generateCanonicalTrackSVG(canonicalLayout, subset, { stroke: '#ffffff', strokeWidth: 12, maxHeight: 620 }) : generateColorMapSVG(subset, 'speed', { small: false, sectors: lap.sector_times })}
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
        if (data.lap1?.track_scope === 'global' && data.lap1?.track_id && data.lap1.track_id === data.lap2?.track_id) {
            try {
                data.canonicalLayout = await apiCall(`/api/tracks/${data.lap1.track_id}/layout`, { displayError: false });
            } catch (error) {
                data.canonicalLayout = null;
            }
        }

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
                <h3>Telemetry Overlay</h3>
                ${data.canonicalLayout
                    ? generateCanonicalComparisonSVG(data.canonicalLayout, data.lap1.telemetry, data.lap2.telemetry, { maxHeight: 620, strokeWidth: 12 })
                    : `<div style="display: flex; gap: 1rem;">
                        <div style="flex: 1;">
                            ${generateColorMapSVG(sliceTelemetry(data.lap1), 'speed', { small: true })}
                            <p style="text-align: center; font-size: 0.8rem;">Lap 1 Speed Map</p>
                        </div>
                        <div style="flex: 1;">
                            ${generateColorMapSVG(sliceTelemetry(data.lap2), 'speed', { small: true })}
                            <p style="text-align: center; font-size: 0.8rem;">Lap 2 Speed Map</p>
                        </div>
                    </div>`
                }
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
    window.currentComparisonSession = session;

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
        const res = await apiCall(`/api/compare?session1=${sessionId}&lap1=${ref}&session2=${sessionId}&lap2=${target}`);
        if (window.currentComparisonSession?.track?.track_scope === 'global' && window.currentComparisonSession?.track?.has_canonical_layout) {
            try {
                res.canonicalLayout = await apiCall(`/api/tracks/${window.currentComparisonSession.track.track_id}/layout`, { displayError: false });
            } catch (e) {
                res.canonicalLayout = null;
            }
        }
        currentComparisonData = res;

        status.innerText = "";
        results.style.display = "block";

        // Setup Replay
        initReplayMap(res);

        // Draw Chart
        setTimeout(() => {
            drawDeltaChart(res);
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

    if (data.canonicalLayout?.svg_data_url || data.canonicalLayout?.preview_svg_data_url) {
        const layout = data.canonicalLayout;
        const refPoints = projectTelemetryToCanonical(layout, telemetryToSimpleArrays(data.lap1?.telemetry));
        const targetPoints = projectTelemetryToCanonical(layout, telemetryToSimpleArrays(data.lap2?.telemetry));
        const baseSvg = layout.preview_svg_data_url || layout.svg_data_url;
        if (refPoints.length > 1 || targetPoints.length > 1) {
            const refPath = refPoints.length ? `M ${refPoints.map(point => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(' L ')}` : '';
            const targetPath = targetPoints.length ? `M ${targetPoints.map(point => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(' L ')}` : '';
            container.innerHTML = `
                <svg width="100%" height="100%" viewBox="0 0 ${layout.layout_width} ${layout.layout_height}">
                    <image href="${baseSvg}" x="0" y="0" width="${layout.layout_width}" height="${layout.layout_height}" preserveAspectRatio="xMidYMid meet"></image>
                    ${refPath ? `<path d="${refPath}" fill="none" stroke="#4CAF50" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" opacity="0.9"></path>` : ''}
                    ${targetPath ? `<path d="${targetPath}" fill="none" stroke="#F44336" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" opacity="0.9"></path>` : ''}
                    <circle id="ghostRefDot" r="12" fill="#4CAF50" stroke="#fff" stroke-width="2" cx="-10" cy="-10" />
                    <circle id="ghostTargetDot" r="12" fill="#F44336" stroke="#fff" stroke-width="2" cx="-10" cy="-10" />
                </svg>
            `;
            replayState.project = (_, __, index, which = 'ref') => {
                const points = which === 'target' ? targetPoints : refPoints;
                if (!points.length) return [0, 0];
                const point = points[Math.max(0, Math.min(points.length - 1, index || 0))];
                return [point.x, point.y];
            };
            const maxTime = Math.max(data.ref_time[data.ref_time.length - 1], data.target_time[data.target_time.length - 1]);
            replayState.duration = maxTime;
            replayState.currentTime = 0;
            slider.max = maxTime;
            slider.value = 0;
            updateReplayVisuals(0);
            return;
        }
    }

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
    const pRef = replayState.project(data.lat[idxRef], data.lon[idxRef], idxRef, 'ref');
    const pTgt = replayState.project(data.lat[idxTgt], data.lon[idxTgt], idxTgt, 'target');

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
    rawPlaybackPayload: null,
    playbackManifest: null,
    lapCache: {},
    activeLapChunk: null,
    session: null,
    sessionId: null,
    currentIndex: 0,
    startTime: 0,
    duration: 0,
    laps: [],
    selectedLap: 'all',

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
    bounds: null,
    canonicalLayout: null,
    layoutImage: null,
    projectedPoints: null,
    alignedProjectedPoints: null,
    displayProjectedPoints: null,
    renderedLapKey: null,
    pathSource: 'aligned',
    localLagDiagnostics: null,
    tuner: {
        visible: false,
        enabled: false,
        activeTune: null,
        savedTune: null,
        defaultTune: null,
        previewSeq: 0,
        previewTimer: null,
        previewPending: false,
    }
};

function normalizePlaybackData(playbackPayload, fallbackLaps = []) {
    if (['playback_columns', 'playback_manifest', 'playback_lap_chunk'].includes(playbackPayload?.kind) && playbackPayload.columns) {
        const columns = playbackPayload.columns;
        const laps = Array.isArray(playbackPayload?.laps) ? playbackPayload.laps : fallbackLaps;
        const hasSeriesValues = (series) => Array.isArray(series) && series.some(value => value != null && Number.isFinite(Number(value)));
        const alignedLat = hasSeriesValues(columns.aligned_lat) ? columns.aligned_lat : (columns.display_lat || columns.lat || []);
        const alignedLon = hasSeriesValues(columns.aligned_lon) ? columns.aligned_lon : (columns.display_lon || columns.lon || []);
        const alignedSpeed = hasSeriesValues(columns.aligned_speed) ? columns.aligned_speed : (columns.display_speed || columns.speed || []);
        const alignedHeading = hasSeriesValues(columns.aligned_heading_deg) ? columns.aligned_heading_deg : (columns.display_heading_deg || columns.heading_deg || []);
        return {
            ...columns,
            aligned_lat: alignedLat,
            aligned_lon: alignedLon,
            aligned_speed: alignedSpeed,
            aligned_heading_deg: alignedHeading,
            gps_lag_ms_applied: playbackPayload?.meta?.gps_lag_ms_applied ?? playbackPayload?.config?.gpsLagMs ?? 0,
            gps_lean_lag_ms_applied: playbackPayload?.meta?.gps_lean_lag_ms_applied ?? playbackPayload?.meta?.gps_lag_ms_applied ?? playbackPayload?.config?.gpsLagMs ?? 0,
            gps_long_lag_ms_applied: playbackPayload?.meta?.gps_long_lag_ms_applied ?? playbackPayload?.meta?.gps_lag_ms_applied ?? playbackPayload?.config?.gpsLagMs ?? 0,
            gps_lag_source: playbackPayload?.meta?.gps_lag_source ?? 'configured',
            gps_lag_score: playbackPayload?.meta?.gps_lag_score ?? null,
            alignment_confidence: playbackPayload?.meta?.alignment_confidence ?? playbackPayload?.meta?.gps_lag_score ?? null,
            alignment_lean_points: playbackPayload?.meta?.alignment_lean_points ?? null,
            alignment_long_points: playbackPayload?.meta?.alignment_long_points ?? null,
            alignment_frame_points: playbackPayload?.meta?.alignment_frame_points ?? null,
            alignment_frame_laps: playbackPayload?.meta?.alignment_frame_laps ?? null,
            alignment_frame_label: playbackPayload?.meta?.alignment_frame_label ?? null,
            gps_lag_configured_ms: playbackPayload?.meta?.gps_lag_configured_ms ?? playbackPayload?.config?.gpsLagMs ?? 0,
            alignment_mode: playbackPayload?.meta?.alignment_mode ?? playbackPayload?.config?.alignmentMode ?? 'single_lag',
            path_trim_ms: playbackPayload?.meta?.path_trim_ms ?? playbackPayload?.config?.pathTrimMs ?? 0,
            gps_lean_ref_sign: playbackPayload?.meta?.gps_lean_ref_sign ?? 1,
            gps_long_ref_sign: playbackPayload?.meta?.gps_long_ref_sign ?? 1,
            graph_lean_display_sign: playbackPayload?.meta?.graph_lean_display_sign ?? ((playbackPayload?.config?.flipLean ?? false) ? -1 : 1),
            active_tune: playbackPayload?.meta?.active_tune ?? playbackPayload?.config ?? null,
            tune_source: playbackPayload?.meta?.tune_source ?? 'default',
            tuner_feature_enabled: Boolean(playbackPayload?.meta?.tuner_feature_enabled),
            start_index: playbackPayload?.start_index ?? 0,
            end_index: playbackPayload?.end_index ?? (columns.time?.length || 0),
            global_row_count: playbackPayload?.row_count ?? columns.time?.length ?? 0,
            row_index: columns.row_index || columns.time?.map((_, index) => index) || [],
            laps,
            rowCount: columns.time?.length || 0,
        };
    }
    const rows = Array.isArray(playbackPayload?.rows) ? playbackPayload.rows : [];
    const laps = Array.isArray(playbackPayload?.laps) ? playbackPayload.laps : fallbackLaps;
    return {
        time: rows.map(row => row.time),
        lat: rows.map(row => row.lat),
        lon: rows.map(row => row.lon),
        speed: rows.map(row => row.speed_kmh),
        heading_deg: rows.map(row => row.heading_deg),
        lean_deg: rows.map(row => row.lean_deg),
        long_g: rows.map(row => row.long_g),
        lat_g: rows.map(row => row.lat_g),
        accel_g: rows.map(row => row.accel_g),
        brake_g: rows.map(row => row.brake_g),
        display_lat: rows.map(row => row.display_lat ?? row.lat),
        display_lon: rows.map(row => row.display_lon ?? row.lon),
        display_speed: rows.map(row => row.display_speed_kmh ?? row.speed_kmh),
        display_heading_deg: rows.map(row => row.display_heading_deg ?? row.heading_deg),
        aligned_lat: rows.map(row => row.aligned_lat ?? row.display_lat ?? row.lat),
        aligned_lon: rows.map(row => row.aligned_lon ?? row.display_lon ?? row.lon),
        aligned_speed: rows.map(row => row.aligned_speed_kmh ?? row.display_speed_kmh ?? row.speed_kmh),
        aligned_heading_deg: rows.map(row => row.aligned_heading_deg ?? row.display_heading_deg ?? row.heading_deg),
        display_lean_deg: rows.map(row => row.display_lean_deg ?? row.lean_deg),
        display_long_g: rows.map(row => row.display_long_g ?? row.long_g),
        display_lat_g: rows.map(row => row.display_lat_g ?? row.lat_g),
        lap_number: rows.map(row => row.lap_number),
        lap_start: rows.map(row => Boolean(row.lap_start)),
        lap_end: rows.map(row => Boolean(row.lap_end)),
        sector_index: rows.map(row => row.sector_index),
        sector_start: rows.map(row => Boolean(row.sector_start)),
        sector_end: rows.map(row => Boolean(row.sector_end)),
        gps_is_fix: rows.map(row => Boolean(row.gps_is_fix)),
        gps_is_valid: rows.map(row => Boolean(row.gps_is_valid)),
        gps_lean_ref_deg: rows.map(row => row.gps_lean_ref_deg),
        gps_long_ref_g: rows.map(row => row.gps_long_ref_g),
        gps_lag_ms_applied: playbackPayload?.meta?.gps_lag_ms_applied ?? playbackPayload?.config?.gpsLagMs ?? 0,
        gps_lean_lag_ms_applied: playbackPayload?.meta?.gps_lean_lag_ms_applied ?? playbackPayload?.meta?.gps_lag_ms_applied ?? playbackPayload?.config?.gpsLagMs ?? 0,
        gps_long_lag_ms_applied: playbackPayload?.meta?.gps_long_lag_ms_applied ?? playbackPayload?.meta?.gps_lag_ms_applied ?? playbackPayload?.config?.gpsLagMs ?? 0,
        gps_lag_source: playbackPayload?.meta?.gps_lag_source ?? 'configured',
        gps_lag_score: playbackPayload?.meta?.gps_lag_score ?? null,
        alignment_confidence: playbackPayload?.meta?.alignment_confidence ?? playbackPayload?.meta?.gps_lag_score ?? null,
        alignment_lean_points: playbackPayload?.meta?.alignment_lean_points ?? null,
        alignment_long_points: playbackPayload?.meta?.alignment_long_points ?? null,
        alignment_frame_points: playbackPayload?.meta?.alignment_frame_points ?? null,
        alignment_frame_laps: playbackPayload?.meta?.alignment_frame_laps ?? null,
        alignment_frame_label: playbackPayload?.meta?.alignment_frame_label ?? null,
        gps_lag_configured_ms: playbackPayload?.meta?.gps_lag_configured_ms ?? playbackPayload?.config?.gpsLagMs ?? 0,
        alignment_mode: playbackPayload?.meta?.alignment_mode ?? playbackPayload?.config?.alignmentMode ?? 'single_lag',
        path_trim_ms: playbackPayload?.meta?.path_trim_ms ?? playbackPayload?.config?.pathTrimMs ?? 0,
        gps_lean_ref_sign: playbackPayload?.meta?.gps_lean_ref_sign ?? 1,
        gps_long_ref_sign: playbackPayload?.meta?.gps_long_ref_sign ?? 1,
        graph_lean_display_sign: playbackPayload?.meta?.graph_lean_display_sign ?? ((playbackPayload?.config?.flipLean ?? false) ? -1 : 1),
        active_tune: playbackPayload?.meta?.active_tune ?? playbackPayload?.config ?? null,
        tune_source: playbackPayload?.meta?.tune_source ?? 'default',
        tuner_feature_enabled: Boolean(playbackPayload?.meta?.tuner_feature_enabled),
        start_index: playbackPayload?.start_index ?? 0,
        end_index: playbackPayload?.end_index ?? rows.length,
        global_row_count: playbackPayload?.row_count ?? rows.length,
        row_index: rows.map((row, index) => row.row_index ?? index),
        laps,
        rowCount: rows.length,
    };
}

function buildPlaybackFromTelemetry(telemetry, fallbackLaps = []) {
    const count = telemetry?.time?.length || 0;
    const rows = [];
    for (let i = 0; i < count; i += 1) {
        rows.push({
            time: telemetry.time?.[i],
            lat: telemetry.lat?.[i],
            lon: telemetry.lon?.[i],
            speed_kmh: telemetry.speed?.[i],
            heading_deg: null,
            lean_deg: telemetry.lean_angle?.[i] ?? null,
            long_g: telemetry.ax?.[i] ?? telemetry.raw_ax?.[i] ?? null,
            lat_g: telemetry.ay?.[i] ?? telemetry.raw_ay?.[i] ?? null,
            accel_g: telemetry.ax?.[i] != null ? Math.max(Number(telemetry.ax[i]), 0) : null,
            brake_g: telemetry.ax?.[i] != null ? Math.abs(Math.min(Number(telemetry.ax[i]), 0)) : null,
            display_lat: telemetry.lat?.[i],
            display_lon: telemetry.lon?.[i],
            display_speed_kmh: telemetry.speed?.[i],
            display_heading_deg: null,
            aligned_lat: telemetry.lat?.[i],
            aligned_lon: telemetry.lon?.[i],
            aligned_speed_kmh: telemetry.speed?.[i],
            aligned_heading_deg: null,
            display_lean_deg: telemetry.lean_angle?.[i] ?? null,
            display_long_g: telemetry.ax?.[i] ?? telemetry.raw_ax?.[i] ?? null,
            display_lat_g: telemetry.ay?.[i] ?? telemetry.raw_ay?.[i] ?? null,
            lap_number: null,
            lap_start: false,
            lap_end: false,
            sector_index: null,
            sector_start: false,
            sector_end: false,
            gps_is_fix: telemetry.gps_is_fix?.[i] ?? true,
            gps_is_valid: telemetry.gps_is_valid?.[i] ?? true,
        });
    }
    return { meta: { gps_lag_ms_applied: 0 }, laps: fallbackLaps, rows };
}

function loadImageAsset(src) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = reject;
        img.src = src;
    });
}

async function openPlayback(sessionId, shareToken = null) {
    const modal = document.getElementById('playbackModal');

    // 1. Reset State
    pbState = {
        ...pbState,
        active: true,
        playing: false,
        currentIndex: 0,
        mapMode: 'speed',
        pathSource: 'aligned',
        selectedLap: 'all',
        rawPlaybackPayload: null,
        playbackManifest: null,
        lapCache: {},
        activeLapChunk: null,
        sessionId,
        canonicalLayout: null,
        layoutImage: null,
        projectedPoints: null,
        alignedProjectedPoints: null,
        displayProjectedPoints: null,
        renderedLapKey: null,
        localLagDiagnostics: null,
        tuner: {
            visible: false,
            enabled: false,
            activeTune: null,
            savedTune: null,
            defaultTune: null,
            previewSeq: 0,
            previewTimer: null,
            previewPending: false,
        }
    };

    // 2. Show Modal (Loading)
    modal.classList.add('active');
    document.getElementById('pbPlayPause').textContent = '...';

    try {
        // 3. Fetch Data
        let endpoint = `/api/sessions/${sessionId}`;
        let playbackEndpoint = `/api/sessions/${sessionId}/playback/manifest`;

        if (shareToken) {
            endpoint = `/api/shared/${shareToken}`;
            playbackEndpoint = `/api/shared/${shareToken}/playback`;
        }

        const sessionPromise = apiCall(endpoint);
        const playbackPromise = apiCall(playbackEndpoint, { displayError: false });
        const session = await sessionPromise;
        let playback = null;
        try {
            playback = await playbackPromise;
        } catch (playbackError) {
            let telemetryEndpoint = `/api/sessions/${sessionId}/telemetry`;
            if (shareToken) {
                telemetryEndpoint = `/api/shared/${shareToken}/telemetry`;
            }
            const telemetry = await apiCall(telemetryEndpoint);
            playback = buildPlaybackFromTelemetry(telemetry, session.laps || []);
        }

        pbState.session = session;
        pbState.rawPlaybackPayload = playback;
        pbState.playbackManifest = playback?.kind === 'playback_manifest' ? playback : null;
        pbState.data = normalizePlaybackData(playback, session.laps || []);
        pbState.laps = pbState.data.laps || session.laps || [];

        if (pbState.data.time && pbState.data.time.length > 0) {
            pbState.duration = pbState.data.time[pbState.data.time.length - 1] - pbState.data.time[0];
            pbState.startTime = pbState.data.time[0];
        } else {
            throw new Error("Playback data empty or format invalid");
        }

        // 4. Init UI
        initPlaybackUI();
        renderPlaybackTunerPanel();

        // 5. Draw immediately from display GPS. Layout/tuner metadata loads after first paint.
        fitTrackMap();
        if (playbackResizeHandler) {
            window.removeEventListener('resize', playbackResizeHandler);
        }
        playbackResizeHandler = () => {
            if (!pbState.active) return;
            fitTrackMap();
            drawFrame();
        };
        window.addEventListener('resize', playbackResizeHandler);

        // 6. Ready
        togglePlayback(true);
        loadPlaybackSideData(session, sessionId, shareToken);

    } catch (e) {
        console.error(e);
        closePlaybackModal();
        showToast("Playback Unavailable: " + e.message, "error");
    }
}

async function loadPlaybackSideData(session, sessionId, shareToken = null) {
    loadAnnotations(sessionId);
    if (!shareToken) {
        loadPlaybackTunerState();
    }
    setTimeout(() => {
        loadPlaybackCanonicalLayout(session);
    }, 0);
}

async function loadPlaybackTunerState() {
    try {
        const tunerState = await apiCall('/api/admin/playback-tuner', { displayError: false });
        if (!pbState.active) return;
        pbState.tuner.visible = true;
        pbState.tuner.enabled = Boolean(tunerState?.enabled);
        pbState.tuner.defaultTune = tunerState?.default_tune || null;
        pbState.tuner.savedTune = tunerState?.active_tune || tunerState?.default_tune || null;
        pbState.tuner.activeTune = tunerState?.active_tune || tunerState?.default_tune || null;
        renderPlaybackTunerPanel();
        if (pbState.tuner.enabled) {
            schedulePlaybackTunerPreview();
        }
    } catch (error) {
        if (!pbState.active) return;
        pbState.tuner.visible = Boolean(currentUser?.is_admin);
        pbState.tuner.defaultTune = playbackDefaultTunerTune();
        pbState.tuner.savedTune = playbackDefaultTunerTune();
        pbState.tuner.activeTune = playbackDefaultTunerTune();
        renderPlaybackTunerPanel();
    }
}

async function loadPlaybackCanonicalLayout(session) {
    if (!pbState.active || !(session.track?.track_scope === 'global' && session.track?.has_canonical_layout)) return;
    try {
        const layout = await apiCall(`/api/tracks/${session.track.track_id}/layout`, { displayError: false });
        if (!pbState.active) return;
        const baseSvg = layout?.preview_svg_data_url || layout?.svg_data_url;
        const image = baseSvg ? await loadImageAsset(baseSvg) : null;
        if (!pbState.active) return;
        if (!pbState.active) return;
        pbState.canonicalLayout = layout;
        pbState.layoutImage = image;
        refreshPlaybackProjectedPoints();
        fitTrackMap();
        drawFrame();
    } catch (error) {
        pbState.canonicalLayout = null;
        pbState.layoutImage = null;
        pbState.projectedPoints = null;
        pbState.displayProjectedPoints = null;
    }
}

async function loadPlaybackLapChunk(lapNumber) {
    if (!pbState.sessionId || !lapNumber || lapNumber === 'all') return null;
    const key = String(lapNumber);
    if (pbState.lapCache?.[key]) {
        return pbState.lapCache[key];
    }
    const payload = await apiCall(`/api/sessions/${pbState.sessionId}/playback/laps/${encodeURIComponent(key)}`, { displayError: false });
    const data = normalizePlaybackData(payload, pbState.session?.laps || []);
    pbState.lapCache[key] = { payload, data };
    return pbState.lapCache[key];
}

function activatePlaybackData(data, selectedLap) {
    pbState.data = data;
    pbState.selectedLap = selectedLap == null ? 'all' : String(selectedLap);
    pbState.activeLapChunk = pbState.selectedLap === 'all' ? null : data;
    pbState.pathCache = null;
    pbState.renderedLapKey = null;
    pbState.localLagDiagnostics = null;
    if (data?.time?.length) {
        pbState.startTime = data.time[0];
        pbState.duration = data.time[data.time.length - 1] - data.time[0];
        pbState.currentIndex = 0;
        pbState.playbackTime = data.time[0];
    }
    const slider = document.getElementById('pbSeek');
    if (slider && data?.time) {
        slider.max = Math.max(0, data.time.length - 1);
        slider.value = 0;
    }
    const sel = document.getElementById('pbLapSelect');
    if (sel) sel.value = pbState.selectedLap;
    refreshPlaybackProjectedPoints();
    fitTrackMap();
    drawFrame();
}

function closePlaybackModal() {
    pbState.active = false;
    pbState.playing = false;
    if (pbState.tuner?.previewTimer) {
        clearTimeout(pbState.tuner.previewTimer);
        pbState.tuner.previewTimer = null;
    }
    if (playbackResizeHandler) {
        window.removeEventListener('resize', playbackResizeHandler);
        playbackResizeHandler = null;
    }
    document.getElementById('playbackModal').classList.remove('active');
    closePlaybackTimingModal();
    closePlaybackGraphModal();
}

function playbackTunerFieldDefs() {
    return [
        { key: 'gyroScale', label: 'Gyro Scale', kind: 'range', step: 0.001, min: 0, max: 0.12, unit: 'x', decimals: 3 },
        { key: 'leanGaussianSigma', label: 'Lean Gaussian', kind: 'range', step: 0.25, min: 0, max: 20, unit: 'sigma', decimals: 2 },
        { key: 'longGaussianSigma', label: 'Long Gaussian', kind: 'range', step: 0.25, min: 0, max: 20, unit: 'sigma', decimals: 2 },
        { key: 'pathTrimMs', label: 'Path Lag Trim', kind: 'range', step: 25, min: -3000, max: 3000, unit: 'ms', decimals: 0 },
        { key: 'flipLean', label: 'Flip Lean', kind: 'toggle' },
        { key: 'flipForce', label: 'Flip Force', kind: 'toggle' },
        { key: 'autoAlignEnabled', label: 'Auto Align', kind: 'toggle' },
    ];
}

function playbackTunerPayload(tune) {
    const source = tune || {};
    const payload = {};
    playbackTunerFieldDefs().forEach((field) => {
        if (source[field.key] === undefined) return;
        payload[field.key] = source[field.key];
    });
    return payload;
}

function playbackDefaultTunerTune() {
    return {
        gyroScale: 0.04,
        leanGaussianSigma: 0,
        longGaussianSigma: 0,
        pathTrimMs: 0,
        flipLean: false,
        flipForce: false,
        autoAlignEnabled: true,
    };
}

function renderPlaybackAlignmentModeControl() {
    const wrap = document.getElementById('playbackAlignmentModeCard');
    const select = document.getElementById('playbackAlignmentModeSelect');
    const trimWrap = document.getElementById('playbackPathTrimCard');
    const trimSlider = document.getElementById('playbackPathTrimSlider');
    const trimValue = document.getElementById('playbackPathTrimValue');
    if (!wrap || !select || !trimWrap || !trimSlider || !trimValue) return;
    wrap.style.display = 'none';
    trimWrap.style.display = 'none';
}

function renderPlaybackTunerPanel() {
    const card = document.getElementById('playbackGraphTunerPanel');
    const fields = document.getElementById('playbackTunerFields');
    const status = document.getElementById('playbackTunerStatus');
    if (!card || !status || !fields) return;
    if (!pbState.tuner?.visible) {
        card.style.display = 'none';
        return;
    }
    card.style.display = 'flex';
    renderPlaybackAlignmentModeControl();
    const tune = pbState.tuner.activeTune || pbState.tuner.savedTune || pbState.tuner.defaultTune || {};
    fields.innerHTML = playbackTunerFieldDefs().map((field) => {
        const value = tune[field.key] ?? '';
        if (field.kind === 'select') {
            return `
                <label class="form-group" style="margin-bottom:12px; display:block;">
                    <span class="help-text" style="display:block; margin-bottom:6px;">${field.label}</span>
                    <select class="filter-select" style="width:100%;" onchange="updatePlaybackTunerField('${field.key}', this.value)">
                        ${field.options.map((option) => `<option value="${option.value}" ${String(value) === String(option.value) ? 'selected' : ''}>${option.label}</option>`).join('')}
                    </select>
                </label>
            `;
        }
        if (field.kind === 'toggle') {
            return `
                <label class="form-group" style="margin-bottom:12px; display:flex; align-items:center; justify-content:space-between; gap:12px;">
                    <span class="help-text">${field.label}</span>
                    <input
                        type="checkbox"
                        ${value ? 'checked' : ''}
                        onchange="updatePlaybackTunerField('${field.key}', this.checked)"
                    />
                </label>
            `;
        }
        return `
            <label class="form-group" style="margin-bottom:14px; display:block;">
                <div style="display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:6px;">
                    <span class="help-text">${field.label}</span>
                    <strong id="playbackTunerValue_${field.key}" style="font-size:0.82rem; color:#f5f5f5;">${playbackTunerFormatValue(field, value)}</strong>
                </div>
                <input
                    type="range"
                    min="${field.min}"
                    max="${field.max}"
                    step="${field.step}"
                    value="${value}"
                    style="width:100%; accent-color: var(--primary);"
                    onchange="updatePlaybackTunerField('${field.key}', this.value)"
                    oninput="updatePlaybackTunerField('${field.key}', this.value, true)"
                />
            </label>
        `;
    }).join('');
    updatePlaybackTunerStatus();
}

function updatePlaybackTunerStatus() {
    const status = document.getElementById('playbackTunerStatus');
    if (!status) return;
    if (pbState.tuner?.previewPending) {
        status.textContent = 'Previewing...';
    } else if (pbState.tuner?.previewError) {
        status.textContent = 'Preview failed';
    } else if (!pbState.tuner?.enabled) {
        status.textContent = 'Admin preview only';
    } else {
        status.textContent = `Live preview ${pbState.data?.tune_source || 'default'}`;
    }
    renderPlaybackAlignmentModeControl();
}

function playbackTunerFormatValue(field, value) {
    if (field.kind === 'toggle') {
        return value ? 'On' : 'Off';
    }
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '--';
    const decimals = Number(field.decimals ?? 0);
    const formatted = numeric.toFixed(decimals);
    return field.unit ? `${formatted} ${field.unit}` : formatted;
}

function updatePlaybackTunerField(key, rawValue, liveOnly = false) {
    if (!pbState.tuner?.visible) return;
    const defs = playbackTunerFieldDefs();
    const field = defs.find(item => item.key === key);
    if (!field) return;
    let value = rawValue;
    if (field.kind === 'toggle') {
        value = Boolean(rawValue);
    } else if (field.kind !== 'select' || rawValue === '-1' || rawValue === '1') {
        const numeric = Number(rawValue);
        if (!Number.isFinite(numeric)) return;
        value = field.step === 1 ? Math.round(numeric) : numeric;
    }
    pbState.tuner.activeTune = {
        ...(pbState.tuner.activeTune || pbState.tuner.savedTune || pbState.tuner.defaultTune || {}),
        [key]: value,
    };
    if (field.kind === 'range') {
        const label = document.getElementById(`playbackTunerValue_${key}`);
        if (label) label.textContent = playbackTunerFormatValue(field, value);
    } else if (!liveOnly) {
        renderPlaybackTunerPanel();
    }
    schedulePlaybackTunerPreview();
}

function schedulePlaybackTunerPreview() {
    if (!pbState.sessionId || !pbState.tuner?.visible) return;
    if (pbState.tuner.previewTimer) clearTimeout(pbState.tuner.previewTimer);
    pbState.tuner.previewPending = true;
    pbState.tuner.previewError = false;
    updatePlaybackTunerStatus();
    pbState.tuner.previewTimer = setTimeout(() => {
        runPlaybackTunerPreview();
    }, 80);
}

async function runPlaybackTunerPreview() {
    if (!pbState.sessionId || !pbState.tuner?.visible) return;
    const seq = (pbState.tuner.previewSeq || 0) + 1;
    pbState.tuner.previewSeq = seq;
    const tune = playbackTunerPayload(pbState.tuner.activeTune || pbState.tuner.savedTune || pbState.tuner.defaultTune || {});
    const bounds = playbackPreviewPatchBounds();
    try {
        const payload = await apiCall('/api/admin/playback-tuner/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: pbState.sessionId,
                tune,
                start_index: bounds.startIndex,
                end_index: bounds.endIndex,
            }),
            displayError: false,
        });
        if (seq !== pbState.tuner.previewSeq || !payload) return;
        if (payload.kind === 'playback_tune_patch') {
            applyPlaybackTunePatch(payload);
        } else {
            pbState.data = normalizePlaybackData(payload, pbState.session.laps || []);
            pbState.laps = pbState.data.laps || pbState.session.laps || [];
            pbState.duration = pbState.data.time[pbState.data.time.length - 1] - pbState.data.time[0];
        }
        pbState.tuner.previewPending = false;
        pbState.tuner.previewError = false;
        updatePlaybackTunerStatus();
        if (document.getElementById('playbackGraphModal')?.classList.contains('active')) {
            updatePlaybackGraphMeta();
        }
        drawFrame();
        if (document.getElementById('playbackGraphModal')?.classList.contains('active')) {
            drawPlaybackComparisonGraph();
        }
    } catch (error) {
        if (seq !== pbState.tuner.previewSeq) return;
        pbState.tuner.previewPending = false;
        pbState.tuner.previewError = true;
        updatePlaybackTunerStatus();
    }
}

function playbackPreviewPatchBounds() {
    const data = pbState.data;
    if (!data?.time?.length) return { startIndex: 0, endIndex: 0 };
    if (pbState.selectedLap && pbState.selectedLap !== 'all') {
        const start = Number(data.start_index || 0);
        const end = Number(data.end_index || (start + data.time.length));
        return { startIndex: start, endIndex: end };
    }
    const rowLapNumber = data.lap_number?.[pbState.currentIndex];
    const activeLap = rowLapNumber ? playbackLapByNumber(rowLapNumber) : playbackLapForTime(data.time[pbState.currentIndex]);
    if (activeLap) {
        const range = pbState.playbackManifest?.lap_ranges?.find(item => Number(item.lap_number) === Number(activeLap.lap_number));
        if (range) return { startIndex: range.start_index, endIndex: range.end_index };
    }
    const start = Number(data.start_index || 0);
    const end = Number(data.end_index || (start + data.time.length));
    return { startIndex: start, endIndex: end };
}

function applyPlaybackTunePatch(payload) {
    const dataStart = Number(pbState.data?.start_index || 0);
    const start = Math.max(0, Number(payload.start_index || 0) - dataStart);
    const columns = payload.columns || {};
    Object.entries(columns).forEach(([key, values]) => {
        if (!Array.isArray(values)) return;
        if (!Array.isArray(pbState.data[key])) return;
        for (let offset = 0; offset < values.length; offset += 1) {
            const target = start + offset;
            if (target >= 0 && target < pbState.data[key].length) {
                pbState.data[key][target] = values[offset];
            }
        }
    });
    const meta = payload.meta || {};
    pbState.data.gps_lag_ms_applied = meta.gps_lag_ms_applied ?? pbState.data.gps_lag_ms_applied;
    pbState.data.gps_lean_lag_ms_applied = meta.gps_lean_lag_ms_applied ?? pbState.data.gps_lean_lag_ms_applied;
    pbState.data.gps_long_lag_ms_applied = meta.gps_long_lag_ms_applied ?? pbState.data.gps_long_lag_ms_applied;
    pbState.data.gps_lag_source = meta.gps_lag_source ?? pbState.data.gps_lag_source;
    pbState.data.gps_lag_score = meta.gps_lag_score ?? pbState.data.gps_lag_score;
    pbState.data.alignment_confidence = meta.alignment_confidence ?? pbState.data.alignment_confidence;
    pbState.data.alignment_lean_points = meta.alignment_lean_points ?? pbState.data.alignment_lean_points;
    pbState.data.alignment_long_points = meta.alignment_long_points ?? pbState.data.alignment_long_points;
    pbState.data.alignment_frame_points = meta.alignment_frame_points ?? pbState.data.alignment_frame_points;
    pbState.data.alignment_frame_laps = meta.alignment_frame_laps ?? pbState.data.alignment_frame_laps;
    pbState.data.alignment_frame_label = meta.alignment_frame_label ?? pbState.data.alignment_frame_label;
    pbState.data.gps_lag_configured_ms = meta.gps_lag_configured_ms ?? pbState.data.gps_lag_configured_ms;
    pbState.data.alignment_mode = meta.alignment_mode ?? pbState.data.alignment_mode;
    pbState.data.path_trim_ms = meta.path_trim_ms ?? pbState.data.path_trim_ms;
    pbState.data.gps_lean_ref_sign = meta.gps_lean_ref_sign ?? pbState.data.gps_lean_ref_sign;
    pbState.data.gps_long_ref_sign = meta.gps_long_ref_sign ?? pbState.data.gps_long_ref_sign;
    pbState.data.graph_lean_display_sign = meta.graph_lean_display_sign ?? pbState.data.graph_lean_display_sign;
    pbState.data.active_tune = meta.active_tune ?? payload.config ?? pbState.data.active_tune;
    pbState.data.tune_source = meta.tune_source ?? 'preview';
    pbState.data.tuner_feature_enabled = Boolean(meta.tuner_feature_enabled);
    refreshPlaybackProjectedPoints();
    pbState.pathCache = null;
    pbState.renderedLapKey = null;
}

async function savePlaybackTuner() {
    if (!pbState.tuner?.visible) return;
    const tune = playbackTunerPayload(pbState.tuner.activeTune || pbState.tuner.savedTune || pbState.tuner.defaultTune || {});
    try {
        const response = await apiCall('/api/admin/playback-tuner', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: true, active_tune: tune }),
            displayError: false,
        });
        pbState.tuner.enabled = Boolean(response?.enabled);
        pbState.tuner.savedTune = response?.active_tune || tune;
        pbState.tuner.activeTune = response?.active_tune || tune;
        pbState.tuner.defaultTune = response?.default_tune || pbState.tuner.defaultTune;
        renderPlaybackTunerPanel();
        showToast('Playback tune saved', 'success');
    } catch (error) {
        showToast(error?.message || 'Failed to save playback tune', 'error');
    }
}

function resetPlaybackTuner() {
    if (!pbState.tuner?.visible) return;
    pbState.tuner.activeTune = { ...(pbState.tuner.savedTune || pbState.tuner.defaultTune || {}) };
    renderPlaybackTunerPanel();
    schedulePlaybackTunerPreview();
}

function refreshPlaybackProjectedPoints() {
    if (!pbState.canonicalLayout || !pbState.data) {
        pbState.projectedPoints = null;
        pbState.alignedProjectedPoints = null;
        pbState.displayProjectedPoints = null;
        return;
    }
    pbState.projectedPoints = projectTelemetryToCanonical(pbState.canonicalLayout, {
        lats: pbState.data.lat || [],
        lons: pbState.data.lon || []
    });
    pbState.alignedProjectedPoints = projectTelemetryToCanonical(pbState.canonicalLayout, {
        lats: pbState.data.aligned_lat || pbState.data.display_lat || pbState.data.lat || [],
        lons: pbState.data.aligned_lon || pbState.data.display_lon || pbState.data.lon || []
    });
    pbState.displayProjectedPoints = projectTelemetryToCanonical(pbState.canonicalLayout, {
        lats: pbState.data.display_lat || pbState.data.lat || [],
        lons: pbState.data.display_lon || pbState.data.lon || []
    });
}

function playbackSelectedPathSeries() {
    const data = pbState.data || {};
    if (pbState.pathSource === 'rawfix') {
        return {
            key: 'rawfix',
            label: 'Raw GPS fixes',
            lats: data.lat || [],
            lons: data.lon || [],
            speeds: data.speed || [],
            projected: pbState.projectedPoints,
            fixOnly: true,
        };
    }
    if (pbState.pathSource === 'display') {
        return {
            key: 'display',
            label: 'Display path',
            lats: data.display_lat || data.aligned_lat || data.lat || [],
            lons: data.display_lon || data.aligned_lon || data.lon || [],
            speeds: data.display_speed || data.aligned_speed || data.speed || [],
            projected: pbState.displayProjectedPoints || pbState.alignedProjectedPoints || pbState.projectedPoints,
            fixOnly: false,
        };
    }
    return {
        key: 'aligned',
        label: 'Aligned GPS on IMU',
        lats: data.aligned_lat || data.display_lat || data.lat || [],
        lons: data.aligned_lon || data.display_lon || data.lon || [],
        speeds: data.aligned_speed || data.display_speed || data.speed || [],
        projected: pbState.alignedProjectedPoints || pbState.displayProjectedPoints || pbState.projectedPoints,
        fixOnly: false,
    };
}

function updatePlaybackGraphMeta() {
    const meta = document.getElementById('playbackGraphMeta');
    if (!meta || !pbState.data) return;
    const lagMs = pbState.data.gps_lag_ms_applied ?? 0;
    const lagSource = pbState.data.gps_lag_source || 'configured';
    const score = pbState.data.alignment_confidence == null ? '' : `, score ${Number(pbState.data.alignment_confidence).toFixed(3)}`;
    const mode = pbState.data.alignment_mode || 'single_lag';
    const pathTrimMs = pbState.data.path_trim_ms ?? pbState.data.active_tune?.pathTrimMs ?? 0;
    const scope = pbState.selectedLap && pbState.selectedLap !== 'all' ? `Lap ${pbState.selectedLap}` : 'Session';
    const leanPoints = pbState.data.alignment_lean_points ?? 0;
    const longPoints = pbState.data.alignment_long_points ?? 0;
    const framePoints = pbState.data.alignment_frame_points ?? 0;
    const frameLabel = pbState.data.alignment_frame_label || 'window';
    const trimText = pathTrimMs ? `, path trim ${pathTrimMs} ms` : '';
    const drift = getPlaybackLocalLagDiagnostics(playbackGraphRows());
    const driftText = drift?.segments?.length
        ? ` Local lag ${Math.round(drift.minLagMs)}..${Math.round(drift.maxLagMs)} ms across ${drift.segments.length} windows.`
        : '';
    meta.textContent = `${scope} comparison. GPS alignment ${lagMs} ms${trimText} (${mode}, ${lagSource}${score}). Window ${frameLabel}, ${framePoints} samples. Correlation samples: lean ${leanPoints}, long ${longPoints}.${driftText}`;
}

function showPlaybackTimingModal() {
    const modal = document.getElementById('playbackTimingModal');
    const body = document.getElementById('playbackTimingBody');
    if (!modal || !body) return;
    const laps = pbState.laps || [];
    const officialLaps = pbState.session?.laps || [];
    const sectorCount = Math.max(
        ...[0, ...laps.map(lap => (lap.sector_times || []).length), ...officialLaps.map(lap => (lap.sector_times || []).length)]
    );
    if (!laps.length) {
        body.innerHTML = '<div class="help-text">No enriched playback timing available for this session.</div>';
        modal.classList.add('active');
        return;
    }

    const officialByLap = new Map(officialLaps.map(lap => [lap.lap_number, lap]));
    body.innerHTML = `
        <div class="playback-timing-table-wrap">
            <table class="modern-table playback-timing-table">
                <thead>
                    <tr>
                        <th>Lap</th>
                        <th>Enriched</th>
                        <th>Delta vs GPS</th>
                        ${Array.from({ length: sectorCount }, (_, index) => `<th style="text-align:center;">S${index + 1}</th>`).join('')}
                    </tr>
                </thead>
                <tbody>
                    ${laps.map(lap => {
                        const official = officialByLap.get(lap.lap_number);
                        const delta = lap.delta_to_gps_only ?? (official?.lap_time != null ? lap.lap_time - official.lap_time : null);
                        const deltaClass = delta == null ? '' : (delta > 0 ? 'slower' : 'faster');
                        const isBest = lap.is_session_best;
                        return `
                            <tr class="lap-row ${isBest ? 'best-lap' : ''}">
                                <td class="lap-number">${lap.lap_number}</td>
                                <td class="lap-time">${formatTime(lap.lap_time)}</td>
                                <td class="lap-delta ${deltaClass}">${delta == null ? '--' : `${delta > 0 ? '+' : ''}${delta.toFixed(3)}`}</td>
                                ${Array.from({ length: sectorCount }, (_, index) => {
                                    const value = lap.sector_times?.[index];
                                    return `<td style="text-align:center;">${value == null ? '--' : formatTime(value)}</td>`;
                                }).join('')}
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
        </div>
    `;
    modal.classList.add('active');
}

function closePlaybackTimingModal() {
    const modal = document.getElementById('playbackTimingModal');
    if (modal) modal.classList.remove('active');
}

async function showPlaybackGraphModal() {
    if (pbState.selectedLap === 'all') {
        const currentTime = pbState.data?.time?.[Math.floor(pbState.currentIndex || 0)];
        const lap = currentTime != null ? playbackLapForTime(currentTime) : (pbState.laps?.[0] || null);
        if (lap?.lap_number) {
            await jumpToLap(String(lap.lap_number));
        }
    }
    const modal = document.getElementById('playbackGraphModal');
    const canvas = document.getElementById('playbackGraphCanvas');
    if (!modal || !canvas || !pbState.data) return;
    updatePlaybackGraphMeta();
    modal.classList.add('active');
    renderPlaybackTunerPanel();
    drawPlaybackComparisonGraph();
    canvas.onclick = (event) => seekPlaybackFromGraphClick(event);
}

function closePlaybackGraphModal() {
    const modal = document.getElementById('playbackGraphModal');
    if (modal) modal.classList.remove('active');
}

function playbackGraphRows() {
    const data = pbState.data;
    if (!data?.time?.length) return [];
    const { startIndex, endIndex } = currentPlaybackLapBounds();
    const rows = [];
    for (let index = startIndex; index < endIndex; index += 1) {
        rows.push({
            index,
            time: data.time[index],
            imuLean: finiteOrNull(data.display_lean_deg?.[index] ?? data.lean_deg?.[index]),
            gpsLean: finiteOrNull(data.gps_lean_ref_deg?.[index]),
            imuLong: finiteOrNull(data.display_long_g?.[index] ?? data.long_g?.[index]),
            gpsLong: finiteOrNull(data.gps_long_ref_g?.[index]),
        });
    }
    return rows;
}

function playbackLeanGraphValue(value) {
    const number = finiteOrNull(value);
    if (number == null) return null;
    return number;
}

function finiteOrNull(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
}

function drawPlaybackComparisonGraph() {
    const canvas = document.getElementById('playbackGraphCanvas');
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(640, Math.round(rect.width * dpr));
    canvas.height = Math.max(420, Math.round(rect.height * dpr));
    const ctx = canvas.getContext('2d');
    const rows = playbackGraphRows();
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!rows.length) {
        ctx.fillStyle = 'rgba(255,255,255,0.7)';
        ctx.font = `${16 * dpr}px sans-serif`;
        ctx.fillText('No playback graph data available.', 28 * dpr, 48 * dpr);
        return;
    }
    const diagnostics = getPlaybackLocalLagDiagnostics(rows);
    const panelCount = diagnostics?.segments?.length ? 3 : 2;
    const margin = 26 * dpr;
    const gap = 22 * dpr;
    const graphH = (canvas.height - margin * 2 - gap * (panelCount - 1)) / panelCount;
    const graphW = canvas.width - margin * 2;
    drawPlaybackSeriesGraph(ctx, rows, {
        x: margin,
        y: margin,
        w: graphW,
        h: graphH,
        title: 'Lean: IMU attitude vs GPS curvature',
        imuKey: 'imuLean',
        gpsKey: 'gpsLean',
        valueTransform: playbackLeanGraphValue,
        unit: 'deg',
        minScale: 20,
        positiveLabel: 'right',
        negativeLabel: 'left',
    }, dpr);
    drawPlaybackSeriesGraph(ctx, rows, {
        x: margin,
        y: margin + graphH + gap,
        w: graphW,
        h: graphH,
        title: 'Longitudinal force: acceleration up, braking down',
        imuKey: 'imuLong',
        gpsKey: 'gpsLong',
        unit: 'g',
        minScale: 0.35,
        positiveLabel: 'accel',
        negativeLabel: 'brake',
    }, dpr);
    if (panelCount === 3) {
        drawPlaybackLocalLagGraph(ctx, rows, diagnostics, {
            x: margin,
            y: margin + (graphH + gap) * 2,
            w: graphW,
            h: graphH,
            title: 'Local lag drift: best longitudinal lag by window',
        }, dpr);
    }
}

function drawInlinePlaybackLeanGraph() {
    const canvas = document.getElementById('pbLeanInlineCanvas');
    if (!canvas || !pbState.data?.time?.length) return;
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(480, Math.round(rect.width * dpr));
    canvas.height = Math.max(140, Math.round(rect.height * dpr));
    const ctx = canvas.getContext('2d');
    const rows = playbackGraphRows();
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (!rows.length) {
        ctx.fillStyle = 'rgba(255,255,255,0.65)';
        ctx.font = `${12 * dpr}px sans-serif`;
        ctx.fillText('No lean graph data available.', 18 * dpr, 26 * dpr);
        return;
    }
    const padX = 18 * dpr;
    const padTop = 18 * dpr;
    const padBottom = 20 * dpr;
    const left = padX;
    const right = canvas.width - padX;
    const top = padTop;
    const bottom = canvas.height - padBottom;
    const plotW = Math.max(1, right - left);
    const plotH = Math.max(1, bottom - top);
    const values = rows.flatMap((row) => [playbackLeanGraphValue(row.imuLean), playbackLeanGraphValue(row.gpsLean)]).filter(Number.isFinite);
    const maxValue = Math.max(20, ...values.map((value) => Math.abs(value)));
    const xFor = (offset) => left + (offset / Math.max(1, rows.length - 1)) * plotW;
    const yFor = (value) => top + ((maxValue - value) / (maxValue * 2)) * plotH;

    ctx.fillStyle = 'rgba(12,12,12,0.92)';
    fillRoundedRect(ctx, 0, 0, canvas.width, canvas.height, 16 * dpr);
    ctx.strokeStyle = 'rgba(255,255,255,0.10)';
    ctx.lineWidth = 1 * dpr;
    ctx.strokeRect(0, 0, canvas.width, canvas.height);

    ctx.strokeStyle = 'rgba(255,255,255,0.10)';
    [-0.5, 0, 0.5].forEach((mark) => {
        const y = yFor(maxValue * mark);
        ctx.beginPath();
        ctx.moveTo(left, y);
        ctx.lineTo(right, y);
        ctx.stroke();
    });

    drawPlaybackGraphLine(ctx, rows, 'gpsLean', xFor, yFor, '#4da3ff', 2.0 * dpr, playbackLeanGraphValue);
    drawPlaybackGraphLine(ctx, rows, 'imuLean', xFor, yFor, '#ff6b3a', 1.8 * dpr, playbackLeanGraphValue);

    const markerIndex = Math.max(0, rows.findIndex((row) => row.index >= pbState.currentIndex));
    const markerX = xFor(markerIndex === -1 ? rows.length - 1 : markerIndex);
    ctx.strokeStyle = 'rgba(255,255,255,0.45)';
    ctx.beginPath();
    ctx.moveTo(markerX, top);
    ctx.lineTo(markerX, bottom);
    ctx.stroke();

    ctx.fillStyle = 'rgba(255,255,255,0.72)';
    ctx.font = `${11 * dpr}px sans-serif`;
    ctx.fillText('GPS', left + 2 * dpr, 13 * dpr);
    ctx.fillStyle = '#4da3ff';
    ctx.fillRect(left + 28 * dpr, 5 * dpr, 10 * dpr, 3 * dpr);
    ctx.fillStyle = 'rgba(255,255,255,0.72)';
    ctx.fillText('IMU', left + 52 * dpr, 13 * dpr);
    ctx.fillStyle = '#ff6b3a';
    ctx.fillRect(left + 78 * dpr, 5 * dpr, 10 * dpr, 3 * dpr);
    canvas.onclick = (event) => seekPlaybackFromInlineLeanGraphClick(event);
}

function fillRoundedRect(ctx, x, y, w, h, r) {
    const radius = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.lineTo(x + w - radius, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
    ctx.lineTo(x + w, y + h - radius);
    ctx.quadraticCurveTo(x + w, y + h, x + w - radius, y + h);
    ctx.lineTo(x + radius, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - radius);
    ctx.lineTo(x, y + radius);
    ctx.quadraticCurveTo(x, y, x + radius, y);
    ctx.closePath();
    ctx.fill();
}

function drawPlaybackSeriesGraph(ctx, rows, graph, dpr) {
    const padLeft = 54 * dpr;
    const padRight = 20 * dpr;
    const padTop = 36 * dpr;
    const padBottom = 28 * dpr;
    const left = graph.x + padLeft;
    const right = graph.x + graph.w - padRight;
    const top = graph.y + padTop;
    const bottom = graph.y + graph.h - padBottom;
    const graphValue = (value) => graph.valueTransform ? graph.valueTransform(value) : value;
    const values = rows.flatMap(row => [graphValue(row[graph.imuKey]), graphValue(row[graph.gpsKey])]).filter(Number.isFinite);
    const maxValue = Math.max(graph.minScale, ...values.map(value => Math.abs(value)));
    const xFor = (offset) => left + (offset / Math.max(1, rows.length - 1)) * (right - left);
    const yFor = (value) => top + ((maxValue - value) / (maxValue * 2)) * (bottom - top);

    ctx.fillStyle = 'rgba(16, 16, 16, 0.82)';
    fillRoundedRect(ctx, graph.x, graph.y, graph.w, graph.h, 18 * dpr);
    ctx.strokeStyle = 'rgba(255,255,255,0.12)';
    ctx.lineWidth = 1 * dpr;
    ctx.strokeRect(graph.x, graph.y, graph.w, graph.h);

    ctx.strokeStyle = 'rgba(255,255,255,0.14)';
    [-0.5, 0, 0.5].forEach(mark => {
        const gy = yFor(maxValue * mark);
        ctx.beginPath();
        ctx.moveTo(left, gy);
        ctx.lineTo(right, gy);
        ctx.stroke();
    });
    ctx.strokeStyle = 'rgba(255,255,255,0.42)';
    ctx.beginPath();
    ctx.moveTo(left, yFor(0));
    ctx.lineTo(right, yFor(0));
    ctx.stroke();

    drawPlaybackGraphLine(ctx, rows, graph.gpsKey, xFor, yFor, '#4da3ff', 2.0 * dpr, graph.valueTransform);
    drawPlaybackGraphLine(ctx, rows, graph.imuKey, xFor, yFor, '#ff6b3a', 1.8 * dpr, graph.valueTransform);

    const markerIndex = Math.max(0, rows.findIndex(row => row.index >= pbState.currentIndex));
    const markerX = xFor(markerIndex === -1 ? rows.length - 1 : markerIndex);
    ctx.strokeStyle = 'rgba(255,255,255,0.58)';
    ctx.lineWidth = 1 * dpr;
    ctx.beginPath();
    ctx.moveTo(markerX, top);
    ctx.lineTo(markerX, bottom);
    ctx.stroke();

    ctx.fillStyle = '#f5f5f5';
    ctx.font = `${14 * dpr}px sans-serif`;
    ctx.fillText(graph.title, graph.x + 18 * dpr, graph.y + 24 * dpr);
    ctx.fillStyle = '#4da3ff';
    ctx.fillText('GPS', graph.x + 360 * dpr, graph.y + 24 * dpr);
    ctx.fillStyle = '#ff6b3a';
    ctx.fillText('IMU', graph.x + 410 * dpr, graph.y + 24 * dpr);
    ctx.fillStyle = 'rgba(255,255,255,0.68)';
    ctx.font = `${12 * dpr}px sans-serif`;
    ctx.fillText(`+${maxValue.toFixed(graph.unit === 'g' ? 2 : 0)} ${graph.unit}`, graph.x + 10 * dpr, top + 8 * dpr);
    ctx.fillText(`-${maxValue.toFixed(graph.unit === 'g' ? 2 : 0)} ${graph.unit}`, graph.x + 10 * dpr, bottom);
    ctx.fillText(graph.positiveLabel, right - 58 * dpr, top + 12 * dpr);
    ctx.fillText(graph.negativeLabel, right - 58 * dpr, bottom - 6 * dpr);
}

function drawPlaybackGraphLine(ctx, rows, key, xFor, yFor, color, width, valueTransform = null) {
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    let drawing = false;
    ctx.beginPath();
    rows.forEach((row, offset) => {
        const value = valueTransform ? valueTransform(row[key]) : row[key];
        if (!Number.isFinite(value)) {
            drawing = false;
            return;
        }
        const x = xFor(offset);
        const y = yFor(value);
        if (!drawing) {
            ctx.moveTo(x, y);
            drawing = true;
        } else {
            ctx.lineTo(x, y);
        }
    });
    ctx.stroke();
}

function drawPlaybackLocalLagGraph(ctx, rows, diagnostics, graph, dpr) {
    const padLeft = 54 * dpr;
    const padRight = 20 * dpr;
    const padTop = 36 * dpr;
    const padBottom = 28 * dpr;
    const left = graph.x + padLeft;
    const right = graph.x + graph.w - padRight;
    const top = graph.y + padTop;
    const bottom = graph.y + graph.h - padBottom;
    const lags = diagnostics?.segments?.map(segment => segment.lagMs).filter(Number.isFinite) || [];
    const scores = diagnostics?.segments?.map(segment => segment.score).filter(Number.isFinite) || [];
    const lagExtent = Math.max(250, ...lags.map(value => Math.abs(value)));
    const xFor = (offset) => left + (offset / Math.max(1, rows.length - 1)) * (right - left);
    const yForLag = (value) => top + ((lagExtent - value) / (lagExtent * 2)) * (bottom - top);

    ctx.fillStyle = 'rgba(16, 16, 16, 0.82)';
    fillRoundedRect(ctx, graph.x, graph.y, graph.w, graph.h, 18 * dpr);
    ctx.strokeStyle = 'rgba(255,255,255,0.12)';
    ctx.lineWidth = 1 * dpr;
    ctx.strokeRect(graph.x, graph.y, graph.w, graph.h);

    ctx.strokeStyle = 'rgba(255,255,255,0.14)';
    [-0.5, 0, 0.5].forEach(mark => {
        const gy = yForLag(lagExtent * mark);
        ctx.beginPath();
        ctx.moveTo(left, gy);
        ctx.lineTo(right, gy);
        ctx.stroke();
    });
    ctx.strokeStyle = 'rgba(255,255,255,0.42)';
    ctx.beginPath();
    ctx.moveTo(left, yForLag(0));
    ctx.lineTo(right, yForLag(0));
    ctx.stroke();

    const segments = diagnostics?.segments || [];
    if (segments.length) {
        ctx.strokeStyle = '#ffd166';
        ctx.lineWidth = 2 * dpr;
        ctx.lineJoin = 'round';
        ctx.lineCap = 'round';
        ctx.beginPath();
        segments.forEach((segment, index) => {
            const x = xFor(segment.centerOffset);
            const y = yForLag(segment.lagMs);
            if (index === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.stroke();

        segments.forEach((segment) => {
            const x = xFor(segment.centerOffset);
            const y = yForLag(segment.lagMs);
            const alpha = Math.max(0.25, Math.min(1, segment.score || 0));
            ctx.fillStyle = `rgba(255, 209, 102, ${alpha})`;
            ctx.beginPath();
            ctx.arc(x, y, Math.max(2 * dpr, 4 * alpha * dpr), 0, Math.PI * 2);
            ctx.fill();
        });
    }

    const markerIndex = Math.max(0, rows.findIndex(row => row.index >= pbState.currentIndex));
    const markerX = xFor(markerIndex === -1 ? rows.length - 1 : markerIndex);
    ctx.strokeStyle = 'rgba(255,255,255,0.58)';
    ctx.lineWidth = 1 * dpr;
    ctx.beginPath();
    ctx.moveTo(markerX, top);
    ctx.lineTo(markerX, bottom);
    ctx.stroke();

    ctx.fillStyle = '#f5f5f5';
    ctx.font = `${14 * dpr}px sans-serif`;
    ctx.fillText(graph.title, graph.x + 18 * dpr, graph.y + 24 * dpr);
    ctx.fillStyle = '#ffd166';
    ctx.fillText('Lag', graph.x + 366 * dpr, graph.y + 24 * dpr);
    ctx.fillStyle = 'rgba(255,255,255,0.68)';
    ctx.font = `${12 * dpr}px sans-serif`;
    ctx.fillText(`+${Math.round(lagExtent)} ms`, graph.x + 10 * dpr, top + 8 * dpr);
    ctx.fillText(`-${Math.round(lagExtent)} ms`, graph.x + 10 * dpr, bottom);
    const scoreText = scores.length ? `score ${Math.max(...scores).toFixed(2)} best` : 'no local windows';
    ctx.fillText(scoreText, right - 120 * dpr, top + 12 * dpr);
}

function getPlaybackLocalLagDiagnostics(rows) {
    if (!rows?.length) return null;
    const sampleIndexes = [0, Math.floor(rows.length / 2), rows.length - 1]
        .map(index => rows[index])
        .map(row => `${row?.time ?? 'x'}:${row?.imuLong ?? 'x'}:${row?.gpsLong ?? 'x'}`)
        .join('|');
    const key = [
        pbState.selectedLap || 'all',
        rows.length,
        pbState.data?.gps_lag_ms_applied ?? 0,
        sampleIndexes,
    ].join('::');
    if (pbState.localLagDiagnostics?.key === key) {
        return pbState.localLagDiagnostics.value;
    }
    const value = computePlaybackLocalLagDiagnostics(rows);
    pbState.localLagDiagnostics = { key, value };
    return value;
}

function computePlaybackLocalLagDiagnostics(rows) {
    if (!rows.length) return null;
    const dtValues = [];
    for (let index = 1; index < rows.length; index += 1) {
        const dtMs = (Number(rows[index].time) - Number(rows[index - 1].time)) * 1000;
        if (Number.isFinite(dtMs) && dtMs > 1) dtValues.push(dtMs);
    }
    if (!dtValues.length) return null;
    const sortedDt = dtValues.slice().sort((a, b) => a - b);
    const medianDtMs = sortedDt[Math.floor(sortedDt.length / 2)] || 20;
    const windowSize = Math.max(140, Math.min(560, Math.round(rows.length / 5)));
    const stepSize = Math.max(60, Math.round(windowSize / 3));
    const maxShift = Math.max(4, Math.min(240, Math.round(3000 / Math.max(5, medianDtMs))));
    const segments = [];

    for (let start = 0; start + windowSize <= rows.length; start += stepSize) {
        const end = start + windowSize;
        const windowRows = rows.slice(start, end);
        const best = playbackBestLagForWindow(windowRows, maxShift);
        if (!best) continue;
        segments.push({
            centerOffset: start + Math.floor(windowRows.length / 2),
            lagMs: best.shift * medianDtMs,
            score: best.score,
            samples: best.samples,
        });
    }
    if (!segments.length) return null;
    return {
        segments,
        medianDtMs,
        minLagMs: Math.min(...segments.map(segment => segment.lagMs)),
        maxLagMs: Math.max(...segments.map(segment => segment.lagMs)),
    };
}

function playbackBestLagForWindow(rows, maxShift) {
    let best = null;
    for (let shift = -maxShift; shift <= maxShift; shift += 1) {
        const candidate = playbackCorrelationAtShift(rows, shift);
        if (!candidate) continue;
        if (!best || candidate.score > best.score) {
            best = { ...candidate, shift };
        }
    }
    return best;
}

function playbackCorrelationAtShift(rows, shift) {
    let count = 0;
    let sumImu = 0;
    let sumGps = 0;
    let sumImu2 = 0;
    let sumGps2 = 0;
    let sumCross = 0;
    for (let index = 0; index < rows.length; index += 1) {
        const shiftedIndex = index + shift;
        if (shiftedIndex < 0 || shiftedIndex >= rows.length) continue;
        const imu = finiteOrNull(rows[index].imuLong);
        const gps = finiteOrNull(rows[shiftedIndex].gpsLong);
        if (imu == null || gps == null) continue;
        count += 1;
        sumImu += imu;
        sumGps += gps;
        sumImu2 += imu * imu;
        sumGps2 += gps * gps;
        sumCross += imu * gps;
    }
    if (count < Math.max(40, Math.floor(rows.length * 0.35))) return null;
    const numerator = count * sumCross - sumImu * sumGps;
    const denomLeft = count * sumImu2 - sumImu * sumImu;
    const denomRight = count * sumGps2 - sumGps * sumGps;
    const denominator = Math.sqrt(Math.max(1e-9, denomLeft * denomRight));
    if (!Number.isFinite(denominator) || denominator <= 1e-9) return null;
    return {
        score: Math.abs(numerator / denominator),
        samples: count,
    };
}

function seekPlaybackFromGraphClick(event) {
    const canvas = document.getElementById('playbackGraphCanvas');
    const rows = playbackGraphRows();
    if (!canvas || !rows.length) return;
    const rect = canvas.getBoundingClientRect();
    const xRatio = Math.max(0, Math.min(1, (event.clientX - rect.left) / Math.max(1, rect.width)));
    const row = rows[Math.round(xRatio * (rows.length - 1))];
    if (!row) return;
    pbState.currentIndex = row.index;
    pbState.playbackTime = pbState.data.time[row.index];
    const slider = document.getElementById('pbSeek');
    if (slider) slider.value = row.index;
    drawFrame();
    drawPlaybackComparisonGraph();
}

function seekPlaybackFromInlineLeanGraphClick(event) {
    const canvas = document.getElementById('pbLeanInlineCanvas');
    const rows = playbackGraphRows();
    if (!canvas || !rows.length) return;
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const ratio = Math.max(0, Math.min(1, x / Math.max(1, rect.width)));
    const row = rows[Math.round(ratio * (rows.length - 1))];
    if (!row) return;
    pbState.currentIndex = row.index;
    pbState.playbackTime = pbState.data.time[row.index];
    drawFrame();
    drawInlinePlaybackLeanGraph();
    if (document.getElementById('playbackGraphModal')?.classList.contains('active')) {
        drawPlaybackComparisonGraph();
    }
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
    sel.value = pbState.selectedLap;

    // Buttons
    document.getElementById('pbPlayPause').textContent = '▶';
    const pathSourceInputs = document.getElementsByName('pbPathSource');
    for (let input of pathSourceInputs) {
        input.checked = input.value === (pbState.pathSource || 'aligned');
    }
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

    if (pbState.canonicalLayout && (pbState.displayProjectedPoints?.length || pbState.projectedPoints?.length)) {
        const padding = 20;
        const availW = w - padding * 2;
        const availH = h - padding * 2;
        const layoutW = pbState.canonicalLayout.layout_width || 1;
        const layoutH = pbState.canonicalLayout.layout_height || 1;
        const scaleX = availW / layoutW;
        const scaleY = availH / layoutH;
        pbState.scale = Math.min(scaleX, scaleY);
        pbState.offsetX = padding + (availW - layoutW * pbState.scale) / 2;
        pbState.offsetY = padding + (availH - layoutH * pbState.scale) / 2;
        pbState.bounds = null;
        renderStaticMap();
        return;
    }

    // Calculate Bounds
    const pathSeries = playbackSelectedPathSeries();
    const lats = pathSeries.lats;
    const lons = pathSeries.lons;
    if (!lats || !lons || lats.length === 0) return;

    let minLat = 90, maxLat = -90, minLon = 180, maxLon = -180;

    // Sampling for performance
    const step = Math.ceil(lats.length / 2000) || 1;
    for (let i = 0; i < lats.length; i += step) {
        if (pathSeries.fixOnly && !pbState.data.gps_is_fix?.[i]) continue;
        if (lats[i] == null || lons[i] == null || !Number.isFinite(lats[i]) || !Number.isFinite(lons[i])) continue;
        if (lats[i] < minLat) minLat = lats[i];
        if (lats[i] > maxLat) maxLat = lats[i];
        if (lons[i] < minLon) minLon = lons[i];
        if (lons[i] > maxLon) maxLon = lons[i];
    }
    if (minLat === 90 || minLon === 180) return;

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

function projectPlaybackPoint(index) {
    const interpolateMissingPoint = (lookup) => {
        const times = pbState.data?.time || [];
        let left = index;
        let right = index;
        let leftPoint = null;
        let rightPoint = null;
        while (left >= 0) {
            leftPoint = lookup(left);
            if (leftPoint) break;
            left -= 1;
        }
        while (right < times.length) {
            rightPoint = lookup(right);
            if (rightPoint) break;
            right += 1;
        }
        if (leftPoint && rightPoint && left !== right) {
            const leftTime = times[left];
            const rightTime = times[right];
            const currentTime = times[index];
            const span = Math.max(1e-9, rightTime - leftTime);
            const alpha = Math.max(0, Math.min(1, (currentTime - leftTime) / span));
            return {
                x: leftPoint.x + (rightPoint.x - leftPoint.x) * alpha,
                y: leftPoint.y + (rightPoint.y - leftPoint.y) * alpha,
            };
        }
        return leftPoint || rightPoint || null;
    };

    const projected = pbState.pathSource === 'rawfix'
        ? pbState.projectedPoints
        : pbState.pathSource === 'display'
            ? (pbState.displayProjectedPoints || pbState.alignedProjectedPoints || pbState.projectedPoints)
            : (pbState.alignedProjectedPoints || pbState.displayProjectedPoints || pbState.projectedPoints);
    if (pbState.canonicalLayout && projected?.length) {
        let clamped = Math.max(0, Math.min(projected.length - 1, index));
        let point = projected[clamped];
        if (!point) {
            return interpolateMissingPoint((candidateIndex) => {
                const candidate = projected[candidateIndex];
                if (!candidate) return null;
                return {
                    x: candidate.x * pbState.scale + pbState.offsetX,
                    y: candidate.y * pbState.scale + pbState.offsetY,
                };
            });
        }
        if (!point) return null;
        return {
            x: point.x * pbState.scale + pbState.offsetX,
            y: point.y * pbState.scale + pbState.offsetY
        };
    }
    const lat = pbState.pathSource === 'rawfix'
        ? (pbState.data.lat[index])
        : pbState.pathSource === 'display'
            ? (pbState.data.display_lat?.[index] ?? pbState.data.aligned_lat?.[index] ?? pbState.data.lat[index])
            : (pbState.data.aligned_lat?.[index] ?? pbState.data.display_lat?.[index] ?? pbState.data.lat[index]);
    const lon = pbState.pathSource === 'rawfix'
        ? (pbState.data.lon[index])
        : pbState.pathSource === 'display'
            ? (pbState.data.display_lon?.[index] ?? pbState.data.aligned_lon?.[index] ?? pbState.data.lon[index])
            : (pbState.data.aligned_lon?.[index] ?? pbState.data.display_lon?.[index] ?? pbState.data.lon[index]);
    if (lat == null || lon == null || !Number.isFinite(lat) || !Number.isFinite(lon)) {
        return interpolateMissingPoint((candidateIndex) => {
            const candidateLat = pbState.pathSource === 'rawfix'
                ? pbState.data.lat[candidateIndex]
                : pbState.pathSource === 'display'
                    ? (pbState.data.display_lat?.[candidateIndex] ?? pbState.data.aligned_lat?.[candidateIndex] ?? pbState.data.lat[candidateIndex])
                    : (pbState.data.aligned_lat?.[candidateIndex] ?? pbState.data.display_lat?.[candidateIndex] ?? pbState.data.lat[candidateIndex]);
            const candidateLon = pbState.pathSource === 'rawfix'
                ? pbState.data.lon[candidateIndex]
                : pbState.pathSource === 'display'
                    ? (pbState.data.display_lon?.[candidateIndex] ?? pbState.data.aligned_lon?.[candidateIndex] ?? pbState.data.lon[candidateIndex])
                    : (pbState.data.aligned_lon?.[candidateIndex] ?? pbState.data.display_lon?.[candidateIndex] ?? pbState.data.lon[candidateIndex]);
            if (candidateLat == null || candidateLon == null || !Number.isFinite(candidateLat) || !Number.isFinite(candidateLon)) return null;
            return project(candidateLat, candidateLon);
        });
    }
    return project(lat, lon);
}

function projectRawPlaybackPoint(index) {
    if (pbState.canonicalLayout && pbState.projectedPoints?.length) {
        const point = pbState.projectedPoints[Math.max(0, Math.min(pbState.projectedPoints.length - 1, index))];
        if (!point) return null;
        return {
            x: point.x * pbState.scale + pbState.offsetX,
            y: point.y * pbState.scale + pbState.offsetY
        };
    }
    const lat = pbState.data.lat[index];
    const lon = pbState.data.lon[index];
    if (lat == null || lon == null || !Number.isFinite(lat) || !Number.isFinite(lon)) return null;
    return project(lat, lon);
}

function playbackTimeWindow(timeSec) {
    const times = pbState.data?.time || [];
    if (!times.length) return { left: 0, right: 0, alpha: 0 };
    const right = playbackIndexForTime(timeSec);
    const left = Math.max(0, right - 1);
    const leftTime = times[left];
    const rightTime = times[right];
    const span = Math.max(1e-9, rightTime - leftTime);
    const alpha = left === right ? 0 : Math.max(0, Math.min(1, (timeSec - leftTime) / span));
    return { left, right, alpha };
}

function playbackSeriesValueAtTime(series, timeSec, fallbackIndex = 0) {
    if (!Array.isArray(series) || !series.length) return null;
    const { left, right, alpha } = playbackTimeWindow(timeSec);
    const a = Number(series[left]);
    const b = Number(series[right]);
    if (Number.isFinite(a) && Number.isFinite(b)) {
        return a + ((b - a) * alpha);
    }
    if (Number.isFinite(a)) return a;
    if (Number.isFinite(b)) return b;
    const fallback = Number(series[Math.max(0, Math.min(series.length - 1, fallbackIndex))]);
    return Number.isFinite(fallback) ? fallback : null;
}

function playbackPathTimeOffsetSec() {
    const lagMs = Number(pbState.data?.gps_lag_ms_applied ?? 0) || 0;
    const trimMs = Number(pbState.data?.path_trim_ms ?? pbState.data?.active_tune?.pathTrimMs ?? 0) || 0;
    return (lagMs + trimMs) / 1000.0;
}

function projectPlaybackPointAtTime(timeSec) {
    if (pbState.pathSource === 'rawfix') {
        const index = playbackNearestFixIndexForTime(timeSec + playbackPathTimeOffsetSec());
        return index == null ? null : projectPlaybackPoint(index);
    }
    const { left, right, alpha } = playbackTimeWindow(timeSec);
    const a = projectPlaybackPoint(left);
    const b = projectPlaybackPoint(right);
    if (a && b) {
        return {
            x: a.x + (b.x - a.x) * alpha,
            y: a.y + (b.y - a.y) * alpha,
        };
    }
    return a || b || null;
}

function playbackNearestFixIndexForTime(timeSec) {
    const times = pbState.data?.time || [];
    const fixes = pbState.data?.gps_is_fix || [];
    if (!times.length) return null;
    let bestIndex = null;
    let bestDistance = Infinity;
    for (let index = 0; index < times.length; index += 1) {
        if (!fixes[index]) continue;
        if (pbState.data.lat?.[index] == null || pbState.data.lon?.[index] == null) continue;
        const distance = Math.abs(Number(times[index]) - Number(timeSec));
        if (distance < bestDistance) {
            bestDistance = distance;
            bestIndex = index;
        }
    }
    return bestIndex;
}

function playbackLapByNumber(lapNumber) {
    const laps = pbState.laps || [];
    return laps.find(lap => String(lap.lap_number) === String(lapNumber)) || null;
}

function playbackLapForTime(timeSec) {
    const laps = pbState.laps || [];
    for (let i = 0; i < laps.length; i += 1) {
        const lap = laps[i];
        const lapEnd = Number.isFinite(lap.end_time) ? lap.end_time : (lap.start_time + (lap.lap_time || 0));
        if (timeSec >= lap.start_time && timeSec <= lapEnd) return lap;
    }
    return null;
}

function playbackIndexForTime(timeSec) {
    const times = pbState.data?.time || [];
    if (!times.length) return 0;
    for (let i = 0; i < times.length; i += 1) {
        if (times[i] >= timeSec) return i;
    }
    return times.length - 1;
}

function currentPlaybackLapBounds() {
    const times = pbState.data?.time || [];
    if (!times.length) return { startIndex: 0, endIndex: 0, lapKey: 'empty' };
    if (pbState.selectedLap && pbState.selectedLap !== 'all') {
        const lap = playbackLapByNumber(pbState.selectedLap);
        if (lap) {
            const lapEnd = Number.isFinite(lap.end_time) ? lap.end_time : (lap.start_time + (lap.lap_time || 0));
            const startIndex = playbackIndexForTime(lap.start_time);
            const endIndex = Math.max(startIndex + 1, playbackIndexForTime(lapEnd) + 1);
            return {
                startIndex,
                endIndex,
                lapKey: `lap-${lap.lap_number}`,
            };
        }
    }
    return { startIndex: 0, endIndex: times.length, lapKey: 'session' };
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
    const { startIndex, endIndex, lapKey } = currentPlaybackLapBounds();
    pbState.renderedLapKey = lapKey;
    const pathSeries = playbackSelectedPathSeries();

    if (pbState.canonicalLayout && (pathSeries.projected?.length || pbState.projectedPoints?.length)) {
        if (pbState.layoutImage) {
            ctx.drawImage(
                pbState.layoutImage,
                pbState.offsetX,
                pbState.offsetY,
                (pbState.canonicalLayout.layout_width || 1) * pbState.scale,
                (pbState.canonicalLayout.layout_height || 1) * pbState.scale
            );
        }

        drawPlaybackGpsDiagnostics(ctx, data, startIndex, Math.min(endIndex, count), {
            projectIndex: (index) => projectPlaybackPoint(index),
            speedSeries: pathSeries.speeds,
            fixOnly: pathSeries.fixOnly,
            emphasizeFixes: pathSeries.fixOnly,
        });
        return;
    }

    drawPlaybackGpsDiagnostics(ctx, data, startIndex, Math.min(endIndex, count), {
        projectIndex: (index) => projectPlaybackPoint(index),
        speedSeries: pathSeries.speeds,
        fixOnly: pathSeries.fixOnly,
        emphasizeFixes: pathSeries.fixOnly,
    });
}

function drawPlaybackGpsDiagnostics(ctx, data, startIndex, endIndex, options) {
    const projectIndex = typeof options === 'function' ? options : options?.projectIndex;
    const speedSeries = options?.speedSeries || data.display_speed || data.speed || [];
    const fixOnly = Boolean(options?.fixOnly);
    const emphasizeFixes = Boolean(options?.emphasizeFixes);
    const gpsValid = data.gps_is_valid || [];
    const gpsFix = data.gps_is_fix || [];
    const points = [];
    const rangeCount = Math.max(0, endIndex - startIndex);
    const step = pbState.selectedLap === 'all' ? Math.max(1, Math.ceil(rangeCount / 2500)) : 1;
    for (let i = startIndex; i < endIndex; i += step) {
        if (gpsValid.length && !gpsValid[i]) continue;
        if (fixOnly && !gpsFix[i]) continue;
        const point = projectIndex(i);
        if (!point) continue;
        points.push({
            x: point.x,
            y: point.y,
            index: i,
            isFix: Boolean(gpsFix[i]),
        });
    }

    if (!points.length) return;

    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    let minSpeed = 0;
    let maxSpeed = 1;
    if (pbState.mapMode === 'speed') {
        const speeds = [];
        for (let index = startIndex; index < endIndex; index += step) {
            const speed = Number(speedSeries[index]);
            if (Number.isFinite(speed)) speeds.push(speed);
        }
        minSpeed = speeds.length ? Math.min(...speeds) : 0;
        maxSpeed = speeds.length ? Math.max(...speeds) : 1;
    }
    for (let i = 1; i < points.length; i += 1) {
        const prev = points[i - 1];
        const next = points[i];
        let strokeStyle = 'rgba(150, 150, 150, 0.72)';
        if (pbState.mapMode === 'speed') {
            const a = Number(speedSeries?.[prev.index]);
            const b = Number(speedSeries?.[next.index]);
            const avg = [a, b].filter(Number.isFinite).reduce((sum, value) => sum + value, 0) / Math.max(1, [a, b].filter(Number.isFinite).length);
            strokeStyle = getHeatmapColor(avg || 0, minSpeed, maxSpeed || minSpeed + 1);
        } else if (pbState.mapMode === 'accel') {
            const axPrev = Number(data.display_long_g?.[prev.index] ?? data.long_g?.[prev.index] ?? data.ax?.[prev.index] ?? data.raw_ax?.[prev.index]);
            const ayPrev = Number(data.display_lat_g?.[prev.index] ?? data.lat_g?.[prev.index] ?? data.ay?.[prev.index] ?? data.raw_ay?.[prev.index]);
            const axNext = Number(data.display_long_g?.[next.index] ?? data.long_g?.[next.index] ?? data.ax?.[next.index] ?? data.raw_ax?.[next.index]);
            const ayNext = Number(data.display_lat_g?.[next.index] ?? data.lat_g?.[next.index] ?? data.ay?.[next.index] ?? data.raw_ay?.[next.index]);
            const magPrev = Number.isFinite(axPrev) && Number.isFinite(ayPrev) ? Math.sqrt(axPrev * axPrev + ayPrev * ayPrev) : 0;
            const magNext = Number.isFinite(axNext) && Number.isFinite(ayNext) ? Math.sqrt(axNext * axNext + ayNext * ayNext) : 0;
            strokeStyle = getHeatmapColor((magPrev + magNext) / 2, 0, 1.5);
        }
        ctx.strokeStyle = strokeStyle;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(prev.x, prev.y);
        ctx.lineTo(next.x, next.y);
        ctx.stroke();
    }

    for (let i = 0; i < points.length; i += 1) {
        const point = points[i];
        ctx.beginPath();
        const radius = point.isFix ? (emphasizeFixes ? 2.8 : 2.2) : 1.7;
        ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
        ctx.fillStyle = point.isFix ? '#ff4d4f' : '#4da3ff';
        ctx.fill();
    }
}

function getHeatmapColor(val, min, max) {
    let t = (val - min) / (max - min);
    if (t < 0) t = 0;
    if (t > 1) t = 1;
    if (t < 0.33) {
        const local = t / 0.33;
        return `rgb(${Math.round(0)}, ${Math.round(180 + (75 * local))}, ${Math.round(255 - (135 * local))})`;
    }
    if (t < 0.66) {
        const local = (t - 0.33) / 0.33;
        return `rgb(${Math.round(255 * local)}, ${Math.round(255 - (55 * local))}, ${Math.round(120 - (120 * local))})`;
    }
    const local = (t - 0.66) / 0.34;
    return `rgb(255, ${Math.round(200 - (200 * local))}, 0)`;
}

function updateHeatmapMode() {
    const modes = document.getElementsByName('pbMapMode');
    for (let m of modes) {
        if (m.checked) pbState.mapMode = m.value;
    }
    renderStaticMap();
    if (!pbState.playing) drawFrame();
}

function updatePlaybackPathSource() {
    const inputs = document.getElementsByName('pbPathSource');
    for (let input of inputs) {
        if (input.checked) pbState.pathSource = input.value;
    }
    pbState.localLagDiagnostics = null;
    pbState.pathCache = null;
    pbState.renderedLapKey = null;
    fitTrackMap();
    if (!pbState.playing) {
        drawFrame();
    }
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

async function jumpToLap(val) {
    pbState.selectedLap = val;
    if (val === 'all') {
        if (pbState.playbackManifest) {
            activatePlaybackData(normalizePlaybackData(pbState.playbackManifest, pbState.session?.laps || []), 'all');
            return;
        }
        pbState.currentIndex = 0;
    } else {
        try {
            const chunk = await loadPlaybackLapChunk(parseInt(val));
            if (chunk) {
                activatePlaybackData(chunk.data, val);
                prefetchPlaybackLap(parseInt(val) + 1);
                return;
            }
        } catch (error) {
            console.error('Failed to load playback lap chunk', error);
        }
    }
    // Sync Time
    if (pbState.data) pbState.playbackTime = pbState.data.time[pbState.currentIndex];
    drawFrame();
}

function prefetchPlaybackLap(lapNumber) {
    if (!lapNumber || pbState.lapCache?.[String(lapNumber)]) return;
    const lap = pbState.laps?.find(item => Number(item.lap_number) === Number(lapNumber));
    if (!lap) return;
    loadPlaybackLapChunk(lapNumber).catch(() => {});
}

async function nextLapPlay() {
    const curTime = pbState.data.time[Math.floor(pbState.currentIndex)];
    const curLap = playbackLapForTime(curTime);

    if (curLap) {
        const nextLapNum = curLap.lap_number + 1;
        const nextLap = pbState.laps.find(l => l.lap_number === nextLapNum);
        if (nextLap) {
            await jumpToLap(String(nextLapNum));
        } else {
            pbState.selectedLap = 'all';
            pbState.currentIndex = 0;
            togglePlayback(false);
        }
    } else {
        await jumpToLap(1);
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
    const selectedLap = pbState.selectedLap && pbState.selectedLap !== 'all'
        ? playbackLapByNumber(pbState.selectedLap)
        : null;
    if (selectedLap) {
        const lapEnd = Number.isFinite(selectedLap.end_time) ? selectedLap.end_time : (selectedLap.start_time + (selectedLap.lap_time || 0));
        if (pbState.playbackTime > lapEnd) {
            pbState.playbackTime = selectedLap.start_time;
            pbState.currentIndex = playbackIndexForTime(selectedLap.start_time);
        }
    }

    // Advance index to match playbackTime
    while (pbState.currentIndex < times.length - 1 && times[pbState.currentIndex + 1] <= pbState.playbackTime) {
        pbState.currentIndex++;
    }

    if (!selectedLap && pbState.currentIndex >= times.length - 1) {
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
    if (!data) return;
    const timeSec = pbState.playbackTime ?? data.time[i];
    drawInlinePlaybackLeanGraph();

    const currentLap = currentPlaybackLapBounds();
    if (pbState.renderedLapKey !== currentLap.lapKey) {
        renderStaticMap();
    }

    const ctx = pbState.ctx;
    ctx.clearRect(0, 0, pbState.width, pbState.height);

    if (pbState.pathCache) {
        ctx.drawImage(pbState.pathCache, 0, 0);
    }

    const p = projectPlaybackPointAtTime(timeSec);
    if (!p) return;

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
    const t = timeSec - pbState.startTime;
    const timeEl = document.getElementById('pbTime');
    if (timeEl) timeEl.textContent = formatDuration(t);

    // ===== LAP TIME & DELTA =====
    let currentLapNum = 0;
    let lapStartTime = pbState.startTime;
    let lapEndTime = null;
    let bestLapTime = null;
    let activeLap = null;
    let bestLap = null;

    if (pbState.laps && pbState.laps.length > 0) {
        const rowLapNumber = data.lap_number?.[i];
        activeLap = rowLapNumber ? playbackLapByNumber(rowLapNumber) : playbackLapForTime(timeSec);
        if (activeLap) {
            currentLapNum = activeLap.lap_number || 1;
            lapStartTime = activeLap.start_time;
            lapEndTime = activeLap.end_time;
        }

        // Find best lap time
        const validLaps = pbState.laps.filter(l => l.lap_time && l.lap_time > 0);
        if (validLaps.length > 0) {
            bestLapTime = Math.min(...validLaps.map(l => l.lap_time));
            bestLap = validLaps.reduce((best, lap) => (best == null || lap.lap_time < best.lap_time ? lap : best), null);
        }
    }

    // Current lap time
    const currentLapTime = timeSec - lapStartTime;
    const lapTimeEl = document.getElementById('pbLapTime');
    if (lapTimeEl) {
        lapTimeEl.textContent = formatLapTime(currentLapTime);
    }

    // Lap number display
    const lapNumEl = document.getElementById('pbLapNumber');
    if (lapNumEl) {
        const totalLaps = pbState.laps ? pbState.laps.length : 1;
        lapNumEl.textContent = currentLapNum > 0 ? `${currentLapNum}/${totalLaps}` : `--/${totalLaps}`;
    }

    // Delta calculation aligned by actual sector timings when available.
    const deltaEl = document.getElementById('pbDeltaText');
    const deltaFillEl = document.getElementById('pbDeltaFill');
    if (deltaEl && deltaFillEl && bestLapTime) {
        let delta = 0;
        const currentSectorTimes = activeLap?.sector_times || [];
        const bestSectorTimes = bestLap?.sector_times || [];

        if (currentSectorTimes.length && currentSectorTimes.length === bestSectorTimes.length) {
            let currentAccum = 0;
            let bestAccum = 0;
            let expectedTime = currentLapTime;
            for (let si = 0; si < currentSectorTimes.length; si += 1) {
                const currentSector = Number(currentSectorTimes[si]);
                const bestSector = Number(bestSectorTimes[si]);
                if (!Number.isFinite(currentSector) || !Number.isFinite(bestSector) || currentSector <= 0 || bestSector <= 0) {
                    continue;
                }
                if (currentLapTime <= currentAccum + currentSector) {
                    const progress = (currentLapTime - currentAccum) / currentSector;
                    expectedTime = bestAccum + progress * bestSector;
                    break;
                }
                currentAccum += currentSector;
                bestAccum += bestSector;
                expectedTime = bestAccum;
            }
            delta = currentLapTime - expectedTime;
        } else {
            const lapProgress = lapEndTime ?
                (data.time[i] - lapStartTime) / Math.max(1e-9, (lapEndTime - lapStartTime)) :
                Math.min(currentLapTime / bestLapTime, 1);
            delta = currentLapTime - (lapProgress * bestLapTime);
        }

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
    const SECTOR_COUNT = 7;
    const sectorEls = [];
    const sectorBoxes = [];
    for (let s = 1; s <= SECTOR_COUNT; s++) {
        sectorEls.push(document.getElementById(`pbS${s}Time`));
        sectorBoxes.push(document.getElementById(`pbS${s}`));
    }

    if (sectorEls[0]) {
        const sectorTimes = activeLap?.sector_times || [];
        sectorBoxes.forEach(box => { if (box) box.style.borderColor = 'transparent'; });
        let activeSector = Number.isFinite(data.sector_index?.[i]) ? Number(data.sector_index[i]) - 1 : -1;
        let sectorStart = 0;

        for (let s = 0; s < SECTOR_COUNT; s++) {
            const sectorDuration = Number(sectorTimes[s]);
            if (!Number.isFinite(sectorDuration) || sectorDuration <= 0) {
                sectorEls[s].textContent = '--.-';
                continue;
            }
            const sectorEnd = sectorStart + sectorDuration;
            if (activeSector === -1 && currentLapTime < sectorEnd) {
                activeSector = s;
            }
            if (s < activeSector || (activeSector === -1 && currentLapTime >= sectorEnd)) {
                sectorEls[s].textContent = sectorDuration.toFixed(1);
            } else if (s === activeSector) {
                sectorEls[s].textContent = Math.max(0, currentLapTime - sectorStart).toFixed(1);
                if (sectorBoxes[s]) sectorBoxes[s].style.borderColor = '#fff';
            } else {
                sectorEls[s].textContent = '--.-';
            }
            sectorStart = sectorEnd;
        }
    }

    // Speed
    const speed = playbackSeriesValueAtTime(data.aligned_speed || data.display_speed || data.speed, timeSec, i) ?? 0;
    const speedVal = Math.round(speed);
    const speedEl = document.getElementById('pbSpeed');
    if (speedEl) speedEl.textContent = speedVal;
    const speedDockEl = document.getElementById('pbSpeedDock');
    if (speedDockEl) speedDockEl.textContent = speedVal;

    // Lean Angle
    // Priority: Explicit Lean > Roll > Derived from Gyro/Speed > 0
    let lean = 0;
    const displayLean = playbackSeriesValueAtTime(data.display_lean_deg || data.lean_deg, timeSec, i);
    if (displayLean !== null) {
        lean = displayLean;
    } else if (data.lean_angle && data.lean_angle[i] !== undefined) {
        lean = data.lean_angle[i];
    } else if (data.roll && data.roll[i] !== undefined) {
        lean = data.roll[i];
    } else if (data.lean_deg && data.lean_deg[i] !== undefined && data.lean_deg[i] !== null) {
        lean = data.lean_deg[i];
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
    const leanDockEl = document.getElementById('pbLeanDock');
    if (leanDockEl) {
        const leanDir = lean > 0 ? 'R' : (lean < 0 ? 'L' : '');
        leanDockEl.textContent = `${Math.abs(Math.round(lean))}° ${leanDir}`;
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

    const displayLong = playbackSeriesValueAtTime(data.display_long_g || data.long_g, timeSec, i);
    const displayLat = playbackSeriesValueAtTime(data.display_lat_g || data.lat_g, timeSec, i);
    if (displayLong !== null) gx = displayLong;
    else if (data.long_g && data.long_g[i] !== undefined && data.long_g[i] !== null) gx = data.long_g[i];
    else if (data.ax && data.ax[i] !== undefined) gx = data.ax[i];
    else if (data.raw_ax && data.raw_ax[i] !== undefined) gx = data.raw_ax[i];

    if (displayLat !== null) gy = displayLat;
    else if (data.lat_g && data.lat_g[i] !== undefined && data.lat_g[i] !== null) gy = data.lat_g[i];
    else if (data.ay && data.ay[i] !== undefined) gy = data.ay[i];
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
// BROWSER-BASED SYNC
// ============================================================================
/**
 * Manual CSV Upload Handling
 */
function triggerFileUpload() {
    const input = document.getElementById('manualCsvUpload');
    if (input) input.click();
}

async function handleManualUpload(event) {
    const files = Array.from(event.target.files || []);
    if (!files || files.length === 0) return;

    showToast(`Uploading ${files.length} file(s)...`, 'info');
    updateProcessQueueCount({
        totalFiles: window.currentFiles?.length || 0,
        processedFiles: window.processedFiles?.size || 0,
        archivedView: isArchivesView,
        message: `Uploading ${files.length} CSV file${files.length === 1 ? '' : 's'}...`
    });

    let successCount = 0;
    let failCount = 0;

    for (let i = 0; i < files.length; i++) {
        try {
            const success = await uploadOneFile(files[i]);
            if (success) successCount++;
            else failCount++;
        } catch (e) {
            console.error('Upload failed:', e);
            failCount++;
        }
    }

    if (successCount > 0) {
        showToast(`Successfully uploaded ${successCount} file(s)`, 'success');
        updateProcessQueueCount({
            totalFiles: (window.currentFiles?.length || 0) + successCount,
            processedFiles: window.processedFiles?.size || 0,
            archivedView: isArchivesView,
            message: `${successCount} file${successCount === 1 ? '' : 's'} uploaded and ready to analyze.`
        });
        if (typeof loadLearningFiles === 'function') {
            loadLearningFiles();
        }
    }
    if (failCount > 0) {
        showToast(`Failed to upload ${failCount} file(s)`, 'error');
        updateProcessQueueCount({
            totalFiles: window.currentFiles?.length || 0,
            processedFiles: window.processedFiles?.size || 0,
            archivedView: isArchivesView,
            isError: true,
            message: `${failCount} upload${failCount === 1 ? '' : 's'} failed.`
        });
    }

    // Clear the input so the same files can be selected again
    event.target.value = '';
}

async function uploadOneFile(file) {
    return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = async (e) => {
            try {
                const content = e.target.result;
                const res = await apiCall('/api/upload', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        filename: file.name,
                        content: content,
                        skip_analysis: true // Just save it to learning folder
                    })
                });
                resolve(res && res.success);
            } catch (err) {
                console.error('apiCall error:', err);
                resolve(false);
            }
        };
        reader.onerror = () => {
            console.error('FileReader error');
            resolve(false);
        };
        reader.readAsText(file);
    });
}


async function pollCloudHeartbeat() {
    // Re-schedule first to ensure persistence
    setTimeout(pollCloudHeartbeat, 10000); // Increased frequency for "Live" feel

    if (!currentUser) return;

    try {
        const res = await apiCall('/api/devices', { displayError: false });
        if (res && res.length > 0) {
            deviceTokensCache = res;
            const now = new Date();
            let isOnline = false;
            let activeDevice = null;

            for (const device of res) {
                if (device.last_sync) {
                    const lastSyncTime = new Date(device.last_sync);
                    // If device synced within last 45 seconds, it's online
                    if (Math.abs(now - lastSyncTime) < 45000) {
                        isOnline = true;
                        isCloudConnected = true; // Set cloud flag
                        activeDevice = device;
                        break;
                    }
                }
            }
            if (!isOnline) isCloudConnected = false;
            const headerDevice = activeDevice || res[0] || null;

            const badge = document.getElementById('connectionStatus');
            const text = document.getElementById('connText');
            const connDot = document.getElementById('headerConnDot');
            const detailStatus = document.getElementById('headerDeviceDetailStatus');
            const detailBattery = document.getElementById('headerDeviceDetailBattery');
            const detailSd = document.getElementById('headerDeviceDetailSd');
            const detailFlash = document.getElementById('headerDeviceDetailFlash');
            const detailTrackWrap = document.getElementById('headerDeviceTrackDetailWrap');
            const detailTrack = document.getElementById('headerDeviceDetailTrack');

            // 1. Connection Status & Pulse
            if (badge && text && connDot) {
                if (isOnline) {
                    if (!isDeviceConnected) {
                        showToast('Heartbeat received from device', 'success');
                    }
                    badge.className = 'status-badge online status-pill-button';
                    text.textContent = 'Connected';
                    badge.title = 'RS-Core Connected. Tap for full device details.';
                    isDeviceConnected = true;
                    if (detailStatus) detailStatus.textContent = 'RS-Core Connected';

                    // Pulsing logic: pulse if we got a heartbeat in the last 15 seconds
                    const lastSyncTime = new Date(activeDevice.last_sync);
                    const isRecent = Math.abs(now - lastSyncTime) < 15000;
                    connDot.classList.toggle('pulse', isRecent);
                } else {
                    badge.className = 'status-badge offline status-pill-button';
                    text.textContent = res.length > 0 ? 'Offline' : 'No Device';
                    badge.title = res.length > 0 ? 'RS-Core offline. Tap for last known device details.' : 'No RS-Core detected yet.';
                    connDot.classList.remove('pulse');
                    isDeviceConnected = false;
                    if (detailStatus) detailStatus.textContent = res.length > 0 ? 'RS-Core Offline' : 'No device detected';
                }
            }
            updateDeviceSetupChecklist();

            // 2. Header Telemetry
            const battEl = document.getElementById('headerBattery');
            const storageEl = document.getElementById('headerStorage');
            
            if (headerDevice && isOnline) {
                if (battEl) {
                    battEl.style.display = 'flex';
                    const vbatt = headerDevice.vbatt_sense || 0;
                    const isUsbPowered = vbatt < 1.0;
                    
                    if (isUsbPowered) {
                        document.getElementById('headerVbatt').textContent = `Charge Now`;
                        const pctEl = document.getElementById('headerVbattPct');
                        if (pctEl) pctEl.textContent = ``;
                        battEl.style.color = 'var(--error)';
                        if (detailBattery) detailBattery.textContent = `Charge Now`;
                        const battIcon = document.getElementById('headerBatteryIcon');
                        if (battIcon) battIcon.className = 'fas fa-battery-empty';
                    } else {
                        const pct = calculateBatteryPercentage(vbatt);
                        document.getElementById('headerVbatt').textContent = `${pct}%`;
                        const pctEl = document.getElementById('headerVbattPct');
                        if (pctEl) pctEl.textContent = `${vbatt.toFixed(1)}V`;
                        battEl.style.color = vbatt < 3.6 ? 'var(--error)' : (vbatt < 3.8 ? 'var(--warning)' : 'var(--text-dim)');
                        if (detailBattery) detailBattery.textContent = `${pct}% • ${vbatt.toFixed(1)}V`;
                        const battIcon = document.getElementById('headerBatteryIcon');
                        if (battIcon) {
                            battIcon.className = pct < 20 ? 'fas fa-battery-quarter' : (pct < 60 ? 'fas fa-battery-half' : 'fas fa-battery-full');
                        }
                    }
                }

                if (storageEl) {
                    storageEl.style.display = 'flex';
                    
                    // SD Storage
                    const sdFree = headerDevice.storage_sd_free || 0;
                    const sdTotal = headerDevice.storage_sd_total || 0;
                    const sdBar = document.getElementById('sdBarFill');
                    const sdText = document.getElementById('sdStorageText');
                    const sdShort = document.getElementById('sdStorageShort');
                    
                    if (sdTotal > 0) {
                        const sdUsed = sdTotal - sdFree;
                        const sdPct = Math.round((sdUsed / sdTotal) * 100);
                        if (sdBar) sdBar.style.width = `${sdPct}%`;
                        if (sdText) sdText.textContent = `${(sdUsed/1024).toFixed(1)} / ${(sdTotal/1024).toFixed(1)} GB`;
                        if (sdShort) sdShort.textContent = formatStorageCompact(sdFree, 'SD');
                        document.getElementById('sdStorageGroup').style.opacity = '1';
                        if (detailSd) detailSd.textContent = formatStorageDetail(sdUsed, sdTotal, 'SD');
                    } else {
                        if (sdBar) sdBar.style.width = '0%';
                        if (sdText) sdText.textContent = 'No SD Card';
                        if (sdShort) sdShort.textContent = 'SD --';
                        document.getElementById('sdStorageGroup').style.opacity = '0.5';
                        if (detailSd) detailSd.textContent = 'No SD card detected';
                    }

                    // Internal Flash
                    let fFree = headerDevice.storage_flash_free || 0; // KB
                    let fTotal = headerDevice.storage_flash_total || 0; // KB
                    
                    // Legacy firmware fix: older devices send flash size in bytes, not KB.
                    // If free is larger than 100MB (100,000 KB), it's definitely bytes.
                    if (fFree > 100000) {
                        fFree = Math.round(fFree / 1024);
                    }
                    if (fTotal > 100000) {
                        fTotal = Math.round(fTotal / 1024);
                    }
                    
                    // Fallback for older firmware that doesn't send total (16MB standard)
                    if (fFree > 0 && fTotal === 0) {
                        fTotal = 16384; 
                    }
                    
                    const fBar = document.getElementById('flashBarFill');
                    const fText = document.getElementById('flashStorageText');
                    const fShort = document.getElementById('flashStorageShort');
                    
                    if (fTotal > 0) {
                        const fUsed = fTotal - fFree;
                        const fPct = Math.round((fUsed / fTotal) * 100);
                        if (fBar) fBar.style.width = `${fPct}%`;
                        if (fText) fText.textContent = `${(fUsed/1024).toFixed(1)} / ${(fTotal/1024).toFixed(1)} MB`;
                        if (fShort) fShort.textContent = formatStorageCompact(fFree, 'Flash');
                        if (detailFlash) detailFlash.textContent = formatStorageDetail(fUsed, fTotal, 'Flash');
                    } else {
                        if (fBar) fBar.style.width = '0%';
                        if (fText) fText.textContent = 'Flash --';
                        if (fShort) fShort.textContent = 'Flash --';
                        if (detailFlash) detailFlash.textContent = 'Flash details unavailable';
                    }
                }
                
                // 3. Active Track
                const trackEl = document.getElementById('headerTrack');
                if (trackEl && activeTrackId) {
                    const track = tracks.find(t => t.track_id == activeTrackId);
                    if (track) {
                        trackEl.style.display = 'flex';
                        document.getElementById('headerTrackName').textContent = track.track_name;
                        if (detailTrackWrap) detailTrackWrap.style.display = 'block';
                        if (detailTrack) detailTrack.textContent = track.track_name;
                    } else {
                        trackEl.style.display = 'none';
                        if (detailTrackWrap) detailTrackWrap.style.display = 'none';
                    }
                } else if (trackEl) {
                    trackEl.style.display = 'none';
                    if (detailTrackWrap) detailTrackWrap.style.display = 'none';
                }
            } else {
                if (battEl) battEl.style.display = 'none';
                if (storageEl) storageEl.style.display = 'none';
                if (detailBattery) detailBattery.textContent = '--';
                if (detailSd) detailSd.textContent = '--';
                if (detailFlash) detailFlash.textContent = '--';
                if (detailTrackWrap) detailTrackWrap.style.display = 'none';
            }

            // 3. Global Sync Progress
            const syncPill = document.getElementById('syncStatusPill');
            if (activeDevice && activeDevice.is_syncing && isOnline) {
                if (syncPill) {
                    syncPill.style.display = 'flex';
                    
                    // Use global progress if available, fallback to single file chunk progress
                    let pct = 0;
                    if (activeDevice.sync_global_total && activeDevice.sync_global_total > 0) {
                        const current = activeDevice.sync_global_current || 0;
                        const total = activeDevice.sync_global_total;
                        pct = Math.round((current / total) * 100);
                    } else {
                        const chunk = activeDevice.sync_chunk || 0;
                        const total = activeDevice.sync_total || 1;
                        pct = Math.round((chunk / total) * 100);
                    }
                    
                    const textEl = document.getElementById('syncProgressText');
                    if (textEl) textEl.textContent = `${Math.min(pct, 100)}%`;
                    
                    const filesSpan = document.getElementById('syncProgressFiles');
                    if (filesSpan) {
                        if (activeDevice.sync_total_files > 0) {
                            // File index is 0-based
                            const currentFile = (activeDevice.sync_current_file_index || 0) + 1;
                            filesSpan.textContent = `(${currentFile}/${activeDevice.sync_total_files})`;
                            filesSpan.style.display = 'inline';
                        } else {
                            filesSpan.style.display = 'none';
                        }
                    }
                }
            } else {
                if (syncPill) syncPill.style.display = 'none';
            }

            updateDeviceStatus(
                isOnline,
                isOnline ? 'online' : (res.length > 0 ? 'offline' : 'waiting'),
                isOnline ? headerDevice : null
            );
            updateLastSyncDisplay(headerDevice?.last_sync || null);
            refreshHomeContextBanner();

            requestAnimationFrame(updateResponsiveChromeMetrics);
        } else if (res && Array.isArray(res)) {
            deviceTokensCache = res;
            updateDeviceSetupChecklist();
            isCloudConnected = false;
            isDeviceConnected = false;
            refreshHomeContextBanner();
        }
    } catch (e) {
        console.warn('[Heartbeat] Failed to fetch device status', e);
        updateDeviceStatus(false, 'offline', null);
        isCloudConnected = false;
        isDeviceConnected = false;
        refreshHomeContextBanner();
    }
}

function calculateBatteryPercentage(voltage) {
    if (voltage >= 4.2) return 100;
    if (voltage <= 3.3) return 0;
    
    // Simple LiPo discharge curve approximation
    const curve = [
        { v: 4.2, p: 100 },
        { v: 4.05, p: 90 },
        { v: 3.95, p: 80 },
        { v: 3.85, p: 60 },
        { v: 3.75, p: 40 },
        { v: 3.7, p: 20 },
        { v: 3.6, p: 10 },
        { v: 3.4, p: 5 },
        { v: 3.3, p: 0 }
    ];

    for (let i = 0; i < curve.length - 1; i++) {
        const high = curve[i];
        const low = curve[i + 1];
        if (voltage <= high.v && voltage >= low.v) {
            const rangeV = high.v - low.v;
            const rangeP = high.p - low.p;
            const vOffset = voltage - low.v;
            return Math.round(low.p + (vOffset / rangeV) * rangeP);
        }
    }
    return 0;
}

// Local device connection logic has been removed in favor of Direct-To-Cloud architecture.

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
// DEVICE STATUS & AUTO-SYNC
// ============================================================================

/**
 * Update device status in settings and home sync banner
 */
function updateDeviceStatus(connected, state = 'waiting', device = null) {
    const dot = document.getElementById('deviceStatusDot');
    const text = document.getElementById('deviceStatusText');
    const detailEl = document.getElementById('deviceStatusDetail');
    const banner = document.getElementById('deviceSyncBanner');
    const batteryEl = document.getElementById('deviceStatusBattery');
    const sdEl = document.getElementById('deviceStatusSd');
    const flashEl = document.getElementById('deviceStatusFlash');
    const trackEl = document.getElementById('deviceStatusTrack');
    const uidEl = document.getElementById('deviceStatusUid');
    const syncEl = document.getElementById('deviceStatusSync');

    if (connected && device) {
        if (dot) dot.style.background = 'var(--success)';
        if (text) text.textContent = 'Online';
        if (detailEl) detailEl.textContent = 'Cloud heartbeat received recently.';
        if (banner) {
            banner.style.display = 'block';
            const title = document.getElementById('syncBannerTitle');
            const detail = document.getElementById('syncBannerDetail');
            if (title) title.textContent = 'RS-Core Connected';
            if (detail) detail.textContent = device.is_syncing ? 'Uploading sessions' : 'Auto-sync active';
        }
        if (batteryEl) {
            const vbatt = Number(device.vbatt_sense || 0);
            batteryEl.textContent = vbatt > 0 ? `${calculateBatteryPercentage(vbatt)}% • ${vbatt.toFixed(1)}V` : '--';
        }
        if (sdEl) {
            const total = Number(device.storage_sd_total || 0);
            const free = Number(device.storage_sd_free || 0);
            sdEl.textContent = total > 0 ? formatStorageDetail(total - free, total, 'SD') : 'No SD card';
        }
        if (flashEl) {
            const total = Number(device.storage_flash_total || 0);
            const free = Number(device.storage_flash_free || 0);
            flashEl.textContent = total > 0 ? formatStorageDetail(total - free, total, 'Flash') : 'Flash unavailable';
        }
        if (trackEl) {
            const track = activeTrackId ? tracks.find(t => t.track_id == activeTrackId) : null;
            trackEl.textContent = track?.track_name || 'Not set';
        }
        if (uidEl) uidEl.textContent = device.device_uid || '--';
        if (syncEl) syncEl.textContent = device.is_syncing ? 'Uploading' : 'Idle';
    } else {
        if (dot) dot.style.background = 'var(--error)';
        if (text) text.textContent = state === 'offline' ? 'Offline' : 'Waiting for heartbeat';
        if (detailEl) {
            detailEl.textContent = state === 'offline'
                ? 'A registered RS-Core exists, but no recent heartbeat is available.'
                : 'No RS-Core has checked in yet.';
        }
        if (banner) banner.style.display = 'none';
        if (batteryEl) batteryEl.textContent = '--';
        if (sdEl) sdEl.textContent = '--';
        if (flashEl) flashEl.textContent = '--';
        if (trackEl) {
            const track = activeTrackId ? tracks.find(t => t.track_id == activeTrackId) : null;
            trackEl.textContent = track?.track_name || '--';
        }
        if (uidEl) uidEl.textContent = '--';
        if (syncEl) syncEl.textContent = 'Idle';
    }
}

function updateLastSyncDisplay(lastSyncIso) {
    const el = document.getElementById('lastSyncTime');
    if (!el) return;
    if (lastSyncIso) {
        const d = new Date(lastSyncIso);
        const now = new Date();
        const diff = Math.floor((now - d) / 60000);
        if (diff < 1) el.textContent = 'Just now';
        else if (diff < 60) el.textContent = `${diff} min ago`;
        else if (diff < 1440) el.textContent = `${Math.floor(diff / 60)}h ago`;
        else el.textContent = d.toLocaleDateString();
    } else {
        el.textContent = 'Never';
    }
}


// ============================================================================
// ADMIN USER MANAGEMENT
// ============================================================================

async function loadAdminUsers(page = 1, query = '', tier = '', approval = '') {
    const searchInput = document.getElementById('adminSearchInput');
    const tierFilter = document.getElementById('adminTierFilter');
    const approvalFilter = document.getElementById('adminApprovalFilter');

    if (searchInput && !searchInput.value && readUiState('ui:adminQuery', '')) {
        searchInput.value = readUiState('ui:adminQuery', '');
    }
    if (tierFilter && !tierFilter.value && readUiState('ui:adminTier', '')) {
        tierFilter.value = readUiState('ui:adminTier', '');
    }
    if (approvalFilter && !approvalFilter.value && readUiState('ui:adminApproval', '')) {
        approvalFilter.value = readUiState('ui:adminApproval', '');
    }

    query = query || (searchInput ? searchInput.value : '');
    tier = tier || (tierFilter ? tierFilter.value : '');
    approval = approval || (approvalFilter ? approvalFilter.value : '');
    saveUiState('ui:adminQuery', query);
    saveUiState('ui:adminTier', tier);
    saveUiState('ui:adminApproval', approval);

    try {
        let url = `/api/admin/users?page=${page}&per_page=${adminPerPage}`;
        if (query) url += `&q=${encodeURIComponent(query)}`;
        if (tier) url += `&tier=${tier}`;
        if (approval) url += `&approval=${approval}`;

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

async function loadAdminTrackData() {
    try {
        const [tracksResult, reportsResult, settingsResult] = await Promise.all([
            apiCall('/api/admin/tracks'),
            apiCall('/api/admin/tracks/unmatched'),
            apiCall('/api/admin/settings')
        ]);
        adminTracksData = tracksResult.tracks || [];
        adminUnmatchedTracks = reportsResult.reports || [];
        adminSettings = settingsResult || {};
        const sectorInput = document.getElementById('adminDefaultSectorCount');
        if (sectorInput) sectorInput.value = adminSettings.default_sector_count || '';
        renderAdminTracks();
        renderAdminUnmatchedTracks();
    } catch (error) {
        const tracksEl = document.getElementById('adminTracksList');
        const reportsEl = document.getElementById('adminUnmatchedTracks');
        if (tracksEl) tracksEl.innerHTML = '<p class="help-text">Failed to load global tracks.</p>';
        if (reportsEl) reportsEl.innerHTML = '<p class="help-text">Failed to load unmatched-track queue.</p>';
    }
}

async function saveAdminDefaultSectorCount() {
    const input = document.getElementById('adminDefaultSectorCount');
    const value = Number(input?.value);
    if (!Number.isInteger(value) || value < 1 || value > 16) {
        showToast('Default sector count must be an integer from 1 to 16', 'error');
        return;
    }

    try {
        const result = await apiCall('/api/admin/settings/default-sector-count', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ value })
        });
        adminSettings.default_sector_count = result.default_sector_count;
        if (input) input.value = result.default_sector_count;
        showToast('Default sector count updated', 'success');
    } catch (error) {
        showToast('Failed to update default sector count: ' + error.message, 'error');
    }
}

function renderAdminTracks() {
    const container = document.getElementById('adminTracksList');
    if (!container) return;
    if (!adminTracksData.length) {
        container.innerHTML = '<p class="help-text">No shared tracks uploaded yet.</p>';
        return;
    }

    const escapeJsSingleQuoted = (value) => String(value || '')
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'");

    container.innerHTML = adminTracksData.map(track => {
        const awaitingConfirm = pendingAdminTrackDeleteId === track.track_id;
        return `
        <div class="track-card" style="cursor:default;">
            <img src="${API_BASE}/api/tracks/${track.track_id}/map" alt="${track.track_name}" class="track-map">
            <div class="track-info">
                <div class="card-head-inline">
                    <div class="track-name">${track.track_name}</div>
                    <span class="badge compact-badge">v${track.package_version || 1}</span>
                </div>
                <div class="track-meta">
                    <span><i class="fas fa-hashtag"></i> ${track.track_id}</span>
                    <span><i class="fas fa-draw-polygon"></i> ${track.layout_width || '--'}×${track.layout_height || '--'}</span>
                    <span><i class="fas fa-link"></i> ${track.matched_sessions_count || 0} matched sessions</span>
                </div>
                <div class="track-actions">
                    ${awaitingConfirm
            ? `<button class="btn btn-danger btn-sm" onclick="confirmDeleteAdminTrack(${track.track_id}, '${escapeJsSingleQuoted(track.track_name)}')">
                        <i class="fas fa-exclamation-triangle"></i> Confirm Delete
                    </button>
                    <button class="btn btn-sm" onclick="cancelDeleteAdminTrack()">
                        Cancel
                    </button>`
            : `<button class="btn btn-danger btn-sm" onclick="requestDeleteAdminTrack(${track.track_id})">
                        <i class="fas fa-trash"></i> Delete
                    </button>`}
                </div>
                ${awaitingConfirm ? '<div class="help-text" style="margin-top:0.5rem; color: var(--warning);">Confirm deletion of this shared master track. Matched sessions will remain, but this master layout/package will be removed.</div>' : ''}
            </div>
        </div>
    `;
    }).join('');
}

function renderAdminUnmatchedTracks() {
    const container = document.getElementById('adminUnmatchedTracks');
    if (!container) return;
    if (!adminUnmatchedTracks.length) {
        container.innerHTML = '<p class="help-text">No unmatched fallback tracks waiting for review.</p>';
        return;
    }

    const trackOptions = adminTracksData.map(track => `<option value="${track.track_id}">${track.track_name}</option>`).join('');
    container.innerHTML = adminUnmatchedTracks.map(report => `
        <div class="card" style="margin-bottom:0.75rem;">
            <div style="display:flex; justify-content:space-between; gap:1rem; align-items:flex-start; flex-wrap:wrap;">
                <div>
                    <div style="font-weight:700;">${report.fallback_track_name}</div>
                    <div class="help-text">Fallback track ${report.fallback_track_id} from session ${report.session_id}</div>
                    <div class="help-text">Status: ${report.status}</div>
                </div>
                <div style="display:flex; gap:0.5rem; align-items:center; flex-wrap:wrap;">
                    <select id="resolveTrackSelect${report.id}" class="filter-select" style="min-width:180px;">
                        <option value="">Select shared track</option>
                        ${trackOptions}
                    </select>
                    <button class="btn btn-primary btn-sm" onclick="resolveUnmatchedTrack(${report.id})">Resolve</button>
                    <button class="btn btn-sm" onclick="ignoreUnmatchedTrack(${report.id})">Ignore</button>
                </div>
            </div>
        </div>
    `).join('');
}

async function uploadAdminTrackPackage() {
    const fileInput = document.getElementById('adminTrackPackageFile');
    const trackNameInput = document.getElementById('adminTrackNameInput');
    const trackSlugInput = document.getElementById('adminTrackSlugInput');
    const file = fileInput?.files?.[0];
    if (!file) {
        showToast('Choose a package JSON file first', 'error');
        return;
    }

    try {
        const packageJson = JSON.parse(await file.text());
        await apiCall('/api/admin/tracks/package', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                track_name: trackNameInput?.value?.trim() || undefined,
                slug: trackSlugInput?.value?.trim() || undefined,
                package: packageJson
            })
        });
        showToast('Track package uploaded', 'success');
        if (fileInput) fileInput.value = '';
        if (trackNameInput) trackNameInput.value = '';
        if (trackSlugInput) trackSlugInput.value = '';
        loadAdminTrackData();
        loadTracks();
    } catch (error) {
        showToast('Package upload failed: ' + error.message, 'error');
    }
}

async function resolveUnmatchedTrack(reportId) {
    const select = document.getElementById(`resolveTrackSelect${reportId}`);
    const globalTrackId = select?.value;
    if (!globalTrackId) {
        showToast('Choose a shared track first', 'error');
        return;
    }
    try {
        await apiCall(`/api/admin/tracks/unmatched/${reportId}/resolve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ global_track_id: Number(globalTrackId), status: 'resolved' })
        });
        showToast('Unmatched track resolved', 'success');
        loadAdminTrackData();
    } catch (error) {
        showToast('Resolve failed: ' + error.message, 'error');
    }
}

async function ignoreUnmatchedTrack(reportId) {
    try {
        await apiCall(`/api/admin/tracks/unmatched/${reportId}/resolve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'ignored' })
        });
        showToast('Unmatched track ignored', 'success');
        loadAdminTrackData();
    } catch (error) {
        showToast('Ignore failed: ' + error.message, 'error');
    }
}

function requestDeleteAdminTrack(trackId) {
    pendingAdminTrackDeleteId = trackId;
    renderAdminTracks();
}

function cancelDeleteAdminTrack() {
    pendingAdminTrackDeleteId = null;
    renderAdminTracks();
}

async function confirmDeleteAdminTrack(trackId, trackName) {
    try {
        await apiCall(`/api/admin/tracks/${trackId}`, { method: 'DELETE' });
        pendingAdminTrackDeleteId = null;
        showToast('Shared track deleted. Existing sessions remain.', 'success');
        loadAdminTrackData();
        loadTracks();
    } catch (error) {
        pendingAdminTrackDeleteId = null;
        renderAdminTracks();
        showToast('Delete failed: ' + error.message, 'error');
    }
}

function renderAdminStats(data) {
    const statsEl = document.getElementById('adminStats');
    if (!statsEl) return;

    const pendingHtml = data.pending_count > 0
        ? `<span style="color: var(--warning); cursor: pointer;" onclick="document.getElementById('adminApprovalFilter').value='pending'; filterAdminUsers();">⏳ Pending: <strong>${data.pending_count}</strong></span>`
        : '';

    statsEl.innerHTML = `
        <span>Total Users: <strong>${data.total}</strong></span>
        ${pendingHtml}
        <span>Page <strong>${data.page}</strong> of <strong>${data.pages}</strong></span>
    `;
}

function renderAdminUsersTable(data) {
    const tbody = document.getElementById('adminUsersBody');
    const cards = document.getElementById('adminUsersCards');
    if (!tbody) return;

    if (data.users.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" style="text-align: center; padding: 3rem; color: var(--text-dim);">
                    <i class="fas fa-user-slash" style="font-size: 2rem; margin-bottom: 1rem; opacity: 0.3; display: block;"></i>
                    No users found matching your filters
                </td>
            </tr>
        `;
        if (cards) {
            cards.innerHTML = renderEmptyState(
                '👤',
                'No matching users',
                'Adjust your search or filters and try again.'
            );
        }
        return;
    }

    const rowsHtml = data.users.map(user => {
        const joinDate = user.created_at
            ? new Date(user.created_at).toLocaleDateString()
            : 'N/A';

        const isCurrentUser = currentUser && currentUser.id === user.id;
        const adminBadge = user.is_admin ? '<i class="fas fa-crown admin-badge" title="Admin"></i>' : '';

        const approvalBadge = user.is_approved
            ? '<span class="badge success" style="font-size: 0.65rem; padding: 0.2rem 0.6rem;">APPROVED</span>'
            : '<span class="badge warning" style="font-size: 0.65rem; padding: 0.2rem 0.6rem;">PENDING</span>';

        const approvalActions = !user.is_approved
            ? `<button class="btn btn-sm" onclick="adminApproveUser(${user.id}, true)" style="background: var(--success); color: #000; padding: 0.25rem 0.6rem; font-size: 0.75rem;" title="Approve User">
                    <i class="fas fa-check"></i> Approve
               </button>`
            : `<button class="btn btn-sm" onclick="adminApproveUser(${user.id}, false)" style="background: var(--error); color: #fff; padding: 0.25rem 0.6rem; font-size: 0.75rem;" title="Revoke Approval">
                    <i class="fas fa-ban"></i>
               </button>`;

        return `
            <tr>
                <td style="color: var(--text-dim); font-family: monospace;">#${user.id}</td>
                <td>
                    <div class="admin-user-info">
                        <span class="admin-user-name">${user.name || 'Unnamed Rider'}${adminBadge}</span>
                        <span class="admin-user-email">${user.email}</span>
                    </div>
                </td>
                <td style="text-align: center;">${approvalBadge}</td>
                <td>
                    <span class="tier-badge ${user.subscription_tier}">
                        ${user.subscription_tier}
                    </span>
                </td>
                <td style="text-align: center; font-weight: 700;">${user.session_count || 0}</td>
                <td>${joinDate}</td>
                <td>
                    <div class="admin-actions">
                        ${approvalActions}
                        <select onchange="adminSetUserTier(${user.id}, this.value)" class="filter-select" style="min-width: 100px; padding: 0.35rem; font-size: 0.8rem;">
                            <option value="free" ${user.subscription_tier === 'free' ? 'selected' : ''}>Free</option>
                            <option value="pro" ${user.subscription_tier === 'pro' ? 'selected' : ''}>Pro</option>
                            <option value="team" ${user.subscription_tier === 'team' ? 'selected' : ''}>Team</option>
                        </select>
                        ${(currentUser && currentUser.id === 1 && user.id !== 1) ? `
                            <button class="btn-icon" onclick="adminToggleAdmin(${user.id}, ${!user.is_admin})" title="${user.is_admin ? 'Revoke Admin' : 'Grant Admin'}">
                                <i class="fas ${user.is_admin ? 'fa-user-minus' : 'fa-user-shield'}"></i>
                            </button>
                        ` : ''}
                    </div>
                </td>
            </tr>
        `;
    }).join('');

    tbody.innerHTML = rowsHtml;

    if (cards) {
        cards.innerHTML = data.users.map(user => {
            const joinDate = user.created_at
                ? new Date(user.created_at).toLocaleDateString()
                : 'N/A';

            const approvalBadge = user.is_approved
                ? '<span class="badge success compact-badge">Approved</span>'
                : '<span class="badge warning compact-badge">Pending</span>';

            return `
                <div class="admin-user-card">
                    <div class="card-head-inline">
                        <div>
                            <div class="admin-user-name">${user.name || 'Unnamed Rider'}</div>
                            <div class="admin-user-email">${user.email}</div>
                        </div>
                        ${approvalBadge}
                    </div>
                    <div class="admin-user-meta">
                        <span><strong>ID:</strong> #${user.id}</span>
                        <span><strong>Tier:</strong> ${user.subscription_tier}</span>
                        <span><strong>Sessions:</strong> ${user.session_count || 0}</span>
                        <span><strong>Joined:</strong> ${joinDate}</span>
                    </div>
                    <div class="admin-actions">
                        <select onchange="adminSetUserTier(${user.id}, this.value)" class="filter-select admin-tier-select">
                            <option value="free" ${user.subscription_tier === 'free' ? 'selected' : ''}>Free</option>
                            <option value="pro" ${user.subscription_tier === 'pro' ? 'selected' : ''}>Pro</option>
                            <option value="team" ${user.subscription_tier === 'team' ? 'selected' : ''}>Team</option>
                        </select>
                        ${!user.is_approved
                            ? `<button class="btn btn-sm" onclick="adminApproveUser(${user.id}, true)" style="background: var(--success); color: #000;"><i class="fas fa-check"></i> Approve</button>`
                            : `<button class="btn btn-sm secondary" onclick="adminApproveUser(${user.id}, false)"><i class="fas fa-ban"></i> Revoke</button>`}
                    </div>
                </div>
            `;
        }).join('');
    }
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
    html += `<button onclick="loadAdminUsers(${data.page - 1})" ${data.page <= 1 ? 'disabled' : ''}><i class="fas fa-chevron-left"></i></button>`;

    // Page numbers (show max 5)
    const startPage = Math.max(1, data.page - 2);
    const endPage = Math.min(data.pages, data.page + 2);

    if (startPage > 1) html += '<span style="color: var(--text-dim)">...</span>';

    for (let i = startPage; i <= endPage; i++) {
        html += `<button onclick="loadAdminUsers(${i})" class="${i === data.page ? 'active' : ''}">${i}</button>`;
    }

    if (endPage < data.pages) html += '<span style="color: var(--text-dim)">...</span>';

    // Next button
    html += `<button onclick="loadAdminUsers(${data.page + 1})" ${data.page >= data.pages ? 'disabled' : ''}><i class="fas fa-chevron-right"></i></button>`;

    paginationEl.innerHTML = html;
}

async function adminSetUserTier(userId, newTier) {
    const confirmMsg = `Change user ${userId} tier to ${newTier.toUpperCase()}?`;
    if (!confirm(confirmMsg)) {
        loadAdminUsers(adminCurrentPage);
        return;
    }

    try {
        const result = await apiCall(`/api/admin/users/${userId}/tier`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tier: newTier })
        });

        if (result && result.success) {
            showToast(`User ${userId} updated to ${newTier}`, 'success');

            if (currentUser && currentUser.id === userId) {
                await checkAuth();
            }

            loadAdminUsers(adminCurrentPage);
        }
    } catch (e) {
        showToast('Failed to update tier: ' + e.message, 'error');
        loadAdminUsers(adminCurrentPage);
    }
}

async function adminToggleAdmin(userId, isAdmin) {
    const action = isAdmin ? 'GRANT' : 'REVOKE';
    if (!confirm(`${action} admin privileges for user ${userId}?`)) return;

    try {
        const result = await apiCall(`/api/admin/users/${userId}/admin`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_admin: isAdmin })
        });

        if (result && result.success) {
            showToast(`Admin privileges ${isAdmin ? 'granted' : 'revoked'} for user ${userId}`, 'success');
            loadAdminUsers(adminCurrentPage);
        }
    } catch (e) {
        showToast('Failed to toggle admin: ' + e.message, 'error');
    }
}

async function adminApproveUser(userId, approved) {
    const action = approved ? 'APPROVE' : 'REJECT';
    if (!confirm(`${action} user #${userId}?`)) return;

    try {
        const result = await apiCall(`/api/admin/users/${userId}/approve`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ approved: approved })
        });

        if (result && result.success) {
            showToast(`User #${userId} ${approved ? 'approved' : 'rejected'}`, 'success');
            loadAdminUsers(adminCurrentPage);
        }
    } catch (e) {
        showToast('Failed to update approval: ' + e.message, 'error');
    }
}

function searchAdminUsers() {
    const query = document.getElementById('adminSearchInput').value;
    loadAdminUsers(1, query);
}

function filterAdminUsers() {
    const tier = document.getElementById('adminTierFilter').value;
    const approval = document.getElementById('adminApprovalFilter') ? document.getElementById('adminApprovalFilter').value : '';
    const query = document.getElementById('adminSearchInput').value;
    loadAdminUsers(1, query, tier, approval);
}

// === SCROLL REVEAL ANIMATION ===
(function initScrollReveal() {
    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry, i) => {
            if (entry.isIntersecting) {
                setTimeout(() => entry.target.classList.add('visible'), i * 100);
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.15 });

    document.querySelectorAll('[data-animate]').forEach(el => observer.observe(el));
})();
