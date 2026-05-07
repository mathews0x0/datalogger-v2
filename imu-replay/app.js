import { parseSessionCsv, processors } from "./processor.js";

const el = {
  csvFile: document.getElementById("csvFile"),
  csvFileName: document.getElementById("csvFileName"),
  algorithmSelect: document.getElementById("algorithmSelect"),
  minSpeed: document.getElementById("minSpeed"),
  smoothingMs: document.getElementById("smoothingMs"),
  leanRateLimit: document.getElementById("leanRateLimit"),
  upMinG: document.getElementById("upMinG"),
  leanGain: document.getElementById("leanGain"),
  upFloorG: document.getElementById("upFloorG"),
  accMagTol: document.getElementById("accMagTol"),
  playbackRate: document.getElementById("playbackRate"),
  enableHampelFilter: document.getElementById("enableHampelFilter"),
  enableMovingAverage: document.getElementById("enableMovingAverage"),
  maskLowSpeed: document.getElementById("maskLowSpeed"),
  maskAccelMagnitude: document.getElementById("maskAccelMagnitude"),
  maskPitch: document.getElementById("maskPitch"),
  maskLongitudinalAccel: document.getElementById("maskLongitudinalAccel"),
  maskWeakTurnEvidence: document.getElementById("maskWeakTurnEvidence"),
  maskLateralVibration: document.getElementById("maskLateralVibration"),
  maskVerticalVibration: document.getElementById("maskVerticalVibration"),
  holdMaskedLean: document.getElementById("holdMaskedLean"),
  processBtn: document.getElementById("processBtn"),
  loadDemoBtn: document.getElementById("loadDemoBtn"),
  lapSelect: document.getElementById("lapSelect"),
  playBtn: document.getElementById("playBtn"),
  pauseBtn: document.getElementById("pauseBtn"),
  resetBtn: document.getElementById("resetBtn"),
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
  viewFrames: null,
  laps: [],
  selectedLap: "all",
  frameIndex: 0,
  playing: false,
  lastTick: 0,
  playbackTickMs: 0,
  animationId: 0,
  bounds: null,
};

function initAlgorithms() {
  Object.values(processors).forEach((processor) => {
    const option = document.createElement("option");
    option.value = processor.id;
    option.textContent = processor.label;
    el.algorithmSelect.appendChild(option);
  });
  el.algorithmSelect.value = "accelOnlyV1";
}

function applyAlgorithmDefaults() {
  if (el.algorithmSelect.value !== "calibratedV2") return;
  el.minSpeed.value = "0";
  el.smoothingMs.value = "100";
  el.leanRateLimit.value = "90";
  el.upMinG.value = "0.65";
  el.leanGain.value = "1";
  el.upFloorG.value = "0.15";
  el.accMagTol.value = "0.16";
  el.enableHampelFilter.checked = false;
  el.enableMovingAverage.checked = false;
  el.maskLowSpeed.checked = false;
  el.maskAccelMagnitude.checked = false;
  el.maskPitch.checked = false;
  el.maskLongitudinalAccel.checked = false;
  el.maskWeakTurnEvidence.checked = false;
  el.maskLateralVibration.checked = false;
  el.maskVerticalVibration.checked = false;
  el.holdMaskedLean.checked = false;
}

function currentConfig() {
  return {
    minSpeed: Number(el.minSpeed.value) || 0,
    smoothingMs: Number(el.smoothingMs.value) || 750,
    leanRateLimit: Number(el.leanRateLimit.value) || 120,
    upMinG: Number(el.upMinG.value) || 0.72,
    leanGain: Number(el.leanGain.value) || 1,
    upFloorG: Number(el.upFloorG.value) || 0.15,
    accMagTol: Number(el.accMagTol.value) || 0.35,
    lowSpeedKmh: 15,
    turnSpeedKmh: 45,
    pitchWarnDeg: 18,
    fusionTauSec: 0.45,
    mahonyKp: 0.5,
    mahonyKi: 0.02,
    vibrationWindowMs: 500,
    lateralVibeThresholdG: 0.06,
    verticalVibeThresholdG: 0.16,
    enableHampelFilter: el.enableHampelFilter.checked,
    enableMovingAverage: el.enableMovingAverage.checked,
    maskLowSpeed: el.maskLowSpeed.checked,
    maskAccelMagnitude: el.maskAccelMagnitude.checked,
    maskPitch: el.maskPitch.checked,
    maskLongitudinalAccel: el.maskLongitudinalAccel.checked,
    maskWeakTurnEvidence: el.maskWeakTurnEvidence.checked,
    maskLateralVibration: el.maskLateralVibration.checked,
    maskVerticalVibration: el.maskVerticalVibration.checked,
    holdMaskedLean: el.holdMaskedLean.checked,
  };
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
  setStatus(`Loaded ${name}\nRows: ${state.session.rows.length}`);
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
  const processor = processors[el.algorithmSelect.value];
  const result = processor.process(state.session, currentConfig());
  state.processed = result;
  state.laps = detectLaps(result.frames);
  populateLapSelect(state.laps);
  const defaultLap = state.laps.length >= 3 ? "lap-3" : state.laps.length ? "lap-1" : "all";
  el.lapSelect.value = defaultLap;
  applyLapSelection(defaultLap);
  setStatus(formatStats(result));
  const repairNotes = formatRepairs(result.stats.repairs);
  const lapNotes = state.laps.length ? `\nDetected laps: ${state.laps.length}` : "";
  setNotes(`${processor.description}\n\nAlgorithm: ${result.algorithm}\nProfile: ${result.stats.profileName}\nLean-valid fraction: ${(result.stats.validLeanFraction * 100).toFixed(1)}%${repairNotes ? `\nRepairs: ${repairNotes}` : ""}${lapNotes}\nEnabled options: ${enabledOptionLabels(currentConfig()).join(", ") || "none"}`);
  render();
}

function enabledOptionLabels(config) {
  const labels = [];
  if (config.enableHampelFilter) labels.push("Hampel");
  if (config.enableMovingAverage) labels.push("MovingAvg");
  if (config.maskLowSpeed) labels.push("LowSpeedMask");
  if (config.maskAccelMagnitude) labels.push("AccelMagMask");
  if (config.maskPitch) labels.push("PitchMask");
  if (config.maskLongitudinalAccel) labels.push("LongAccelMask");
  if (config.maskWeakTurnEvidence) labels.push("WeakTurnMask");
  if (config.maskLateralVibration) labels.push("LatVibeMask");
  if (config.maskVerticalVibration) labels.push("VertVibeMask");
  if (config.holdMaskedLean) labels.push("HoldMaskedLean");
  return labels;
}

function computeBounds(frames) {
  if (!frames?.length) return null;
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

function formatStats(result) {
  if (result.stats?.error) return result.stats.error;
  const lines = [
    `Algorithm: ${result.algorithm}`,
    `Frames: ${result.stats.imuFrames}`,
    `GPS points: ${result.stats.gpsPoints}`,
    `Distance: ${(result.stats.totalDistanceM / 1000).toFixed(2)} km`,
    `Median dt: ${result.stats.medianDtMs.toFixed(1)} ms`,
    `Max lean: ${result.stats.maxLeanDeg.toFixed(1)} deg`,
    `Mean confidence: ${(result.stats.meanConfidence * 100).toFixed(1)}%`,
    `Low-confidence frac: ${(result.stats.lowConfidenceFraction * 100).toFixed(1)}%`,
    `Profile: ${result.stats.profileName} (${result.stats.profileQuality ?? "n/a"})`,
  ];
  const repairs = formatRepairs(result.stats.repairs);
  if (repairs) lines.push(`Repairs: ${repairs}`);
  if (result.stats.axisName) lines.push(`Axis: ${result.stats.axisName} (${result.stats.axisCorrelation})`);
  return lines.join("\n");
}

function formatRepairs(repairs) {
  if (!repairs?.length) return "";
  return repairs.map((repair) => {
    if (repair.type === "bmi323_gyro_range_scale") {
      const rate = repair.detectedSampleRateHz ?? repair.detected_sample_rate_hz ?? "n/a";
      const p99 = repair.gyroAbsP99Before ?? repair.gyro_abs_p99_before ?? "n/a";
      return `BMI323 gyro x${repair.scale} (${rate}Hz, p99 ${p99})`;
    }
    return repair.type || "unknown";
  }).join("; ");
}

function currentFrames() {
  return state.viewFrames || state.processed?.frames || [];
}

function frameAt(index) {
  return currentFrames()[index] || null;
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
    if (i > 0) {
      const dx = sampled[i].x - sampled[i - 1].x;
      const dy = sampled[i].y - sampled[i - 1].y;
      cumulativeDist.push(cumulativeDist[i - 1] + Math.hypot(dx, dy));
    }
  }

  const diag = Math.hypot(maxX - minX, maxY - minY);
  const radiusM = Math.max(10, Math.min(25, diag * 0.015));
  const headingTolDeg = 40;
  const minLapSec = 20;
  const minGap = Math.max(20, Math.round(minLapSec / (dtSec * stride)));
  const skip = Math.max(0, Math.round(10 / (dtSec * stride)));

  let bestAnchor = -1;
  let bestCount = 0;
  for (let i = skip; i < sampled.length - minGap; i += 1) {
    let count = 0;
    let lastHit = -minGap;
    for (let j = i + minGap; j < sampled.length; j += 1) {
      const dx = sampled[j].x - sampled[i].x;
      const dy = sampled[j].y - sampled[i].y;
      const dist = Math.hypot(dx, dy);
      if (dist > radiusM) continue;
      if (angularDiffDeg(sampled[j].headingDeg, sampled[i].headingDeg) > headingTolDeg) continue;
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
    const dx = sampled[j].x - sampled[bestAnchor].x;
    const dy = sampled[j].y - sampled[bestAnchor].y;
    const dist = Math.hypot(dx, dy);
    if (dist > radiusM) continue;
    if (angularDiffDeg(sampled[j].headingDeg, sampled[bestAnchor].headingDeg) > headingTolDeg) continue;
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
  state.playbackTickMs = currentFrames()[0]?.tickMs || 0;
  el.timeline.min = 0;
  el.timeline.max = Math.max(0, currentFrames().length - 1);
  el.timeline.value = "0";
  state.bounds = computeBounds(currentFrames());
}

function render() {
  resizeCanvasIfNeeded();
  ctx.clearRect(0, 0, el.stage.width, el.stage.height);
  drawBackground();
  if (!currentFrames().length || !state.bounds) {
    drawEmptyState();
    return;
  }
  drawTrack();
  drawHud(frameAt(state.frameIndex));
  drawLeanComparisonGraph();
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

  ctx.strokeStyle = "rgba(41, 37, 31, 0.05)";
  ctx.lineWidth = 1;
  const spacing = 80 * window.devicePixelRatio;
  for (let x = 0; x < el.stage.width; x += spacing) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, el.stage.height);
    ctx.stroke();
  }
  for (let y = 0; y < el.stage.height; y += spacing) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(el.stage.width, y);
    ctx.stroke();
  }
}

function toScreen(frame) {
  const pad = 90 * window.devicePixelRatio;
  const width = el.stage.width - pad * 2;
  const height = el.stage.height - pad * 2;
  const { minX, maxX, minY, maxY } = state.bounds;
  const spanX = Math.max(1, maxX - minX);
  const spanY = Math.max(1, maxY - minY);
  const scale = Math.min(width / spanX, height / spanY);
  const offsetX = pad + (width - spanX * scale) / 2;
  const offsetY = pad + (height - spanY * scale) / 2;
  return {
    x: offsetX + (frame.x - minX) * scale,
    y: offsetY + (frame.y - minY) * scale,
    scale,
  };
}

function drawTrack() {
  const frames = currentFrames();
  if (frames.length < 2) return;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";

  for (let i = 1; i < frames.length; i += 1) {
    const prev = toScreen(frames[i - 1]);
    const cur = toScreen(frames[i]);
    const alpha = Math.max(0.18, Math.min(0.85, frames[i].confidence));
    ctx.strokeStyle = `rgba(94, 102, 104, ${alpha})`;
    ctx.lineWidth = Math.max(2, 4 * prev.scale / 120);
    ctx.beginPath();
    ctx.moveTo(prev.x, prev.y);
    ctx.lineTo(cur.x, cur.y);
    ctx.stroke();
  }

  const current = frames[state.frameIndex];
  const screen = toScreen(current);
  drawBike(screen.x, screen.y, current.headingDeg, current.leanDeg, current.confidence);

  ctx.fillStyle = "#0d6c74";
  const start = toScreen(frames[0]);
  ctx.beginPath();
  ctx.arc(start.x, start.y, 7 * window.devicePixelRatio, 0, Math.PI * 2);
  ctx.fill();
}

function drawBike(x, y, headingDeg, leanDeg, confidence) {
  const size = 18 * window.devicePixelRatio;
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate((headingDeg * Math.PI) / 180);

  ctx.fillStyle = confidence > 0.5 ? "#181411" : "rgba(24, 20, 17, 0.4)";
  ctx.beginPath();
  ctx.moveTo(0, -size);
  ctx.lineTo(size * 0.62, size * 0.8);
  ctx.lineTo(0, size * 0.35);
  ctx.lineTo(-size * 0.62, size * 0.8);
  ctx.closePath();
  ctx.fill();

  ctx.rotate((leanDeg * Math.PI) / 180);
  ctx.strokeStyle = leanDeg >= 0 ? "#1a8f5b" : "#bb3d2f";
  ctx.lineWidth = 3 * window.devicePixelRatio;
  ctx.beginPath();
  ctx.moveTo(0, size * 0.15);
  ctx.lineTo(0, -size * 1.25);
  ctx.stroke();
  ctx.restore();
}

function drawHud(frame) {
  if (!frame) return;
  el.leanValue.textContent = `${frame.leanDeg.toFixed(1)} deg`;
  el.speedValue.textContent = `${frame.speedKmh.toFixed(1)} km/h`;
  const lapLabel = state.selectedLap === "all" ? "Full Session" : (state.laps.find((lap) => lap.id === state.selectedLap)?.label || "Lap");
  const gpsLeanText = frame.gpsLeanDeg == null ? "" : ` | GPS lean ${frame.gpsLeanDeg.toFixed(1)} deg`;
  el.frameMeta.textContent = `${lapLabel} | Tick ${frame.tickMs} | GPS ${frame.lat.toFixed(6)}, ${frame.lon.toFixed(6)} | Heading ${frame.headingDeg.toFixed(1)} deg | Confidence ${(frame.confidence * 100).toFixed(0)}%${gpsLeanText}`;

  const pad = 30 * window.devicePixelRatio;
  const panelW = 320 * window.devicePixelRatio;
  const panelH = 92 * window.devicePixelRatio;
  const x = el.stage.width - panelW - pad;
  const y = pad;

  ctx.fillStyle = "rgba(255, 250, 240, 0.92)";
  roundRect(ctx, x, y, panelW, panelH, 18 * window.devicePixelRatio, true);
  ctx.fillStyle = "#29251f";
  ctx.font = `${18 * window.devicePixelRatio}px sans-serif`;
  ctx.fillText("Replay HUD", x + 18 * window.devicePixelRatio, y + 28 * window.devicePixelRatio);
  ctx.font = `${14 * window.devicePixelRatio}px sans-serif`;
  ctx.fillText(`Lean ${frame.leanDeg.toFixed(1)} deg`, x + 18 * window.devicePixelRatio, y + 56 * window.devicePixelRatio);
  const gpsLean = frame.gpsLeanDeg == null ? "" : ` | GPS ${frame.gpsLeanDeg.toFixed(1)} deg`;
  ctx.fillText(`Speed ${frame.speedKmh.toFixed(1)} km/h${gpsLean}`, x + 18 * window.devicePixelRatio, y + 80 * window.devicePixelRatio);

  const gaugeX = x + 205 * window.devicePixelRatio;
  const gaugeY = y + 68 * window.devicePixelRatio;
  const gaugeR = 34 * window.devicePixelRatio;
  ctx.strokeStyle = "rgba(41, 37, 31, 0.18)";
  ctx.lineWidth = 8 * window.devicePixelRatio;
  ctx.beginPath();
  ctx.arc(gaugeX, gaugeY, gaugeR, Math.PI * 0.8, Math.PI * 2.2);
  ctx.stroke();

  const leanNorm = Math.max(-1, Math.min(1, frame.leanDeg / 45));
  ctx.strokeStyle = frame.leanDeg >= 0 ? "#1a8f5b" : "#bb3d2f";
  ctx.beginPath();
  ctx.arc(gaugeX, gaugeY, gaugeR, Math.PI * 1.5, Math.PI * (1.5 + leanNorm * 0.7));
  ctx.stroke();
}

function drawLeanComparisonGraph() {
  const frames = currentFrames();
  if (!frames.length || frames[0].gpsLeanDeg == null) return;
  const dpr = window.devicePixelRatio;
  const x = 28 * dpr;
  const y = el.stage.height - 168 * dpr;
  const w = el.stage.width - 56 * dpr;
  const h = 128 * dpr;
  const pad = 16 * dpr;
  const left = x + pad;
  const right = x + w - pad;
  const top = y + pad;
  const bottom = y + h - pad;
  const chartW = Math.max(1, right - left);
  const chartH = Math.max(1, bottom - top);
  const maxAbs = Math.max(20, ...frames.flatMap((frame) => [Math.abs(frame.leanDeg), Math.abs(frame.gpsLeanDeg || 0)]));
  const xFor = (index) => left + (index / Math.max(1, frames.length - 1)) * chartW;
  const yFor = (value) => top + ((maxAbs - value) / (maxAbs * 2)) * chartH;

  ctx.fillStyle = "rgba(255, 250, 240, 0.92)";
  roundRect(ctx, x, y, w, h, 12 * dpr, true);
  ctx.strokeStyle = "rgba(41, 37, 31, 0.16)";
  ctx.lineWidth = 1 * dpr;
  ctx.strokeRect(x, y, w, h);

  ctx.strokeStyle = "rgba(41, 37, 31, 0.25)";
  ctx.lineWidth = 1 * dpr;
  ctx.beginPath();
  ctx.moveTo(left, yFor(0));
  ctx.lineTo(right, yFor(0));
  ctx.stroke();

  const drawSeries = (getter, color, lineWidth) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth * dpr;
    ctx.beginPath();
    frames.forEach((frame, index) => {
      const px = xFor(index);
      const py = yFor(getter(frame));
      if (index === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.stroke();
  };
  drawSeries((frame) => frame.gpsLeanDeg || 0, "#0b5cad", 1.7);
  drawSeries((frame) => frame.leanDeg, "#d13f2f", 1.5);

  const markerX = xFor(state.frameIndex);
  ctx.strokeStyle = "rgba(20, 20, 20, 0.55)";
  ctx.lineWidth = 1 * dpr;
  ctx.beginPath();
  ctx.moveTo(markerX, top);
  ctx.lineTo(markerX, bottom);
  ctx.stroke();

  ctx.fillStyle = "#29251f";
  ctx.font = `${12 * dpr}px sans-serif`;
  ctx.fillText("Lean overlay", x + 12 * dpr, y + 18 * dpr);
  ctx.fillStyle = "#0b5cad";
  ctx.fillText("GPS", x + 112 * dpr, y + 18 * dpr);
  ctx.fillStyle = "#d13f2f";
  ctx.fillText("Attitude", x + 154 * dpr, y + 18 * dpr);
}

function drawEmptyState() {
  ctx.fillStyle = "rgba(41, 37, 31, 0.55)";
  ctx.font = `${24 * window.devicePixelRatio}px sans-serif`;
  ctx.fillText("Load and process a session CSV to start replay.", 80 * window.devicePixelRatio, 100 * window.devicePixelRatio);
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

function stepPlayback(ts) {
  const frames = currentFrames();
  if (!state.playing || !frames.length) return;
  if (!state.lastTick) state.lastTick = ts;
  const delta = ts - state.lastTick;
  state.lastTick = ts;
  const advanceMs = delta * (Number(el.playbackRate.value) || 1);
  let nextIndex = state.frameIndex;
  if (!state.playbackTickMs) state.playbackTickMs = frames[state.frameIndex].tickMs;
  state.playbackTickMs += advanceMs;
  while (nextIndex + 1 < frames.length && frames[nextIndex + 1].tickMs <= state.playbackTickMs) {
    nextIndex += 1;
  }
  state.frameIndex = nextIndex;
  el.timeline.value = String(nextIndex);
  render();
  if (nextIndex >= frames.length - 1) {
    state.playing = false;
    state.lastTick = 0;
    return;
  }
  state.animationId = requestAnimationFrame(stepPlayback);
}

function play() {
  if (!currentFrames().length) return;
  state.playing = true;
  state.playbackTickMs = currentFrames()[state.frameIndex]?.tickMs || 0;
  state.lastTick = 0;
  cancelAnimationFrame(state.animationId);
  state.animationId = requestAnimationFrame(stepPlayback);
}

function pause() {
  state.playing = false;
  state.lastTick = 0;
  cancelAnimationFrame(state.animationId);
}

function reset() {
  pause();
  state.frameIndex = 0;
  state.playbackTickMs = currentFrames()[0]?.tickMs || 0;
  el.timeline.value = "0";
  render();
}

el.csvFile.addEventListener("change", async (event) => {
  const [file] = event.target.files;
  if (file) await readFile(file);
});

el.loadDemoBtn.addEventListener("click", () => {
  loadDemo().catch((err) => setStatus(`Demo load failed: ${err.message}`));
});
el.processBtn.addEventListener("click", processSession);
el.algorithmSelect.addEventListener("change", applyAlgorithmDefaults);
el.lapSelect.addEventListener("change", () => {
  applyLapSelection(el.lapSelect.value);
  render();
});
el.playBtn.addEventListener("click", play);
el.pauseBtn.addEventListener("click", pause);
el.resetBtn.addEventListener("click", reset);
el.timeline.addEventListener("input", () => {
  state.frameIndex = Number(el.timeline.value) || 0;
  state.playbackTickMs = currentFrames()[state.frameIndex]?.tickMs || 0;
  render();
});
window.addEventListener("resize", render);

initAlgorithms();
render();
