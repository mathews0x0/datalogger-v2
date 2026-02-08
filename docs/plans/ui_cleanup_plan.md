# UI Cleanup Plan: Session Details View

**Project:** Racesense Companion App  
**Date:** 2026-02-08  
**Author:** Strategic Architect (Opus)  
**Status:** Ready for Implementation

---

## 1. Problem Statement

The Session Details view (`viewSession` function, line ~2414 in `app.js`) is cluttered and overwhelming. Users report it as "super cluttered" and a "mess" with too much information presented at once.

### Current Issues
1. **All sections render immediately** — No progressive disclosure
2. **Dense information hierarchy** — Session summary, weather, notes, diagnostics, sector charts, lap table, timeline, and annotations all visible at once
3. **No clear visual separation** between primary/secondary information
4. **Vertical scroll is excessive** — Users must scroll through ~6-8 cards to see everything
5. **Action buttons are scattered** — Header has 6-8 buttons, lap rows have 2-3 each

---

## 2. New Layout Design

### 2.1 Information Hierarchy

**TIER 1 — Always Visible (Hero Section)**
- Session name + date
- Session Best lap time (large, prominent)
- Track name
- Total laps count
- Primary action: ▶ Live Playback

**TIER 2 — Collapsible Sections (Default Closed)**
| Section | Default State | Reason |
|---------|--------------|--------|
| Quick Stats Cards | **OPEN** | Core metrics, compact |
| Lap Analysis Table | **OPEN** | Primary data, always needed |
| Session Notes | **CLOSED** | Optional context |
| Weather & Conditions | **CLOSED** | Rarely checked |
| Session Diagnostics | **CLOSED** | Advanced analysis |
| Sector Comparison Chart | **CLOSED** | Visual analysis, optional |
| Session Trend Timeline | **CLOSED** | Progress visualization |
| Coach Annotations | **CLOSED** | Optional notes |

**TIER 3 — Secondary Actions (Collapsible "More Actions" Menu)**
- Share, Export ZIP, Print Report, Tag to Trackday, Delete
- Public toggle moves here too

### 2.2 Visual Mockup (ASCII)

```
┌──────────────────────────────────────────────────────────────────┐
│ ← Back                                    [▶ Live Playback] [⋮]  │ ← "⋮" = More Actions menu
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  SESSION NAME                                      ✎ Edit        │
│  Buddh International Circuit · 08 Feb 2026 14:30                │
│  ──────────────────────────────────────────────────────────────  │
│                                                                  │
│   ┌─────────────┐                                               │
│   │  1:52.341   │  ← SESSION BEST (large, green, prominent)     │
│   │  Session PB │                                               │
│   └─────────────┘                                               │
│                                                                  │
│   12 Laps · Consistency: ±0.82s · IMU: HIGH                     │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│ ▼ Quick Stats                                              [−]  │
│   ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐                  │
│   │ Laps │ │ Best │ │ Theo │ │  PB  │ │Consist│                 │
│   └──────┘ └──────┘ └──────┘ └──────┘ └──────┘                  │
├──────────────────────────────────────────────────────────────────┤
│ ▼ Lap Analysis                                             [−]  │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │ Lap │ Time     │ Delta  │ S1     │ S2     │ S3     │     │  │
│   │ 1   │ 1:54.123 │ +1.782 │ 45.2   │ 38.1   │ 30.8   │ ... │  │
│   │ 2   │ 1:53.456 │ +1.115 │ 44.8   │ 37.9   │ 30.7   │ ... │  │
│   │ 3   │ 1:52.341 │  0.000 │ 44.1   │ 37.5   │ 30.7   │ ★   │  │
│   └──────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────────┤
│ ▶ Session Notes                                            [+]  │  ← Collapsed
├──────────────────────────────────────────────────────────────────┤
│ ▶ Weather & Conditions                                     [+]  │  ← Collapsed
├──────────────────────────────────────────────────────────────────┤
│ ▶ Session Diagnostics                                      [+]  │  ← Collapsed
├──────────────────────────────────────────────────────────────────┤
│ ▶ Sector Comparison                                        [+]  │  ← Collapsed
├──────────────────────────────────────────────────────────────────┤
│ ▶ Session Trend                                            [+]  │  ← Collapsed
├──────────────────────────────────────────────────────────────────┤
│ ▶ Coach Annotations (3)                                    [+]  │  ← Shows count
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Implementation Instructions

### 3.1 CSS Changes (`styles.css`)

Add these new classes at the end of the file:

```css
/* ============================================================================
   COLLAPSIBLE SECTIONS (Phase: UI Cleanup)
   ============================================================================ */

.collapsible-section {
  margin-bottom: 0.75rem;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--glass);
  backdrop-filter: blur(10px);
}

.collapsible-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.25rem;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s ease;
}

.collapsible-header:hover {
  background: rgba(255, 255, 255, 0.03);
}

.collapsible-header h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.collapsible-header .toggle-icon {
  font-size: 0.8rem;
  color: var(--text-dim);
  transition: transform 0.25s ease;
}

.collapsible-section.open .collapsible-header .toggle-icon {
  transform: rotate(90deg);
}

.collapsible-body {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.35s cubic-bezier(0.4, 0, 0.2, 1), 
              padding 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  padding: 0 1.25rem;
}

.collapsible-section.open .collapsible-body {
  max-height: 2000px; /* Large enough for any content */
  padding: 0 1.25rem 1.25rem 1.25rem;
}

/* Hero Session Header */
.session-hero {
  background: linear-gradient(135deg, var(--surface) 0%, rgba(255, 107, 53, 0.08) 100%);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.session-hero-title {
  font-size: 1.4rem;
  font-weight: 700;
  margin-bottom: 0.25rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.session-hero-meta {
  font-size: 0.9rem;
  color: var(--text-dim);
  margin-bottom: 1rem;
}

.session-hero-best {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  background: rgba(0, 210, 106, 0.1);
  border: 2px solid var(--success);
  border-radius: 12px;
  padding: 0.75rem 1.5rem;
  margin: 0.5rem 0;
}

.session-hero-best .time {
  font-size: 2rem;
  font-weight: 800;
  font-family: 'JetBrains Mono', monospace;
  color: var(--success);
  line-height: 1;
}

.session-hero-best .label {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--success);
  opacity: 0.8;
  margin-top: 0.25rem;
}

.session-hero-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 1rem;
}

/* More Actions Dropdown */
.actions-dropdown {
  position: relative;
  display: inline-block;
}

.actions-dropdown-btn {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 0.5rem 0.75rem;
  border-radius: 8px;
  cursor: pointer;
  font-size: 1.2rem;
  transition: all 0.2s;
}

.actions-dropdown-btn:hover {
  background: rgba(255, 255, 255, 0.1);
}

.actions-dropdown-menu {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 0.5rem;
  background: var(--surface-opaque);
  border: 1px solid var(--glass-border);
  border-radius: 8px;
  min-width: 200px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
  z-index: 100;
  display: none;
  overflow: hidden;
}

.actions-dropdown.open .actions-dropdown-menu {
  display: block;
  animation: dropdownEnter 0.2s ease;
}

@keyframes dropdownEnter {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
}

.actions-dropdown-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  color: var(--text);
  cursor: pointer;
  transition: background 0.15s;
  border: none;
  background: none;
  width: 100%;
  text-align: left;
  font-size: 0.9rem;
}

.actions-dropdown-item:hover {
  background: rgba(255, 255, 255, 0.05);
}

.actions-dropdown-item.danger {
  color: var(--error);
}

.actions-dropdown-divider {
  height: 1px;
  background: var(--border);
  margin: 0.25rem 0;
}

/* Section badge (for counts) */
.section-badge {
  font-size: 0.75rem;
  background: var(--primary);
  color: #000;
  padding: 0.15rem 0.5rem;
  border-radius: 10px;
  font-weight: 700;
  margin-left: 0.5rem;
}
```

---

### 3.2 JavaScript Changes (`app.js`)

#### 3.2.1 Add Collapsible Toggle Function

Add this utility function near the top of `app.js` (after the helper functions):

```javascript
// ============================================================================
// COLLAPSIBLE SECTIONS UTILITY
// ============================================================================

function toggleCollapsible(sectionId) {
    const section = document.getElementById(sectionId);
    if (section) {
        section.classList.toggle('open');
        // Persist state to localStorage
        const state = section.classList.contains('open');
        localStorage.setItem(`collapsible_${sectionId}`, state);
    }
}

function initCollapsibleState(sectionId, defaultOpen = false) {
    const stored = localStorage.getItem(`collapsible_${sectionId}`);
    return stored !== null ? stored === 'true' : defaultOpen;
}

function toggleActionsDropdown(event) {
    event.stopPropagation();
    const dropdown = document.getElementById('sessionActionsDropdown');
    if (dropdown) {
        dropdown.classList.toggle('open');
    }
}

// Close dropdown when clicking outside
document.addEventListener('click', (e) => {
    const dropdown = document.getElementById('sessionActionsDropdown');
    if (dropdown && !dropdown.contains(e.target)) {
        dropdown.classList.remove('open');
    }
});
```

#### 3.2.2 Refactor `viewSession` Function

Replace the `container.innerHTML` assignment (starting around line 2489) with this new structure:

```javascript
// Helper to generate collapsible section wrapper
function wrapCollapsible(id, title, icon, content, defaultOpen = false, badge = '') {
    const openClass = initCollapsibleState(id, defaultOpen) ? 'open' : '';
    const badgeHTML = badge ? `<span class="section-badge">${badge}</span>` : '';
    return `
        <div class="collapsible-section ${openClass}" id="${id}">
            <div class="collapsible-header" onclick="toggleCollapsible('${id}')">
                <h3>
                    <span style="color: var(--primary);">${icon}</span>
                    ${title}${badgeHTML}
                </h3>
                <span class="toggle-icon">▶</span>
            </div>
            <div class="collapsible-body">
                ${content}
            </div>
        </div>
    `;
}

// Then in viewSession, replace the container.innerHTML with:
container.innerHTML = `
    ${isShared ? `
        <div style="background: var(--bg-secondary); padding: 1rem; border-radius: 8px; margin-bottom: 1.5rem; display: flex; justify-content: space-between; align-items: center; border: 1px solid var(--primary);">
            <div>
                <span style="color: var(--primary); font-weight: bold; cursor: pointer;" onclick="showUserProfile(${session.user_id})">Rider: ${session.owner_name || 'Anonymous'}</span>
                <p style="margin: 0.25rem 0 0 0; font-size: 0.8rem; color: var(--text-dim);">You are viewing a shared session.</p>
            </div>
            ${!currentUser ? `
                <button class="btn btn-primary btn-sm" onclick="showAuthModal()">Sign up to track your own laps</button>
            ` : ''}
        </div>
    ` : ''}

    <!-- HERO SECTION -->
    <div class="session-hero">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
            <div>
                <div class="session-hero-title">
                    ${session.meta.session_name || session.track.track_name + ' Session'}
                    ${!isShared ? `<button class="btn-icon no-print" onclick="promptRenameSession('${session.meta.session_id}', '${session.meta.session_name || ''}')" title="Rename Session">✎</button>` : ''}
                </div>
                <div class="session-hero-meta">
                    ${session.track.track_name} · ${formatDateTime(session.meta.start_time)}
                </div>
                <div class="session-hero-best">
                    <span class="time">${formatTime(session.summary.best_lap_time)}</span>
                    <span class="label">Session Best</span>
                </div>
                <div class="session-hero-badges">
                    <div class="consistency-badge" title="Total Laps">
                        <strong>${session.summary.total_laps}</strong> Laps
                    </div>
                    <div class="consistency-badge" title="Standard Deviation of valid laps">
                        Consistency: <strong>±${consistency.toFixed(2)}s</strong>
                    </div>
                    ${calibBadge}
                    ${allTimeBest && session.summary.best_lap_time <= allTimeBest ? '<div style="color: #4CAF50; font-size: 0.8rem; font-weight: 700;">🏆 NEW PB!</div>' : ''}
                </div>
            </div>
            <div style="display: flex; gap: 0.5rem; align-items: flex-start;">
                <button class="btn btn-primary btn-sm no-print" onclick="openPlayback('${session.meta.session_id}', ${isShared ? `'${shareToken}'` : 'null'})">▶ Live Playback</button>
                ${!isShared ? `
                    <div class="actions-dropdown no-print" id="sessionActionsDropdown">
                        <button class="actions-dropdown-btn" onclick="toggleActionsDropdown(event)" title="More Actions">⋮</button>
                        <div class="actions-dropdown-menu">
                            <div class="actions-dropdown-item" style="padding: 0.5rem 1rem; display: flex; justify-content: space-between; align-items: center;">
                                <span>Public</span>
                                <label class="toggle-switch" style="transform: scale(0.8);">
                                    <input type="checkbox" id="privacyToggle" ${session.is_public ? 'checked' : ''} onchange="togglePrivacy('${session.meta.session_id}', this.checked)">
                                    <span class="toggle-slider"></span>
                                </label>
                            </div>
                            <div class="actions-dropdown-divider"></div>
                            <button class="actions-dropdown-item" onclick="shareSession('${session.meta.session_id}')"><i class="fas fa-share-alt"></i> Share</button>
                            <button class="actions-dropdown-item" onclick="showTagToTrackdayModal('${session.meta.session_id}')">🏷️ Tag to Trackday</button>
                            <button class="actions-dropdown-item" 
                                    ${(!currentUser || currentUser.subscription_tier === 'free') ? 'disabled title="Upgrade to Pro"' : ''}
                                    onclick="exportSession('${session.meta.session_id}')">
                                <i class="fas fa-file-export"></i> Export ZIP ${(!currentUser || currentUser.subscription_tier === 'free') ? '🔒' : ''}
                            </button>
                            <button class="actions-dropdown-item" onclick="window.print()">🖨️ Print Report</button>
                            <div class="actions-dropdown-divider"></div>
                            <button class="actions-dropdown-item danger" onclick="deleteSession('${session.meta.session_id}')">🗑️ Delete Session</button>
                        </div>
                    </div>
                ` : ''}
            </div>
        </div>
    </div>

    <!-- COLLAPSIBLE: QUICK STATS -->
    ${wrapCollapsible('section-quick-stats', 'Quick Stats', '📊', `
        <div class="quick-stats" style="margin: 0;">
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
                    <div class="stat-value" style="color: var(--success);">${formatTime(session.summary.best_lap_time)}</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon" style="background: rgba(0, 78, 137, 0.1); color: var(--secondary);"><i class="fas fa-magic"></i></div>
                <div class="stat-info">
                    <div class="stat-label">Theo. Best</div>
                    <div class="stat-value">${formatTime(session.references.theoretical_best_reference)}</div>
                </div>
            </div>
            ${allTimeBest ? `
            <div class="stat-card">
                <div class="stat-icon" style="background: rgba(156, 39, 176, 0.1); color: #9c27b0;"><i class="fas fa-crown"></i></div>
                <div class="stat-info">
                    <div class="stat-label">All-Time PB</div>
                    <div class="stat-value" style="color: #9c27b0;">${formatTime(allTimeBest)}</div>
                </div>
            </div>
            ` : ''}
            <div class="stat-card">
                <div class="stat-icon" style="background: ${session.analysis?.diagnostics?.consistency_score > 80 ? 'rgba(76, 175, 80, 0.1)' : 'rgba(255, 193, 7, 0.1)'}; color: ${session.analysis?.diagnostics?.consistency_score > 80 ? '#4CAF50' : '#FFC107'};"><i class="fas fa-chart-line"></i></div>
                <div class="stat-info">
                    <div class="stat-label">Consistency</div>
                    <div class="stat-value">${session.analysis?.diagnostics?.consistency_score || '--'}%</div>
                </div>
            </div>
        </div>
    `, true)}

    <!-- COLLAPSIBLE: LAP ANALYSIS -->
    ${wrapCollapsible('section-lap-analysis', 'Lap Analysis', '📊', `
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
                                <td class="lap-number">${lap.lap_number}</td>
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
                        `;
                    }).join('')}
                </tbody>
            </table>
        </div>
        <div id="comparisonContainer"></div>
    `, true)}

    <!-- COLLAPSIBLE: SESSION NOTES -->
    ${wrapCollapsible('section-notes', 'Session Notes', '📝', `
        <textarea 
            id="sessionNotes" 
            ${isShared ? 'readonly' : ''}
            placeholder="${isShared ? 'No notes available.' : 'Add notes about this session (e.g., tire pressure, setup changes, conditions)...'}"
            style="width: 100%; min-height: 100px; background: var(--surface-light); border: 1px solid var(--border); border-radius: 6px; padding: 0.75rem; color: var(--text); resize: vertical; font-family: inherit;"
            onblur="saveSessionNotes('${session.meta.session_id}')"
        >${session.mode?.notes || ''}</textarea>
    `, false)}

    <!-- COLLAPSIBLE: WEATHER & CONDITIONS -->
    ${wrapCollapsible('section-weather', 'Weather & Conditions', '🌡️', `
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem;">
            <div style="display: flex; align-items: center; gap: 0.75rem;">
                <span style="font-size: 1.5rem;">🌡️</span>
                <div>
                    <div style="font-size: 0.75rem; color: var(--text-dim); text-transform: uppercase;">Track Temp</div>
                    <div style="font-weight: 600;">${session.environment?.track_temperature ? session.environment.track_temperature + '°C' : '--'}</div>
                </div>
            </div>
            <div style="display: flex; align-items: center; gap: 0.75rem;">
                <span style="font-size: 1.5rem;">☁️</span>
                <div>
                    <div style="font-size: 0.75rem; color: var(--text-dim); text-transform: uppercase;">Ambient</div>
                    <div style="font-weight: 600;">${session.environment?.ambient_temperature ? session.environment.ambient_temperature + '°C' : '--'}</div>
                </div>
            </div>
            <div style="display: flex; align-items: center; gap: 0.75rem;">
                <span style="font-size: 1.5rem;">📡</span>
                <div>
                    <div style="font-size: 0.75rem; color: var(--text-dim); text-transform: uppercase;">GPS Quality</div>
                    <div style="font-weight: 600;">${session.environment?.gps_quality_summary?.fix_dropouts === 0 ? '✓ Excellent' : session.environment?.gps_quality_summary?.fix_dropouts + ' dropouts'}</div>
                </div>
            </div>
            <div style="display: flex; align-items: center; gap: 0.75rem;">
                <span style="font-size: 1.5rem;">⏱️</span>
                <div>
                    <div style="font-size: 0.75rem; color: var(--text-dim); text-transform: uppercase;">Duration</div>
                    <div style="font-weight: 600;">${Math.floor(session.meta.duration_sec / 60)}m ${Math.floor(session.meta.duration_sec % 60)}s</div>
                </div>
            </div>
        </div>
    `, false)}

    <!-- COLLAPSIBLE: SESSION DIAGNOSTICS -->
    ${session.analysis?.diagnostics ? wrapCollapsible('section-diagnostics', 'Session Diagnostics', '🎯', generateDiagnosticsContent(session), false) : ''}

    <!-- COLLAPSIBLE: SECTOR COMPARISON -->
    ${wrapCollapsible('section-sectors', 'Sector Comparison', '📈', generateSectorComparisonContent(session.laps, sectorCount, sectorBests), false)}

    <!-- COLLAPSIBLE: SESSION TREND -->
    ${wrapCollapsible('section-trend', 'Session Trend', '📉', generateTimelineContent(session.laps), false)}

    <!-- COLLAPSIBLE: COACH ANNOTATIONS -->
    ${wrapCollapsible('section-annotations', 'Coach Annotations', '📝', `
        <div style="display: flex; justify-content: flex-end; margin-bottom: 1rem;">
            <button class="btn btn-primary btn-sm" onclick="showAddAnnotationModalFromDetail('${session.meta.session_id}')">Add Note</button>
        </div>
        <div id="detailAnnotationsList">
            <div class="loading">Loading notes...</div>
        </div>
    `, false)}
`;
```

#### 3.2.3 New Content Generator Functions

Replace the original `generateDiagnosticsPanelFixed`, `generateSectorComparisonChart`, and `generateTimelineSVG` functions with versions that return just the content (without the wrapping card):

```javascript
// New: Returns just the inner content for the diagnostics section
function generateDiagnosticsContent(session) {
    if (!session.analysis || !session.analysis.diagnostics) return '<p class="help-text">No diagnostics available.</p>';
    const d = session.analysis.diagnostics;
    if (d.error) return '<p class="help-text">Diagnostics error.</p>';

    let scoreColor = '#4CAF50';
    if (d.consistency_score < 90) scoreColor = '#FFC107';
    if (d.consistency_score < 75) scoreColor = '#F44336';

    const hotspots = d.variance_hotspots || [];
    const hotspotHTML = hotspots.length > 0 ? hotspots.map(h => `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0.75rem; background: rgba(255, 193, 7, 0.08); border-radius: 6px; border-left: 3px solid #ffc107;">
            <span style="font-weight: 600;">${h.sector_label}</span>
            <span style="font-family: monospace; color: #ffc107; font-size: 0.85rem;">CV: ${h.cv_percent}%</span>
        </div>
    `).join('') : '<div class="help-text" style="text-align: center; padding: 1rem;">✓ No significant variance detected. Good consistency!</div>';

    return `
        <div style="display: grid; grid-template-columns: auto 1fr; gap: 2rem; align-items: start;">
            <div style="text-align: center; padding: 1rem; background: ${scoreColor}10; border-radius: 8px; min-width: 120px;">
                <div style="font-size: 2.5em; font-weight: bold; color: ${scoreColor}; line-height: 1;">
                    ${d.consistency_score !== null ? d.consistency_score : '--'}
                </div>
                <div style="font-size: 0.8em; opacity: 0.7; margin-top: 0.25rem;">Consistency</div>
            </div>
            <div>
                <h4 style="margin: 0 0 0.75rem 0; font-size: 0.85em; text-transform: uppercase; color: var(--text-secondary); letter-spacing: 0.5px;">Variance Hotspots</h4>
                <div style="display: flex; flex-direction: column; gap: 0.5rem;">
                    ${hotspotHTML}
                </div>
            </div>
        </div>
    `;
}

// New: Returns just the inner content for sector comparison
function generateSectorComparisonContent(laps, sectorCount, sectorBests) {
    if (!laps || laps.length < 2) return '<p class="help-text">Need at least 2 laps for comparison.</p>';
    const validLaps = laps.filter(l => l.valid && l.lap_time > 0).slice(0, 10);
    if (validLaps.length === 0) return '<p class="help-text">No valid laps for comparison.</p>';

    // ... (keep the existing SVG generation logic from generateSectorComparisonChart)
    // Return just the <svg> without the card wrapper
    // Full implementation omitted for brevity - copy from original and remove card wrapper
}

// New: Returns just the inner content for timeline
function generateTimelineContent(laps) {
    const validLaps = laps.filter(l => l.valid && l.lap_time > 0);
    if (validLaps.length < 2) return '<p class="help-text">Need at least 2 valid laps for trend analysis.</p>';
    
    // ... (keep the existing SVG generation logic from generateTimelineSVG)
    // Return just the <svg> without the card wrapper
    // Full implementation omitted for brevity - copy from original and remove div wrapper
}
```

---

## 4. Verification Checklist

The implementation model **MUST** verify all items before marking complete:

### Functional Checks
- [ ] **Hero section displays correctly** — Session name, best time prominent, badges visible
- [ ] **Collapsible sections work** — Click header toggles open/close
- [ ] **Animation is smooth** — CSS transition on `max-height` and `padding`
- [ ] **State persists** — Reloading page retains collapsed/expanded state via localStorage
- [ ] **Quick Stats section defaults OPEN**
- [ ] **Lap Analysis section defaults OPEN**
- [ ] **All other sections default CLOSED**
- [ ] **More Actions dropdown works** — Click ⋮ opens menu, click outside closes it
- [ ] **All actions still functional** — Share, Export, Print, Delete, Playback all work
- [ ] **Public toggle works in dropdown**

### Visual Checks
- [ ] **Hero section has gradient background** (`rgba(255, 107, 53, 0.08)`)
- [ ] **Session Best time is large and green** (`2rem`, `var(--success)`)
- [ ] **Collapsed sections show `▶` icon**
- [ ] **Expanded sections rotate icon to `▶` (rotated 90°)**
- [ ] **No visual glitches on mobile** (responsive layout)

### Edge Cases
- [ ] **Shared session view works** — No more actions dropdown, read-only notes
- [ ] **Empty annotations handled** — Shows "Loading..." then "No notes" if empty
- [ ] **Session without diagnostics** — Diagnostics section not rendered
- [ ] **Session with 0-1 laps** — Trend/Sector sections show "Need at least 2 laps"

### Regression
- [ ] **Lap row click still opens lap detail**
- [ ] **Annotations load correctly**
- [ ] **Print styles still work** (collapsible sections expand for print)

---

## 5. Print Styles Addendum

Add to `@media print` section in `styles.css`:

```css
@media print {
  /* Expand all collapsible sections for print */
  .collapsible-section .collapsible-body {
    max-height: none !important;
    padding: 1rem 1.25rem !important;
  }
  
  .collapsible-header .toggle-icon {
    display: none;
  }
  
  .actions-dropdown,
  .session-hero-best {
    print-color-adjust: exact;
    -webkit-print-color-adjust: exact;
  }
}
```

---

## 6. Implementation Notes for Model

**Target Model:** Gemini 3 Flash / GPT OSS

1. **Start with CSS** — Add all new classes first
2. **Add utility functions** — `toggleCollapsible`, `wrapCollapsible`, etc.
3. **Refactor viewSession** — Replace the innerHTML assignment
4. **Create content generators** — Modify existing generator functions
5. **Test incrementally** — After each step, verify in browser

**Estimated LOC changes:**
- `styles.css`: +120 lines
- `app.js`: +80 lines (net, after removing card wrappers from generators)

---

**Planning phase complete. Ready for implementation.**
