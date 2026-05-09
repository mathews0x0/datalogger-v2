import { parseSessionCsv, processors } from "./processor.js";

const el = {
  csvFile: document.getElementById("csvFile"),
  csvFileName: document.getElementById("csvFileName"),
  algorithmSelect: document.getElementById("algorithmSelect"),
  paramFields: document.getElementById("paramFields"),
  processBtn: document.getElementById("processBtn"),
  resetParamsBtn: document.getElementById("resetParamsBtn"),
  loadDemoBtn: document.getElementById("loadDemoBtn"),
  profileSelect: document.getElementById("profileSelect"),
  profileName: document.getElementById("profileName"),
  saveProfileBtn: document.getElementById("saveProfileBtn"),
  loadProfileBtn: document.getElementById("loadProfileBtn"),
  deleteProfileBtn: document.getElementById("deleteProfileBtn"),
  lapSelect: document.getElementById("lapSelect"),
  timeline: document.getElementById("timeline"),
  frameMeta: document.getElementById("frameMeta"),
  leanValue: document.getElementById("leanValue"),
  speedValue: document.getElementById("speedValue"),
  algorithmNotes: document.getElementById("algorithmNotes"),
  status: document.getElementById("status"),
  stage: document.getElementById("stage"),
};

const ctx = el.stage.getContext("2d");

const state = {
  rawText: "",
  session: null,
  processed: null,
  viewFrames: [],
  laps: [],
  selectedLap: "all",
  frameIndex: 0,
  graphHitZones: [],
  profiles: [],
};

const PROFILE_STORAGE_KEY = "imuReplayTuningProfiles.v1";

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

function processorLabel(id) {
  return processors[id]?.label || id || "Unknown";
}

function populateProfileSelect(selectedId = el.profileSelect.value) {
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

function syncProfileName() {
  const selected = state.profiles.find((profile) => profile.id === el.profileSelect.value);
  if (selected) {
    el.profileName.value = selected.name;
  } else {
    el.profileName.value = "";
  }
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

function renderParamFields() {
  const processor = activeProcessor();
  el.paramFields.innerHTML = "";
  for (const param of processor.params || []) {
    const label = document.createElement("label");
    label.className = "field";
    label.dataset.param = param.key;

    const caption = document.createElement("span");
    caption.textContent = param.label;
    label.appendChild(caption);

    const input = document.createElement("input");
    input.id = `param-${param.key}`;
    input.dataset.key = param.key;
    input.type = param.type || "number";
    input.step = param.step ?? "any";
    input.value = param.default;
    input.addEventListener("input", () => {
      if (state.session) processSession();
      else render();
    });
    label.appendChild(input);
    el.paramFields.appendChild(label);
  }
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
  populateProfileSelect(profile.id);
  setStatus(`Saved profile "${profile.name}" for ${processorLabel(profile.algorithmId)}.`);
}

function loadSelectedProfile() {
  const profile = state.profiles.find((item) => item.id === el.profileSelect.value);
  if (!profile) {
    setStatus("Select a saved profile to load.");
    return;
  }
  if (!processors[profile.algorithmId]) {
    setStatus(`Profile "${profile.name}" references a missing algorithm: ${profile.algorithmId}`);
    return;
  }

  el.algorithmSelect.value = profile.algorithmId;
  renderParamFields();
  setParamValues(profile.params);
  el.profileName.value = profile.name;
  if (state.session) {
    processSession();
  } else {
    render();
    setStatus(`Loaded profile "${profile.name}". Load a session CSV to process it.`);
  }
}

function deleteSelectedProfile() {
  const profile = state.profiles.find((item) => item.id === el.profileSelect.value);
  if (!profile) {
    setStatus("Select a saved profile to delete.");
    return;
  }
  state.profiles = state.profiles.filter((item) => item.id !== profile.id);
  if (!saveProfilesToStorage()) return;
  populateProfileSelect("");
  el.profileName.value = "";
  setStatus(`Deleted profile "${profile.name}".`);
}

function resetParams() {
  renderParamFields();
  if (state.session) processSession();
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

function loadText(name, text) {
  state.rawText = text;
  state.session = parseSessionCsv(text);
  el.csvFileName.textContent = name;
  state.processed = null;
  state.viewFrames = [];
  setStatus(`Loaded ${name}\nRows: ${state.session.rows.length}`);
  render();
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

  const processor = activeProcessor();
  const config = currentConfig();
  const result = processor.process(state.session, config);
  state.processed = result;
  state.laps = detectLaps(result.frames);
  populateLapSelect(state.laps);
  const defaultLap = state.laps.length >= 3 ? "lap-3" : state.laps.length ? "lap-1" : "all";
  el.lapSelect.value = defaultLap;
  applyLapSelection(defaultLap);

  const scores = scoreFrames(currentFrames(), config.gpsLagMs || 0);
  setStatus(formatStats(result, scores));
  setNotes(formatNotes(processor, result, config, scores));
  render();
}

function formatNotes(processor, result, config, scores) {
  if (result.stats?.error) return result.stats.error;
  const repairs = formatRepairs(result.stats.repairs);
  const lines = [
    processor.description,
    "",
    `Algorithm: ${result.algorithm}`,
    `GPS lag: ${config.gpsLagMs || 0} ms`,
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
  return state.viewFrames || [];
}

function frameAt(index) {
  return currentFrames()[index] || null;
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
  const lagMs = Number(state.processed?.config?.gpsLagMs || 0);
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
  const allFrames = state.processed?.frames || [];
  if (selection === "all" || !state.laps.length) {
    state.viewFrames = allFrames;
  } else {
    const lap = state.laps.find((entry) => entry.id === selection);
    state.viewFrames = lap ? allFrames.slice(lap.start, lap.end + 1) : allFrames;
  }
  state.frameIndex = 0;
  state.graphHitZones = [];
  el.timeline.min = 0;
  el.timeline.max = Math.max(0, currentFrames().length - 1);
  el.timeline.value = "0";
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
  el.leanValue.textContent = `${frame.leanDeg.toFixed(1)} deg`;
  el.speedValue.textContent = `${frame.speedKmh.toFixed(1)} km/h`;
  const lapLabel = state.selectedLap === "all" ? "Full Session" : (state.laps.find((lap) => lap.id === state.selectedLap)?.label || "Lap");
  el.frameMeta.textContent = `${lapLabel} | Tick ${frame.tickMs} | Lean IMU/GPS ${frame.leanDeg.toFixed(1)} / ${gpsLean.toFixed(1)} deg | Long IMU/GPS ${imuLong.toFixed(3)} / ${gpsLong.toFixed(3)} g`;
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
  const dpr = window.devicePixelRatio;
  const margin = 32 * dpr;
  const gap = 20 * dpr;
  const trackH = Math.max(130 * dpr, Math.min(210 * dpr, el.stage.height * 0.22));
  const hudReserve = 78 * dpr;
  const graphW = el.stage.width - (margin * 2);
  const graphH = (el.stage.height - (margin * 2) - (gap * 2) - hudReserve - trackH) / 2;
  state.graphHitZones = [];
  graphDefinitions(frames).forEach((graph, index) => {
    const y = margin + index * (graphH + gap);
    const zone = drawComparisonGraph(frames, graph, margin, y, graphW, graphH);
    state.graphHitZones.push(zone);
  });
}

function drawComparisonGraph(frames, graph, x, y, w, h) {
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
  const values = frames.flatMap((frame) => [graph.gpsValue(frame), graph.imuValue(frame)]);
  const maxValue = Math.max(graph.minScale, ...values.map((value) => Math.abs(value)));
  const xFor = (index) => left + (index / Math.max(1, frames.length - 1)) * chartW;
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

  drawSeries(frames, xFor, yFor, graph.gpsValue, graph.gpsColor, 2.0 * dpr);
  drawSeries(frames, xFor, yFor, graph.imuValue, graph.imuColor, 1.7 * dpr);

  const markerX = xFor(state.frameIndex);
  ctx.strokeStyle = "rgba(20, 20, 20, 0.55)";
  ctx.lineWidth = 1 * dpr;
  ctx.beginPath();
  ctx.moveTo(markerX, top);
  ctx.lineTo(markerX, bottom);
  ctx.stroke();

  ctx.fillStyle = "#29251f";
  ctx.font = `${14 * dpr}px sans-serif`;
  ctx.fillText(graph.title, x + 18 * dpr, y + 24 * dpr);
  ctx.fillStyle = graph.gpsColor;
  ctx.fillText(graph.gpsLabel, x + 330 * dpr, y + 24 * dpr);
  ctx.fillStyle = graph.imuColor;
  ctx.fillText(graph.imuLabel, x + 386 * dpr, y + 24 * dpr);
  ctx.fillStyle = "rgba(41, 37, 31, 0.72)";
  ctx.fillText(`+${maxValue.toFixed(graph.unit === "g" ? 2 : 0)} ${graph.unit}`, x + 10 * dpr, top + 8 * dpr);
  ctx.fillText(`-${maxValue.toFixed(graph.unit === "g" ? 2 : 0)} ${graph.unit}`, x + 10 * dpr, bottom);
  ctx.fillText(graph.positiveLabel, right - 60 * dpr, top + 12 * dpr);
  ctx.fillText(graph.negativeLabel, right - 60 * dpr, bottom - 6 * dpr);
  return { left, right, top, bottom };
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
  const trackH = Math.max(130 * dpr, Math.min(210 * dpr, el.stage.height * 0.22));
  const w = el.stage.width - (margin * 2);
  const h = trackH;
  const x = margin;
  const y = el.stage.height - margin - trackH;
  const pad = 18 * dpr;
  const bounds = trackBounds(frames);
  const spanX = Math.max(1, bounds.maxX - bounds.minX);
  const spanY = Math.max(1, bounds.maxY - bounds.minY);
  const scale = Math.min((w - pad * 2) / spanX, (h - pad * 2) / spanY);
  const mapX = (frame) => x + (w / 2) + ((frame.x - ((bounds.minX + bounds.maxX) / 2)) * scale);
  const mapY = (frame) => y + (h / 2) + ((frame.y - ((bounds.minY + bounds.maxY) / 2)) * scale);

  ctx.fillStyle = "rgba(255, 250, 240, 0.94)";
  roundRect(ctx, x, y, w, h, 18 * dpr, true);
  ctx.strokeStyle = "rgba(41, 37, 31, 0.14)";
  ctx.lineWidth = 1 * dpr;
  ctx.strokeRect(x, y, w, h);

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
  const size = 15 * dpr;
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
el.processBtn.addEventListener("click", processSession);
el.resetParamsBtn.addEventListener("click", resetParams);
el.profileSelect.addEventListener("change", syncProfileName);
el.saveProfileBtn.addEventListener("click", saveProfile);
el.loadProfileBtn.addEventListener("click", loadSelectedProfile);
el.deleteProfileBtn.addEventListener("click", deleteSelectedProfile);
el.algorithmSelect.addEventListener("change", () => {
  renderParamFields();
  if (state.session) processSession();
});
el.lapSelect.addEventListener("change", () => {
  applyLapSelection(el.lapSelect.value);
  render();
});
el.timeline.addEventListener("input", () => {
  state.frameIndex = Number(el.timeline.value) || 0;
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
  state.frameIndex = Math.max(0, Math.min(frames.length - 1, Math.round(ratio * (frames.length - 1))));
  el.timeline.value = String(state.frameIndex);
  render();
});
window.addEventListener("resize", render);

initAlgorithms();
loadProfilesFromStorage();
populateProfileSelect();
render();
