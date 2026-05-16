import { enrichSessionWithHermite, parseSessionCsv, processors, serializeSessionCsv } from "./processor.js";

const el = {
  csvFile: document.getElementById("csvFile"),
  csvFileName: document.getElementById("csvFileName"),
  tuningTabBtn: document.getElementById("tuningTabBtn"),
  hermiteTabBtn: document.getElementById("hermiteTabBtn"),
  tuningPane: document.getElementById("tuningPane"),
  hermitePane: document.getElementById("hermitePane"),
  algorithmSelect: document.getElementById("algorithmSelect"),
  paramFields: document.getElementById("paramFields"),
  liveTuningMeta: document.getElementById("liveTuningMeta"),
  processBtn: document.getElementById("processBtn"),
  resetParamsBtn: document.getElementById("resetParamsBtn"),
  loadDemoBtn: document.getElementById("loadDemoBtn"),
  hermiteFactor: document.getElementById("hermiteFactor"),
  processHermiteBtn: document.getElementById("processHermiteBtn"),
  reloadOriginalBtn: document.getElementById("reloadOriginalBtn"),
  sessionDatasetMeta: document.getElementById("sessionDatasetMeta"),
  profileSelect: document.getElementById("profileSelect"),
  profileName: document.getElementById("profileName"),
  saveProfileBtn: document.getElementById("saveProfileBtn"),
  loadProfileBtn: document.getElementById("loadProfileBtn"),
  deleteProfileBtn: document.getElementById("deleteProfileBtn"),
  lapSelect: document.getElementById("lapSelect"),
  graphZoom: document.getElementById("graphZoom"),
  graphZoomValue: document.getElementById("graphZoomValue"),
  showGpsSeries: document.getElementById("showGpsSeries"),
  showImuSeries: document.getElementById("showImuSeries"),
  seekBackBtn: document.getElementById("seekBackBtn"),
  playPauseBtn: document.getElementById("playPauseBtn"),
  seekForwardBtn: document.getElementById("seekForwardBtn"),
  playbackMeta: document.getElementById("playbackMeta"),
  trackZoom: document.getElementById("trackZoom"),
  trackZoomValue: document.getElementById("trackZoomValue"),
  timeline: document.getElementById("timeline"),
  frameMeta: document.getElementById("frameMeta"),
  leanGauge: document.getElementById("leanGauge"),
  leanValue: document.getElementById("leanValue"),
  leanDirection: document.getElementById("leanDirection"),
  speedValue: document.getElementById("speedValue"),
  driveValue: document.getElementById("driveValue"),
  driveBar: document.getElementById("driveBar"),
  driveBrakeFill: document.getElementById("driveBrakeFill"),
  driveThrottleFill: document.getElementById("driveThrottleFill"),
  algorithmNotes: document.getElementById("algorithmNotes"),
  status: document.getElementById("status"),
  stage: document.getElementById("stage"),
};

const ctx = el.stage.getContext("2d");

const state = {
  rawText: "",
  session: null,
  sourceSession: null,
  sourceName: "",
  activeSessionName: "",
  sessionVariant: "source",
  hermiteStats: null,
  processed: null,
  laps: [],
  selectedLap: "all",
  frameIndex: 0,
  graphHitZones: [],
  profiles: [],
  expandedParamHelp: null,
  isPlaying: false,
  playbackStartTs: 0,
  playbackStartTickMs: 0,
  rafId: 0,
  liveProcessTimer: 0,
  trackZoom: 1.4,
  graphZoomLaps: 1,
  showGpsSeries: true,
  showImuSeries: true,
  activeTab: "tuning",
  isApplyingProfile: false,
};

const PROFILE_STORAGE_KEY = "imuReplayTuningProfiles.v1";
const LAST_PROFILE_STORAGE_KEY = "imuReplayLastProfileId.v1";
const LIVE_TUNING_DELAY_MS = 120;

const PARAM_HELP = {
  gyroScale: {
    technical: "Multiplies gyro readings before integration. Use it to correct a sensor range or unit mismatch so the integrated lean rate matches real motion.",
    simple: "Makes the gyro motion stronger or weaker. If lean grows too fast, reduce it. If lean feels lazy, increase it.",
  },
  smoothingSamples: {
    technical: "Moving-average window applied to the estimator output or comparison samples. Higher values reduce jitter but add lag and soften peaks.",
    simple: "Smooths the graph. Higher means cleaner but slower response.",
  },
  accelBlendMode: {
    technical: "Chooses how accelerometer correction is blended into the gyro estimate. `hard` uses thresholded correction, `soft` scales correction continuously by confidence.",
    simple: "Changes how aggressively the accelerometer helps straighten the lean estimate.",
  },
  accelCorrectionStrong: {
    technical: "High-confidence accelerometer correction gain used when the bike looks dynamically stable and gravity is trustworthy.",
    simple: "How strongly to trust the accelerometer when conditions look clean.",
  },
  accelCorrectionWeak: {
    technical: "Low-confidence accelerometer correction gain used when the bike is moving in a less trustworthy state.",
    simple: "How much accelerometer correction to keep even when conditions are messy.",
  },
  calibratedLeanGain: {
    technical: "Final scale factor applied to the calibrated lean estimate after filtering.",
    simple: "Stretches or shrinks the IMU lean curve.",
  },
  leanOffsetDeg: {
    technical: "Constant angular bias added to the output lean estimate, in degrees.",
    simple: "Shifts the whole lean curve left or right.",
  },
  longitudinalGain: {
    technical: "Scale factor applied to the chosen longitudinal IMU acceleration axis before splitting accel versus brake.",
    simple: "Makes the IMU accel/brake graph stronger or weaker.",
  },
  autoGpsLag: {
    technical: "When set to 1, scans a lag range and picks the GPS delay that maximizes the comparison score against the IMU estimate.",
    simple: "Lets the app auto-align GPS timing to IMU timing.",
  },
  gpsLagMs: {
    technical: "Manual GPS time shift applied during comparison, in milliseconds.",
    simple: "Moves the GPS graph earlier or later to line it up with IMU.",
  },
  autoLagMinMs: {
    technical: "Minimum GPS lag checked during auto-alignment scan.",
    simple: "The earliest timing offset the auto-aligner is allowed to test.",
  },
  autoLagMaxMs: {
    technical: "Maximum GPS lag checked during auto-alignment scan.",
    simple: "The latest timing offset the auto-aligner is allowed to test.",
  },
  autoLagStepMs: {
    technical: "Step size for the GPS lag scan. Smaller values search more precisely but cost more processing time.",
    simple: "How finely the auto-aligner searches for timing.",
  },
};

const visibleProcessors = () => Object.values(processors).filter((processor) => processor.visible !== false);

function activeProcessor() {
  return processors[el.algorithmSelect.value] || visibleProcessors()[0];
}

function profileId() {
  return `profile-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function loadProfilesFromStorage() {
  try {
    const parsed = JSON.parse(localStorage.getItem(PROFILE_STORAGE_KEY) || "[]");
    state.profiles = Array.isArray(parsed) ? parsed.filter((profile) => profile?.id && profile?.algorithmId) : [];
  } catch (err) {
    state.profiles = [];
    setStatus(`Could not read saved profiles: ${err.message}`);
  }
}

function saveProfilesToStorage() {
  try {
    localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(state.profiles));
    return true;
  } catch (err) {
    setStatus(`Could not save profiles: ${err.message}`);
    return false;
  }
}

function lastUsedProfileId() {
  return localStorage.getItem(LAST_PROFILE_STORAGE_KEY) || "";
}

function rememberLastUsedProfile(profileId = "") {
  if (profileId) localStorage.setItem(LAST_PROFILE_STORAGE_KEY, profileId);
  else localStorage.removeItem(LAST_PROFILE_STORAGE_KEY);
}

function processorLabel(id) {
  return processors[id]?.label || id || "Unknown";
}

function populateProfileSelect(selectedId = el.profileSelect.value || lastUsedProfileId()) {
  el.profileSelect.innerHTML = "";
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "New profile";
  el.profileSelect.appendChild(empty);

  for (const profile of state.profiles) {
    const option = document.createElement("option");
    option.value = profile.id;
    option.textContent = `${profile.name} (${processorLabel(profile.algorithmId)})`;
    el.profileSelect.appendChild(option);
  }

  el.profileSelect.value = state.profiles.some((profile) => profile.id === selectedId) ? selectedId : "";
  syncProfileName();
}

function selectedProfile() {
  return state.profiles.find((profile) => profile.id === el.profileSelect.value) || null;
}

function syncProfileName() {
  const selected = selectedProfile();
  if (selected) {
    el.profileName.value = selected.name;
  } else {
    el.profileName.value = "";
  }
}

function setActiveTab(tab) {
  state.activeTab = tab === "hermite" ? "hermite" : "tuning";
  const tuningActive = state.activeTab === "tuning";
  el.tuningTabBtn.classList.toggle("active", tuningActive);
  el.hermiteTabBtn.classList.toggle("active", !tuningActive);
  el.tuningPane.classList.toggle("hidden-pane", !tuningActive);
  el.hermitePane.classList.toggle("hidden-pane", tuningActive);
}

function datasetMetaText() {
  const sessionLabel = state.activeSessionName || "No session loaded";
  if (state.sessionVariant !== "hermite" || !state.hermiteStats) {
    return `${sessionLabel}\nOriginal session data is active.`;
  }
  return `${sessionLabel}\nHermite enrichment: requested ${state.hermiteStats.requestedFactor}x, applied ${state.hermiteStats.appliedFactor}x, GPS ${state.hermiteStats.originalGpsPoints} -> ${state.hermiteStats.totalGpsPoints}, promoted IG rows ${state.hermiteStats.promotedRows}, max ${state.hermiteStats.maxFactor}x.`;
}

function syncSessionMeta() {
  el.csvFileName.textContent = state.activeSessionName || "No file selected";
  el.sessionDatasetMeta.textContent = datasetMetaText();
}

function applyProfile(profile, { autoProcess = false, quiet = false } = {}) {
  if (!profile || !processors[profile.algorithmId]) return false;
  state.isApplyingProfile = true;
  el.profileSelect.value = profile.id;
  el.algorithmSelect.value = profile.algorithmId;
  renderParamFields();
  setParamValues(profile.params);
  el.profileName.value = profile.name;
  state.isApplyingProfile = false;
  rememberLastUsedProfile(profile.id);
  if (autoProcess && state.session) {
    processSession();
  } else if (!quiet) {
    render();
    setStatus(`Loaded profile "${profile.name}". Click Process to re-run if you change values.`);
  }
  return true;
}

function preferredProfile() {
  const remembered = lastUsedProfileId();
  return state.profiles.find((profile) => profile.id === remembered) || selectedProfile();
}

function applyPreferredProfile({ autoProcess = false, quiet = false } = {}) {
  const profile = preferredProfile();
  if (!profile) return false;
  return applyProfile(profile, { autoProcess, quiet });
}

function currentParamValues() {
  const processor = activeProcessor();
  const params = {};
  for (const param of processor.params || []) {
    const input = document.getElementById(`param-${param.key}`);
    if (!input) continue;
    params[param.key] = input.type === "number" ? Number(input.value) : input.value;
  }
  return params;
}

function setParamValues(values = {}) {
  const processor = activeProcessor();
  for (const param of processor.params || []) {
    const input = document.getElementById(`param-${param.key}`);
    if (!input) continue;
    input.value = values[param.key] ?? param.default;
  }
}

function initAlgorithms() {
  el.algorithmSelect.innerHTML = "";
  visibleProcessors().forEach((processor) => {
    const option = document.createElement("option");
    option.value = processor.id;
    option.textContent = processor.label;
    el.algorithmSelect.appendChild(option);
  });
  el.algorithmSelect.value = visibleProcessors()[0]?.id || "";
  renderParamFields();
}

function renderParamFields({ preserveExisting = false } = {}) {
  const processor = activeProcessor();
  const existingValues = preserveExisting ? currentParamValues() : {};
  el.paramFields.innerHTML = "";
  for (const param of processor.params || []) {
    const label = document.createElement("label");
    label.className = "field";
    label.dataset.param = param.key;

    const header = document.createElement("div");
    header.className = "field-header";

    const caption = document.createElement("span");
    caption.textContent = param.label;
    header.appendChild(caption);

    const infoBtn = document.createElement("button");
    infoBtn.type = "button";
    infoBtn.className = "info-btn";
    infoBtn.textContent = "i";
    infoBtn.setAttribute("aria-label", `Explain ${param.label}`);
    infoBtn.addEventListener("click", (event) => {
      event.preventDefault();
      state.expandedParamHelp = state.expandedParamHelp === param.key ? null : param.key;
      renderParamFields({ preserveExisting: true });
    });
    header.appendChild(infoBtn);
    label.appendChild(header);

    const input = document.createElement("input");
    input.id = `param-${param.key}`;
    input.dataset.key = param.key;
    input.type = param.type || "number";
    input.step = param.step ?? "any";
    input.value = existingValues[param.key] ?? param.default;
    input.addEventListener("input", () => {
      scheduleLiveProcess();
    });
    label.appendChild(input);

    if (state.expandedParamHelp === param.key) {
      const help = document.createElement("div");
      help.className = "param-help";
      const tech = PARAM_HELP[param.key]?.technical || `${param.label} is passed directly into the active processor configuration.`;
      const simple = PARAM_HELP[param.key]?.simple || `This changes how ${param.label.toLowerCase()} influences the output.`;
      help.innerHTML = `<strong>Technical</strong>${tech}<strong>Simple</strong>${simple}`;
      label.appendChild(help);
    }
    el.paramFields.appendChild(label);
  }
}

function cancelLiveProcess() {
  if (state.liveProcessTimer) {
    clearTimeout(state.liveProcessTimer);
    state.liveProcessTimer = 0;
  }
}

function scheduleLiveProcess() {
  el.liveTuningMeta.textContent = `Live tuning is on. Reprocessing ${state.activeSessionName || "active session"}...`;
  cancelLiveProcess();
  if (!state.session) {
    setStatus("Parameters changed. Load a session CSV to process it.");
    render();
    return;
  }
  state.liveProcessTimer = window.setTimeout(() => {
    state.liveProcessTimer = 0;
    processSession();
  }, LIVE_TUNING_DELAY_MS);
}

function saveProfile() {
  const name = el.profileName.value.trim();
  if (!name) {
    setStatus("Enter a profile name before saving.");
    return;
  }

  const existingIndex = state.profiles.findIndex((profile) => profile.id === el.profileSelect.value);
  const now = new Date().toISOString();
  const profile = {
    id: existingIndex >= 0 ? state.profiles[existingIndex].id : profileId(),
    name,
    algorithmId: activeProcessor().id,
    params: currentParamValues(),
    updatedAt: now,
    createdAt: existingIndex >= 0 ? state.profiles[existingIndex].createdAt : now,
  };

  if (existingIndex >= 0) state.profiles[existingIndex] = profile;
  else state.profiles.push(profile);

  if (!saveProfilesToStorage()) return;
  rememberLastUsedProfile(profile.id);
  populateProfileSelect(profile.id);
  setStatus(`Saved profile "${profile.name}" for ${processorLabel(profile.algorithmId)}.`);
}

function loadSelectedProfile() {
  const profile = selectedProfile();
  if (!profile) {
    setStatus("Select a saved profile to load.");
    return;
  }
  applyProfile(profile, { autoProcess: Boolean(state.session), quiet: !state.session });
  if (!state.session) setStatus(`Loaded profile "${profile.name}". Load a session CSV to process it.`);
}

function deleteSelectedProfile() {
  const profile = selectedProfile();
  if (!profile) {
    setStatus("Select a saved profile to delete.");
    return;
  }
  state.profiles = state.profiles.filter((item) => item.id !== profile.id);
  if (!saveProfilesToStorage()) return;
  if (lastUsedProfileId() === profile.id) rememberLastUsedProfile("");
  populateProfileSelect("");
  el.profileName.value = "";
  setStatus(`Deleted profile "${profile.name}".`);
}

function resetParams() {
  renderParamFields();
  scheduleLiveProcess();
}

function currentConfig() {
  const processor = activeProcessor();
  const config = {
    minSpeed: 0,
    smoothingMs: 100,
    leanRateLimit: 90,
    upMinG: 0.65,
    leanGain: 1,
    upFloorG: 0.15,
    accMagTol: 0.16,
    lowSpeedKmh: 15,
    turnSpeedKmh: 45,
    pitchWarnDeg: 18,
    fusionTauSec: 0.45,
    mahonyKp: 0.5,
    mahonyKi: 0.02,
    vibrationWindowMs: 500,
    lateralVibeThresholdG: 0.06,
    verticalVibeThresholdG: 0.16,
    enableHampelFilter: false,
    enableMovingAverage: false,
    maskLowSpeed: false,
    maskAccelMagnitude: false,
    maskPitch: false,
    maskLongitudinalAccel: false,
    maskWeakTurnEvidence: false,
    maskLateralVibration: false,
    maskVerticalVibration: false,
    holdMaskedLean: false,
  };
  for (const param of processor.params || []) {
    const input = document.getElementById(`param-${param.key}`);
    if (!input) continue;
    config[param.key] = input.type === "number" ? Number(input.value) : input.value;
  }
  return config;
}

function setStatus(message) {
  el.status.textContent = message;
}

function setNotes(message) {
  el.algorithmNotes.textContent = message;
}

function activateSession(session, name, { rawText = "", variant = "source", hermiteStats = null, autoProcess = false } = {}) {
  state.rawText = rawText || serializeSessionCsv(session);
  state.session = session;
  state.activeSessionName = name;
  state.sessionVariant = variant;
  state.hermiteStats = hermiteStats;
  state.processed = null;
  state.laps = [];
  state.selectedLap = "all";
  state.frameIndex = 0;
  state.graphHitZones = [];
  syncSessionMeta();
  setStatus(`Loaded ${name}\nRows: ${state.session.rows.length}`);
  if (autoProcess) {
    processSession();
    return;
  }
  render();
}

function processHermiteSession() {
  if (!state.session) {
    setStatus("Load a session CSV first.");
    return;
  }
  const factor = Math.max(1, Math.round(Number(el.hermiteFactor.value) || 3));
  const enriched = enrichSessionWithHermite(state.sessionVariant === "source" && state.sourceSession ? state.sourceSession : state.session, { factor });
  if (enriched.stats?.error) {
    setStatus(enriched.stats.error);
    return;
  }
  const baseName = (state.sourceName || state.activeSessionName || "session.csv").replace(/\.csv$/i, "");
  const enrichedName = `${baseName}.hermite${enriched.stats.appliedFactor}x.csv`;
  activateSession(enriched.session, enrichedName, {
    rawText: serializeSessionCsv(enriched.session),
    variant: "hermite",
    hermiteStats: enriched.stats,
    autoProcess: true,
  });
}

function reloadOriginalSession() {
  if (!state.sourceSession) {
    setStatus("Load a session CSV first.");
    return;
  }
  activateSession(state.sourceSession, state.sourceName || "original.csv", {
    variant: "source",
    hermiteStats: null,
    autoProcess: true,
  });
}

function loadText(name, text) {
  stopPlayback();
  const parsed = parseSessionCsv(text);
  state.sourceSession = parsed;
  state.sourceName = name;
  applyPreferredProfile({ quiet: true });
  activateSession(parsed, name, { rawText: text, variant: "source", hermiteStats: null, autoProcess: true });
}

async function readFile(file) {
  const text = await file.text();
  loadText(file.name, text);
}

async function loadDemo() {
  const response = await fetch("/temp_data/sess_004.csv");
  if (!response.ok) {
    setStatus("Failed to load demo CSV from /temp_data/sess_004.csv");
    return;
  }
  const text = await response.text();
  loadText("sess_004.csv", text);
}

function processSession() {
  if (!state.session) {
    setStatus("Load a session CSV first.");
    return;
  }
  cancelLiveProcess();
  const previousFrames = currentFrames();
  const previousTickMs = frameAt(state.frameIndex)?.tickMs || previousFrames[0]?.tickMs || 0;
  const previousLapSelection = state.selectedLap;
  const previousGraphZoom = state.graphZoomLaps;

  const processor = activeProcessor();
  const config = currentConfig();
  const result = processor.process(state.session, config);
  stopPlayback();
  state.processed = result;
  state.laps = detectLaps(result.frames);
  populateLapSelect(state.laps);
  syncGraphZoomBounds(previousFrames.length ? previousGraphZoom : state.laps.length || 1);
  el.timeline.min = 0;
  el.timeline.max = Math.max(0, currentFrames().length - 1);
  state.frameIndex = frameIndexForTick(currentFrames(), previousTickMs);
  const hasPreviousLap = previousLapSelection !== "all" && state.laps.some((lap) => lap.id === previousLapSelection);
  state.selectedLap = hasPreviousLap ? previousLapSelection : "all";
  el.lapSelect.value = state.selectedLap;
  el.timeline.value = String(state.frameIndex);
  syncPlaybackUi();

  refreshScores();
  el.liveTuningMeta.textContent = `Live tuning is on. Editing now reprocesses ${state.sessionVariant === "hermite" ? "Hermite-enriched" : "active"} session data immediately.`;
  render();
}

function refreshScores() {
  if (!state.processed) return;
  const config = state.processed.config || currentConfig();
  const frames = currentFrames();
  applyAutoGpsLag(config, state.processed, frames);
  const scores = scoreFrames(frames, effectiveGpsLagMs(state.processed));
  setStatus(formatStats(state.processed, scores));
  setNotes(formatNotes(activeProcessor(), state.processed, config, scores));
}

function effectiveGpsLagMs(result = state.processed) {
  return Number(result?.config?.effectiveGpsLagMs ?? result?.config?.gpsLagMs ?? 0);
}

function applyAutoGpsLag(config, result, frames) {
  const requested = Number(config.autoGpsLag) === 1;
  result.config = { ...result.config, effectiveGpsLagMs: Number(config.gpsLagMs) || 0, autoGpsLag: requested };
  if (!requested || result.stats?.error || !frames?.length) {
    return;
  }

  const scan = findBestGpsLag(frames, config);
  result.config.effectiveGpsLagMs = scan.lagMs;
  result.stats.autoGpsLagMs = scan.lagMs;
  result.stats.autoGpsLagScore = Number(scan.score.toFixed(3));
  result.stats.autoGpsLagLeanCorr = Number(scan.scores.lean.corr.toFixed(3));
  result.stats.autoGpsLagLongCorr = Number(scan.scores.long.corr.toFixed(3));
}

function formatNotes(processor, result, config, scores) {
  if (result.stats?.error) return result.stats.error;
  const repairs = formatRepairs(result.stats.repairs);
  const lines = [
    processor.description,
    "",
    `Algorithm: ${result.algorithm}`,
    `GPS lag: ${effectiveGpsLagMs(result)} ms${result.config?.autoGpsLag ? " (auto)" : ""}`,
    `Lean MAE: ${scores.lean.mae.toFixed(2)} deg, corr ${scores.lean.corr.toFixed(3)}`,
    `Longitudinal MAE: ${scores.long.mae.toFixed(3)} g, corr ${scores.long.corr.toFixed(3)}`,
    `Gyro scale: ${result.stats.gyroScale ?? config.gyroScale ?? "n/a"}`,
    `Smoothing samples: ${result.stats.smoothingSamples ?? config.smoothingSamples ?? "n/a"}`,
    `Manual lean offset: ${result.stats.leanOffsetDeg ?? config.leanOffsetDeg ?? 0} deg`,
    `Profile static lean offset: ${result.stats.profileStaticLeanOffsetDeg ?? "n/a"} deg`,
    `Accel blend: ${result.stats.accelBlendMode ?? config.accelBlendMode ?? "hard"} strong=${result.stats.accelCorrectionStrong ?? config.accelCorrectionStrong ?? "n/a"} weak=${result.stats.accelCorrectionWeak ?? config.accelCorrectionWeak ?? "n/a"}`,
    `Lean axis: ${result.stats.axisName || "n/a"} ${result.stats.axisCorrelation ?? ""}`,
    `Accel axis: ${result.stats.accelAxisName || "n/a"} ${result.stats.accelAxisCorrelation ?? ""}`,
    "Useful gyro scale presets: 1/8=0.125, 1/10=0.100, 1/12=0.0833, 1/14=0.0714, 1/16=0.0625, 1/32=0.03125",
  ];
  if (repairs) lines.push(`Repairs: ${repairs}`);
  return lines.join("\n");
}

function formatStats(result, scores) {
  if (result.stats?.error) return result.stats.error;
  const lines = [
    `Algorithm: ${result.algorithm}`,
    `Frames: ${result.stats.imuFrames}`,
    `GPS points: ${result.stats.gpsPoints}`,
    `Distance: ${(result.stats.totalDistanceM / 1000).toFixed(2)} km`,
    `Median dt: ${result.stats.medianDtMs.toFixed(1)} ms`,
    `Max lean: ${result.stats.maxLeanDeg.toFixed(1)} deg`,
    `Max accel/brake: ${result.stats.maxAccelG.toFixed(3)}g / ${result.stats.maxBrakeG.toFixed(3)}g`,
    `Gyro scale: ${result.stats.gyroScale ?? "n/a"}`,
    `Smoothing samples: ${result.stats.smoothingSamples ?? "n/a"}`,
    `Lean offset: ${result.stats.leanOffsetDeg ?? "n/a"} deg`,
    `GPS lag: ${effectiveGpsLagMs(result)} ms${result.config?.autoGpsLag ? " (auto)" : ""}`,
    `Profile static offset: ${result.stats.profileStaticLeanOffsetDeg ?? "n/a"} deg`,
    `Accel blend: ${result.stats.accelBlendMode ?? "n/a"} (${result.stats.accelCorrectionStrong ?? "n/a"} / ${result.stats.accelCorrectionWeak ?? "n/a"})`,
    `Lean score: ${scores.lean.mae.toFixed(2)} deg MAE, ${scores.lean.corr.toFixed(3)} corr`,
    `Long score: ${scores.long.mae.toFixed(3)}g MAE, ${scores.long.corr.toFixed(3)} corr`,
    `Profile: ${result.stats.profileName} (${result.stats.profileQuality ?? "n/a"})`,
  ];
  const repairs = formatRepairs(result.stats.repairs);
  if (repairs) lines.push(`Repairs: ${repairs}`);
  return lines.join("\n");
}

function formatRepairs(repairs) {
  if (!repairs?.length) return "";
  return repairs.map((repair) => {
    if (repair.type === "manual_gyro_scale") {
      const rate = repair.detectedSampleRateHz ?? "n/a";
      const p99 = repair.gyroAbsP99Before ?? "n/a";
      return `manual gyro scale ${repair.scale} (${rate}Hz, p99 ${p99})`;
    }
    if (repair.type === "bmi323_gyro_range_scale") {
      const rate = repair.detectedSampleRateHz ?? repair.detected_sample_rate_hz ?? "n/a";
      const p99 = repair.gyroAbsP99Before ?? repair.gyro_abs_p99_before ?? "n/a";
      return `BMI323 gyro x${repair.scale} (${rate}Hz, p99 ${p99})`;
    }
    return repair.type || "unknown";
  }).join("; ");
}

function currentFrames() {
  return state.processed?.frames || [];
}

function frameAt(index) {
  return currentFrames()[index] || null;
}

function graphWindowLapCount() {
  if (!state.laps.length) return 1;
  return Math.max(1, Math.min(state.laps.length, Math.round(state.graphZoomLaps || state.laps.length)));
}

function averageLapDurationMs() {
  if (!state.laps.length) return totalDurationMs();
  const total = state.laps.reduce((sum, lap) => sum + ((lap.durationSec || 0) * 1000), 0);
  return total > 0 ? total / state.laps.length : totalDurationMs();
}

function graphWindowRange() {
  const frames = currentFrames();
  if (!frames.length) return { start: 0, end: 0, frames };
  if (!state.laps.length || graphWindowLapCount() >= state.laps.length) {
    return { start: 0, end: frames.length - 1, frames };
  }

  const windowDurationMs = averageLapDurationMs() * graphWindowLapCount();
  const centerTickMs = frameAt(state.frameIndex)?.tickMs || frames[0].tickMs;
  const firstTickMs = frames[0].tickMs;
  const lastTickMs = frames[frames.length - 1].tickMs;
  let startTickMs = centerTickMs - (windowDurationMs / 2);
  let endTickMs = centerTickMs + (windowDurationMs / 2);
  if (startTickMs < firstTickMs) {
    endTickMs += firstTickMs - startTickMs;
    startTickMs = firstTickMs;
  }
  if (endTickMs > lastTickMs) {
    startTickMs -= endTickMs - lastTickMs;
    endTickMs = lastTickMs;
  }
  startTickMs = Math.max(firstTickMs, startTickMs);
  endTickMs = Math.min(lastTickMs, endTickMs);
  return {
    start: frameIndexForTick(frames, startTickMs),
    end: frameIndexForTick(frames, endTickMs),
    frames,
  };
}

function frameIndexForTick(frames, tickMs) {
  if (!frames.length) return 0;
  if (tickMs <= frames[0].tickMs) return 0;
  if (tickMs >= frames[frames.length - 1].tickMs) return frames.length - 1;
  let lo = 0;
  let hi = frames.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (frames[mid].tickMs <= tickMs) lo = mid;
    else hi = mid;
  }
  return (tickMs - frames[lo].tickMs) <= (frames[hi].tickMs - tickMs) ? lo : hi;
}

function currentFrameElapsedMs() {
  const frames = currentFrames();
  if (!frames.length) return 0;
  return Math.max(0, (frameAt(state.frameIndex)?.tickMs || frames[0].tickMs) - frames[0].tickMs);
}

function totalDurationMs() {
  const frames = currentFrames();
  if (!frames.length) return 0;
  return Math.max(0, frames[frames.length - 1].tickMs - frames[0].tickMs);
}

function formatPlaybackTime(ms) {
  const totalTenths = Math.max(0, Math.round(ms / 100));
  const minutes = Math.floor(totalTenths / 600);
  const seconds = Math.floor((totalTenths % 600) / 10);
  const tenths = totalTenths % 10;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${tenths}`;
}

function seekByMs(deltaMs) {
  const frames = currentFrames();
  if (!frames.length) return;
  const currentTickMs = frameAt(state.frameIndex)?.tickMs || frames[0].tickMs;
  const targetTickMs = Math.max(frames[0].tickMs, Math.min(frames[frames.length - 1].tickMs, currentTickMs + deltaMs));
  state.frameIndex = frameIndexForTick(frames, targetTickMs);
  el.timeline.value = String(state.frameIndex);
  if (state.isPlaying) startPlayback();
  render();
}

function syncPlaybackUi() {
  el.playPauseBtn.textContent = state.isPlaying ? "Pause" : "Play";
  el.playPauseBtn.disabled = currentFrames().length === 0;
  el.seekBackBtn.disabled = currentFrames().length === 0;
  el.seekForwardBtn.disabled = currentFrames().length === 0;
  el.playbackMeta.textContent = `${formatPlaybackTime(currentFrameElapsedMs())} / ${formatPlaybackTime(totalDurationMs())}`;
  el.trackZoomValue.textContent = `${state.trackZoom.toFixed(1)}x`;
  const lapCount = graphWindowLapCount();
  el.graphZoomValue.textContent = state.laps.length && lapCount >= state.laps.length ? `All ${state.laps.length} laps` : `${lapCount} lap${lapCount === 1 ? "" : "s"} view`;
}

function cancelPlaybackFrame() {
  if (state.rafId) {
    cancelAnimationFrame(state.rafId);
    state.rafId = 0;
  }
}

function stopPlayback() {
  state.isPlaying = false;
  state.playbackStartTs = 0;
  state.playbackStartTickMs = 0;
  cancelPlaybackFrame();
  syncPlaybackUi();
}

function startPlayback() {
  const frames = currentFrames();
  if (!frames.length) return;
  if (state.frameIndex >= frames.length - 1) {
    state.frameIndex = 0;
    el.timeline.value = "0";
  }
  state.isPlaying = true;
  state.playbackStartTs = 0;
  state.playbackStartTickMs = frameAt(state.frameIndex)?.tickMs || frames[0].tickMs;
  syncPlaybackUi();
  cancelPlaybackFrame();
  state.rafId = requestAnimationFrame(stepPlayback);
}

function togglePlayback() {
  if (state.isPlaying) {
    stopPlayback();
    render();
    return;
  }
  startPlayback();
}

function stepPlayback(timestamp) {
  if (!state.isPlaying) return;
  const frames = currentFrames();
  if (!frames.length) {
    stopPlayback();
    render();
    return;
  }
  if (!state.playbackStartTs) state.playbackStartTs = timestamp;
  const elapsedMs = timestamp - state.playbackStartTs;
  const targetTickMs = state.playbackStartTickMs + elapsedMs;
  const lastTickMs = frames[frames.length - 1].tickMs;
  if (targetTickMs >= lastTickMs) {
    state.frameIndex = frames.length - 1;
    el.timeline.value = String(state.frameIndex);
    stopPlayback();
    render();
    return;
  }
  state.frameIndex = frameIndexForTick(frames, targetTickMs);
  el.timeline.value = String(state.frameIndex);
  render();
  state.rafId = requestAnimationFrame(stepPlayback);
}

function valueAt(frames, getter, targetTickMs) {
  if (!frames.length) return 0;
  if (targetTickMs <= frames[0].tickMs) return getter(frames[0]);
  if (targetTickMs >= frames[frames.length - 1].tickMs) return getter(frames[frames.length - 1]);
  let lo = 0;
  let hi = frames.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (frames[mid].tickMs <= targetTickMs) lo = mid;
    else hi = mid;
  }
  const a = frames[lo];
  const b = frames[hi];
  const span = Math.max(1, b.tickMs - a.tickMs);
  const alpha = (targetTickMs - a.tickMs) / span;
  return getter(a) + ((getter(b) - getter(a)) * alpha);
}

function shiftedGpsValue(frames, frame, getter) {
  const lagMs = effectiveGpsLagMs();
  return valueAt(frames, getter, frame.tickMs + lagMs);
}

function pearson(xs, ys) {
  if (xs.length !== ys.length || xs.length < 3) return 0;
  const meanX = xs.reduce((sum, value) => sum + value, 0) / xs.length;
  const meanY = ys.reduce((sum, value) => sum + value, 0) / ys.length;
  let numerator = 0;
  let denomX = 0;
  let denomY = 0;
  for (let index = 0; index < xs.length; index += 1) {
    const dx = xs[index] - meanX;
    const dy = ys[index] - meanY;
    numerator += dx * dy;
    denomX += dx * dx;
    denomY += dy * dy;
  }
  return denomX > 1e-9 && denomY > 1e-9 ? numerator / Math.sqrt(denomX * denomY) : 0;
}

function scorePairs(pairs) {
  if (!pairs.length) return { mae: 0, rmse: 0, corr: 0, n: 0 };
  const xs = pairs.map(([imu]) => imu);
  const ys = pairs.map(([, gps]) => gps);
  const mae = pairs.reduce((sum, [imu, gps]) => sum + Math.abs(imu - gps), 0) / pairs.length;
  const rmse = Math.sqrt(pairs.reduce((sum, [imu, gps]) => sum + ((imu - gps) ** 2), 0) / pairs.length);
  return { mae, rmse, corr: pearson(xs, ys), n: pairs.length };
}

function scoreFrames(frames, lagMs) {
  const leanPairs = [];
  const longPairs = [];
  for (const frame of frames) {
    const gpsLean = valueAt(frames, (item) => item.gpsLeanDeg || 0, frame.tickMs + lagMs);
    const gpsLong = valueAt(frames, (item) => item.gpsAccelG || 0, frame.tickMs + lagMs);
    const imuLong = (frame.accelG || 0) - (frame.brakeG || 0);
    if ((frame.speedKmh || 0) > 20 && Math.abs(gpsLean) > 2) leanPairs.push([frame.leanDeg || 0, gpsLean]);
    if ((frame.speedKmh || 0) > 15 && Math.abs(gpsLong) > 0.025) longPairs.push([imuLong, gpsLong]);
  }
  return { lean: scorePairs(leanPairs), long: scorePairs(longPairs) };
}

function lagScore(scores) {
  const leanCorr = Math.max(0, scores.lean.corr);
  const longCorr = Math.max(0, scores.long.corr);
  const leanMaeScore = Math.max(0, 1 - (scores.lean.mae / 18));
  const longMaeScore = Math.max(0, 1 - (scores.long.mae / 0.22));
  const leanWeight = scores.lean.n > 20 ? 0.55 : 0;
  const longWeight = scores.long.n > 20 ? 0.45 : 0;
  const totalWeight = Math.max(1e-9, leanWeight + longWeight);
  const leanScore = (0.7 * leanCorr) + (0.3 * leanMaeScore);
  const longScore = (0.7 * longCorr) + (0.3 * longMaeScore);
  return ((leanScore * leanWeight) + (longScore * longWeight)) / totalWeight;
}

function findBestGpsLag(frames, config) {
  let minLag = Number.isFinite(config.autoLagMinMs) ? config.autoLagMinMs : -800;
  let maxLag = Number.isFinite(config.autoLagMaxMs) ? config.autoLagMaxMs : 2200;
  const step = Math.max(1, Math.abs(Math.round(Number(config.autoLagStepMs) || 25)));
  if (minLag > maxLag) [minLag, maxLag] = [maxLag, minLag];

  let best = null;
  for (let lag = minLag; lag <= maxLag; lag += step) {
    const scores = scoreFrames(frames, lag);
    const score = lagScore(scores);
    if (!best || score > best.score) {
      best = { lagMs: lag, score, scores };
    }
  }
  return best || { lagMs: Number(config.gpsLagMs) || 0, score: 0, scores: scoreFrames(frames, Number(config.gpsLagMs) || 0) };
}

function angularDiffDeg(a, b) {
  let delta = Math.abs(a - b) % 360;
  if (delta > 180) delta = 360 - delta;
  return delta;
}

function detectLaps(frames) {
  if (!frames?.length) return [];
  const dts = [];
  for (let i = 1; i < frames.length; i += 1) {
    const dt = (frames[i].tickMs - frames[i - 1].tickMs) / 1000;
    if (dt > 0.001 && dt < 0.2) dts.push(dt);
  }
  const sortedDt = dts.slice().sort((a, b) => a - b);
  const dtSec = sortedDt.length ? sortedDt[Math.floor(sortedDt.length / 2)] : 0.02;
  const stride = Math.max(1, Math.round(0.2 / dtSec));
  const sampled = frames
    .filter((_, index) => index % stride === 0)
    .map((frame, index) => ({ ...frame, originalIndex: index * stride }));
  if (sampled.length < 200) return [];

  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  const cumulativeDist = [0];
  for (let i = 0; i < sampled.length; i += 1) {
    minX = Math.min(minX, sampled[i].x);
    maxX = Math.max(maxX, sampled[i].x);
    minY = Math.min(minY, sampled[i].y);
    maxY = Math.max(maxY, sampled[i].y);
    if (i > 0) cumulativeDist.push(cumulativeDist[i - 1] + Math.hypot(sampled[i].x - sampled[i - 1].x, sampled[i].y - sampled[i - 1].y));
  }

  const diag = Math.hypot(maxX - minX, maxY - minY);
  const radiusM = Math.max(10, Math.min(25, diag * 0.015));
  const minLapSec = 20;
  const minGap = Math.max(20, Math.round(minLapSec / (dtSec * stride)));
  const skip = Math.max(0, Math.round(10 / (dtSec * stride)));

  let bestAnchor = -1;
  let bestCount = 0;
  for (let i = skip; i < sampled.length - minGap; i += 1) {
    let count = 0;
    let lastHit = -minGap;
    for (let j = i + minGap; j < sampled.length; j += 1) {
      if (Math.hypot(sampled[j].x - sampled[i].x, sampled[j].y - sampled[i].y) > radiusM) continue;
      if (angularDiffDeg(sampled[j].headingDeg, sampled[i].headingDeg) > 40) continue;
      if ((sampled[j].tickMs - sampled[i].tickMs) / 1000 < minLapSec) continue;
      if (cumulativeDist[j] - cumulativeDist[i] < 300) continue;
      if (j - lastHit < Math.round(minGap * 0.5)) continue;
      count += 1;
      lastHit = j;
    }
    if (count > bestCount) {
      bestCount = count;
      bestAnchor = i;
    }
  }

  if (bestAnchor < 0 || bestCount < 1) return [];
  const boundaries = [sampled[bestAnchor].originalIndex];
  let lastBoundary = bestAnchor;
  for (let j = bestAnchor + minGap; j < sampled.length; j += 1) {
    if (Math.hypot(sampled[j].x - sampled[bestAnchor].x, sampled[j].y - sampled[bestAnchor].y) > radiusM) continue;
    if (angularDiffDeg(sampled[j].headingDeg, sampled[bestAnchor].headingDeg) > 40) continue;
    if ((sampled[j].tickMs - sampled[lastBoundary].tickMs) / 1000 < minLapSec) continue;
    boundaries.push(sampled[j].originalIndex);
    lastBoundary = j;
  }

  const laps = [];
  for (let i = 0; i < boundaries.length - 1; i += 1) {
    const start = boundaries[i];
    const end = boundaries[i + 1];
    if (end - start < 50) continue;
    laps.push({
      id: `lap-${laps.length + 1}`,
      label: `Lap ${laps.length + 1}`,
      start,
      end,
      durationSec: (frames[end].tickMs - frames[start].tickMs) / 1000,
    });
  }
  return laps;
}

function populateLapSelect(laps) {
  el.lapSelect.innerHTML = "";
  const full = document.createElement("option");
  full.value = "all";
  full.textContent = "Full Session";
  el.lapSelect.appendChild(full);
  laps.forEach((lap) => {
    const option = document.createElement("option");
    option.value = lap.id;
    option.textContent = `${lap.label} (${lap.durationSec.toFixed(1)}s)`;
    el.lapSelect.appendChild(option);
  });
  el.lapSelect.disabled = laps.length === 0;
}

function applyLapSelection(selection) {
  state.selectedLap = selection;
  if (selection !== "all" && state.laps.length) {
    const lap = state.laps.find((entry) => entry.id === selection);
    if (lap) {
      state.frameIndex = Math.round((lap.start + lap.end) / 2);
      el.timeline.value = String(state.frameIndex);
    }
  }
  state.graphHitZones = [];
  syncPlaybackUi();
}

function syncGraphZoomBounds(preferredLapCount = state.graphZoomLaps) {
  const maxLaps = Math.max(1, state.laps.length || 1);
  el.graphZoom.min = "1";
  el.graphZoom.max = String(maxLaps);
  el.graphZoom.step = "1";
  state.graphZoomLaps = Math.max(1, Math.min(maxLaps, Math.round(preferredLapCount || maxLaps)));
  el.graphZoom.value = String(state.graphZoomLaps);
  syncPlaybackUi();
}

function render() {
  resizeCanvasIfNeeded();
  ctx.clearRect(0, 0, el.stage.width, el.stage.height);
  drawBackground();
  const frames = currentFrames();
  if (!frames.length) {
    drawEmptyState();
    return;
  }
  drawTelemetryGraphs();
  drawTrackContext();
  drawHud(frameAt(state.frameIndex));
}

function resizeCanvasIfNeeded() {
  const rect = el.stage.getBoundingClientRect();
  const width = Math.round(rect.width * window.devicePixelRatio);
  const height = Math.round(rect.height * window.devicePixelRatio);
  if (el.stage.width !== width || el.stage.height !== height) {
    el.stage.width = width;
    el.stage.height = height;
  }
}

function drawBackground() {
  const grad = ctx.createLinearGradient(0, 0, 0, el.stage.height);
  grad.addColorStop(0, "#f6f1e5");
  grad.addColorStop(1, "#e2dbca");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, el.stage.width, el.stage.height);
}

function drawHud(frame) {
  if (!frame) return;
  const frames = currentFrames();
  const gpsLean = shiftedGpsValue(frames, frame, (item) => item.gpsLeanDeg || 0);
  const gpsLong = shiftedGpsValue(frames, frame, (item) => item.gpsAccelG || 0);
  const imuLong = (frame.accelG || 0) - (frame.brakeG || 0);
  const leanDeg = frame.leanDeg || 0;
  const leanAbs = Math.abs(leanDeg);
  const leanRatio = Math.max(-1, Math.min(1, leanDeg / 60));
  const leanFill = (Math.abs(leanRatio) * 100).toFixed(2);
  const accelPct = Math.max(0, Math.min(1, frame.accelG || 0));
  const brakePct = Math.max(0, Math.min(1, frame.brakeG || 0));
  el.leanValue.textContent = `${frame.leanDeg.toFixed(1)} deg`;
  el.leanDirection.textContent = leanAbs < 1.5 ? "Upright" : `${leanDeg < 0 ? "Left" : "Right"} lean`;
  el.speedValue.textContent = `${frame.speedKmh.toFixed(1)} km/h`;
  el.leanGauge?.style.setProperty("--lean-ratio", String(leanRatio));
  el.leanGauge?.style.setProperty("--lean-fill-left", leanRatio < 0 ? leanFill : "0");
  el.leanGauge?.style.setProperty("--lean-fill-right", leanRatio > 0 ? leanFill : "0");
  el.driveThrottleFill.style.width = `${accelPct * 50}%`;
  el.driveBrakeFill.style.width = `${brakePct * 50}%`;
  if (accelPct > brakePct && accelPct > 0.02) {
    el.driveValue.textContent = `${(accelPct * 100).toFixed(0)}% throttle`;
  } else if (brakePct > accelPct && brakePct > 0.02) {
    el.driveValue.textContent = `${(brakePct * 100).toFixed(0)}% brake`;
  } else {
    el.driveValue.textContent = "Coast";
  }
  syncPlaybackUi();
  const activeLap = state.laps.find((lap) => frame.tickMs >= frames[lap.start]?.tickMs && frame.tickMs <= frames[lap.end]?.tickMs);
  const lapLabel = activeLap?.label || "Session";
  const focusLabel = state.selectedLap === "all" ? "Free scroll" : (state.laps.find((lap) => lap.id === state.selectedLap)?.label || "Free scroll");
  el.frameMeta.textContent = `${lapLabel} | Focus ${focusLabel} | Tick ${frame.tickMs} | Lean IMU/GPS ${frame.leanDeg.toFixed(1)} / ${gpsLean.toFixed(1)} deg | Long IMU/GPS ${imuLong.toFixed(3)} / ${gpsLong.toFixed(3)} g`;
}

function graphDefinitions(frames) {
  return [
    {
      title: "Lean: IMU attitude vs GPS curvature",
      gpsLabel: "GPS",
      imuLabel: "IMU",
      gpsColor: "#0b5cad",
      imuColor: "#d13f2f",
      gpsValue: (frame) => shiftedGpsValue(frames, frame, (item) => item.gpsLeanDeg || 0),
      imuValue: (frame) => frame.leanDeg || 0,
      minScale: 20,
      unit: "deg",
      positiveLabel: "right",
      negativeLabel: "left",
    },
    {
      title: "Longitudinal force: acceleration up, braking down",
      gpsLabel: "GPS",
      imuLabel: "IMU",
      gpsColor: "#0b5cad",
      imuColor: "#1a8f5b",
      gpsValue: (frame) => shiftedGpsValue(frames, frame, (item) => item.gpsAccelG || 0),
      imuValue: (frame) => (frame.accelG || 0) - (frame.brakeG || 0),
      minScale: 0.35,
      unit: "g",
      positiveLabel: "accel",
      negativeLabel: "brake",
    },
  ];
}

function drawTelemetryGraphs() {
  const frames = currentFrames();
  const windowRange = graphWindowRange();
  const visibleFrames = frames.slice(windowRange.start, windowRange.end + 1);
  const dpr = window.devicePixelRatio;
  const margin = 32 * dpr;
  const gap = 20 * dpr;
  const trackH = Math.max(170 * dpr, Math.min(260 * dpr, el.stage.height * 0.29));
  const hudReserve = 132 * dpr;
  const overlayReserve = 260 * dpr;
  const graphW = Math.max(320 * dpr, el.stage.width - (margin * 2) - overlayReserve);
  const graphH = (el.stage.height - (margin * 2) - (gap * 2) - hudReserve - trackH) / 2;
  state.graphHitZones = [];
  graphDefinitions(frames).forEach((graph, index) => {
    const y = margin + index * (graphH + gap);
    const zone = drawComparisonGraph(frames, visibleFrames, windowRange.start, graph, margin, y, graphW, graphH);
    state.graphHitZones.push(zone);
  });
}

function drawComparisonGraph(allFrames, visibleFrames, startIndex, graph, x, y, w, h) {
  const dpr = window.devicePixelRatio;
  const padLeft = 52 * dpr;
  const padRight = 18 * dpr;
  const padTop = 34 * dpr;
  const padBottom = 28 * dpr;
  const left = x + padLeft;
  const right = x + w - padRight;
  const top = y + padTop;
  const bottom = y + h - padBottom;
  const chartW = Math.max(1, right - left);
  const chartH = Math.max(1, bottom - top);
  const values = visibleFrames.flatMap((frame) => [graph.gpsValue(frame), graph.imuValue(frame)]);
  const maxValue = Math.max(graph.minScale, ...values.map((value) => Math.abs(value)));
  const xFor = (index) => left + (index / Math.max(1, visibleFrames.length - 1)) * chartW;
  const yFor = (value) => top + ((maxValue - value) / (maxValue * 2)) * chartH;

  ctx.fillStyle = "rgba(255, 250, 240, 0.94)";
  roundRect(ctx, x, y, w, h, 18 * dpr, true);
  ctx.strokeStyle = "rgba(41, 37, 31, 0.14)";
  ctx.lineWidth = 1 * dpr;
  ctx.strokeRect(x, y, w, h);

  ctx.strokeStyle = "rgba(41, 37, 31, 0.16)";
  ctx.lineWidth = 1 * dpr;
  for (let i = -1; i <= 1; i += 1) {
    const gy = yFor((maxValue * i) / 2);
    ctx.beginPath();
    ctx.moveTo(left, gy);
    ctx.lineTo(right, gy);
    ctx.stroke();
  }

  ctx.strokeStyle = "rgba(41, 37, 31, 0.45)";
  ctx.beginPath();
  ctx.moveTo(left, yFor(0));
  ctx.lineTo(right, yFor(0));
  ctx.stroke();

  if (state.showGpsSeries) drawSeries(visibleFrames, xFor, yFor, graph.gpsValue, graph.gpsColor, 2.0 * dpr);
  if (state.showImuSeries) drawSeries(visibleFrames, xFor, yFor, graph.imuValue, graph.imuColor, 1.7 * dpr);

  const markerWindowIndex = Math.max(0, Math.min(visibleFrames.length - 1, state.frameIndex - startIndex));
  const markerX = xFor(markerWindowIndex);
  ctx.strokeStyle = "rgba(20, 20, 20, 0.55)";
  ctx.lineWidth = 1 * dpr;
  ctx.beginPath();
  ctx.moveTo(markerX, top);
  ctx.lineTo(markerX, bottom);
  ctx.stroke();

  ctx.fillStyle = "#29251f";
  ctx.font = `${14 * dpr}px sans-serif`;
  ctx.fillText(graph.title, x + 18 * dpr, y + 24 * dpr);
  ctx.fillStyle = state.showGpsSeries ? graph.gpsColor : "rgba(11, 92, 173, 0.35)";
  ctx.fillText(graph.gpsLabel, x + 330 * dpr, y + 24 * dpr);
  ctx.fillStyle = state.showImuSeries ? graph.imuColor : "rgba(41, 37, 31, 0.35)";
  ctx.fillText(graph.imuLabel, x + 386 * dpr, y + 24 * dpr);
  ctx.fillStyle = "rgba(41, 37, 31, 0.72)";
  ctx.fillText(`+${maxValue.toFixed(graph.unit === "g" ? 2 : 0)} ${graph.unit}`, x + 10 * dpr, top + 8 * dpr);
  ctx.fillText(`-${maxValue.toFixed(graph.unit === "g" ? 2 : 0)} ${graph.unit}`, x + 10 * dpr, bottom);
  ctx.fillText(graph.positiveLabel, right - 60 * dpr, top + 12 * dpr);
  ctx.fillText(graph.negativeLabel, right - 60 * dpr, bottom - 6 * dpr);
  return { left, right, top, bottom, startIndex, visibleCount: visibleFrames.length };
}

function trackBounds(frames) {
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const frame of frames) {
    minX = Math.min(minX, frame.x);
    maxX = Math.max(maxX, frame.x);
    minY = Math.min(minY, frame.y);
    maxY = Math.max(maxY, frame.y);
  }
  return { minX, maxX, minY, maxY };
}

function drawTrackContext() {
  const frames = currentFrames();
  if (!frames.length) return;
  const dpr = window.devicePixelRatio;
  const margin = 32 * dpr;
  const trackH = Math.max(170 * dpr, Math.min(260 * dpr, el.stage.height * 0.29));
  const w = el.stage.width - (margin * 2);
  const h = trackH;
  const x = margin;
  const bottomOverlayReserve = 132 * dpr;
  const y = el.stage.height - margin - bottomOverlayReserve - trackH;
  const pad = 22 * dpr;
  const bounds = trackBounds(frames);
  const spanX = Math.max(1, bounds.maxX - bounds.minX);
  const spanY = Math.max(1, bounds.maxY - bounds.minY);
  const scale = Math.min((w - pad * 2) / spanX, (h - pad * 2) / spanY) * state.trackZoom;
  const mapX = (frame) => x + (w / 2) + ((frame.x - ((bounds.minX + bounds.maxX) / 2)) * scale);
  const mapY = (frame) => y + (h / 2) + ((frame.y - ((bounds.minY + bounds.maxY) / 2)) * scale);

  ctx.fillStyle = "rgba(255, 250, 240, 0.94)";
  roundRect(ctx, x, y, w, h, 18 * dpr, true);
  ctx.strokeStyle = "rgba(41, 37, 31, 0.14)";
  ctx.lineWidth = 1 * dpr;
  ctx.strokeRect(x, y, w, h);

  ctx.fillStyle = "rgba(13, 108, 116, 0.28)";
  frames.forEach((frame) => {
    ctx.beginPath();
    ctx.arc(mapX(frame), mapY(frame), 2.4 * dpr, 0, Math.PI * 2);
    ctx.fill();
  });

  ctx.strokeStyle = "rgba(45, 42, 38, 0.70)";
  ctx.lineWidth = 2 * dpr;
  ctx.beginPath();
  frames.forEach((frame, index) => {
    const px = mapX(frame);
    const py = mapY(frame);
    if (index === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.stroke();

  const selected = frameAt(state.frameIndex) || frames[0];
  drawTrackArrow(mapX(selected), mapY(selected), selected.headingDeg || 0, selected.leanDeg || 0);

  ctx.fillStyle = "#29251f";
  ctx.font = `${14 * dpr}px sans-serif`;
  ctx.fillText("GPS track context", x + 18 * dpr, y + 24 * dpr);
  ctx.fillStyle = "rgba(41, 37, 31, 0.72)";
  ctx.fillText("click graph to move marker", x + 150 * dpr, y + 24 * dpr);
}

function drawTrackArrow(x, y, headingDeg, leanDeg) {
  const dpr = window.devicePixelRatio;
  const size = 18 * dpr;
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate((headingDeg * Math.PI) / 180);
  ctx.fillStyle = leanDeg >= 0 ? "#d13f2f" : "#0d6c74";
  ctx.beginPath();
  ctx.moveTo(0, -size);
  ctx.lineTo(size * 0.62, size * 0.75);
  ctx.lineTo(0, size * 0.35);
  ctx.lineTo(-size * 0.62, size * 0.75);
  ctx.closePath();
  ctx.fill();
  ctx.restore();

  ctx.strokeStyle = "rgba(255, 250, 240, 0.9)";
  ctx.lineWidth = 3 * dpr;
  ctx.beginPath();
  ctx.arc(x, y, size * 0.9, 0, Math.PI * 2);
  ctx.stroke();
}

function drawSeries(frames, xFor, yFor, getter, color, lineWidth) {
  ctx.strokeStyle = color;
  ctx.lineWidth = lineWidth;
  ctx.beginPath();
  frames.forEach((frame, index) => {
    const px = xFor(index);
    const py = yFor(getter(frame));
    if (index === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.stroke();
}

function drawEmptyState() {
  syncPlaybackUi();
  ctx.fillStyle = "rgba(41, 37, 31, 0.62)";
  ctx.font = `${24 * window.devicePixelRatio}px sans-serif`;
  ctx.fillText("Load and process a session CSV to inspect tuning graphs.", 80 * window.devicePixelRatio, 100 * window.devicePixelRatio);
}

function roundRect(context, x, y, width, height, radius, fill) {
  context.beginPath();
  context.moveTo(x + radius, y);
  context.arcTo(x + width, y, x + width, y + height, radius);
  context.arcTo(x + width, y + height, x, y + height, radius);
  context.arcTo(x, y + height, x, y, radius);
  context.arcTo(x, y, x + width, y, radius);
  context.closePath();
  if (fill) context.fill();
}

el.csvFile.addEventListener("change", async (event) => {
  const [file] = event.target.files;
  if (file) await readFile(file);
});
el.loadDemoBtn.addEventListener("click", () => {
  loadDemo().catch((err) => setStatus(`Demo load failed: ${err.message}`));
});
el.tuningTabBtn.addEventListener("click", () => setActiveTab("tuning"));
el.hermiteTabBtn.addEventListener("click", () => setActiveTab("hermite"));
el.processBtn.addEventListener("click", processSession);
el.resetParamsBtn.addEventListener("click", resetParams);
el.profileSelect.addEventListener("change", syncProfileName);
el.saveProfileBtn.addEventListener("click", saveProfile);
el.loadProfileBtn.addEventListener("click", loadSelectedProfile);
el.deleteProfileBtn.addEventListener("click", deleteSelectedProfile);
el.processHermiteBtn.addEventListener("click", processHermiteSession);
el.reloadOriginalBtn.addEventListener("click", reloadOriginalSession);
el.algorithmSelect.addEventListener("change", () => {
  renderParamFields();
  if (!state.isApplyingProfile) {
    el.profileSelect.value = "";
    syncProfileName();
  }
  if (state.session) processSession();
  else {
    setStatus("Algorithm changed. Load a session CSV to process it.");
    render();
  }
});
el.lapSelect.addEventListener("change", () => {
  applyLapSelection(el.lapSelect.value);
  render();
});
el.graphZoom.addEventListener("input", () => {
  state.graphZoomLaps = Math.max(1, Number(el.graphZoom.value) || 1);
  syncPlaybackUi();
  render();
});
el.showGpsSeries.addEventListener("change", () => {
  state.showGpsSeries = el.showGpsSeries.checked;
  render();
});
el.showImuSeries.addEventListener("change", () => {
  state.showImuSeries = el.showImuSeries.checked;
  render();
});
el.seekBackBtn.addEventListener("click", () => seekByMs(-5000));
el.playPauseBtn.addEventListener("click", togglePlayback);
el.seekForwardBtn.addEventListener("click", () => seekByMs(5000));
el.trackZoom.addEventListener("input", () => {
  state.trackZoom = Math.max(1, Number(el.trackZoom.value) || 1);
  syncPlaybackUi();
  render();
});
el.timeline.addEventListener("input", () => {
  state.frameIndex = Number(el.timeline.value) || 0;
  if (state.isPlaying) startPlayback();
  render();
});
el.stage.addEventListener("click", (event) => {
  const frames = currentFrames();
  if (!frames.length) return;
  const rect = el.stage.getBoundingClientRect();
  const x = (event.clientX - rect.left) * window.devicePixelRatio;
  const y = (event.clientY - rect.top) * window.devicePixelRatio;
  const zone = state.graphHitZones.find((item) => x >= item.left && x <= item.right && y >= item.top && y <= item.bottom);
  if (!zone) return;
  const ratio = (x - zone.left) / Math.max(1, zone.right - zone.left);
  const localIndex = Math.max(0, Math.min(zone.visibleCount - 1, Math.round(ratio * Math.max(0, zone.visibleCount - 1))));
  state.frameIndex = Math.max(0, Math.min(frames.length - 1, zone.startIndex + localIndex));
  el.timeline.value = String(state.frameIndex);
  if (state.isPlaying) startPlayback();
  render();
});
window.addEventListener("keydown", (event) => {
  if (event.code !== "Space") return;
  if (event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement || event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLButtonElement) return;
  event.preventDefault();
  togglePlayback();
});
window.addEventListener("resize", render);

initAlgorithms();
loadProfilesFromStorage();
populateProfileSelect();
applyPreferredProfile({ quiet: true });
setActiveTab("tuning");
syncSessionMeta();
render();
