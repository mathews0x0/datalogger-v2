const state = {
  layoutFile: null,
  layoutImage: null,
  layoutImageUrl: "",
  layoutDataUrl: "",
  layoutSvgText: "",
  layoutWidth: 0,
  layoutHeight: 0,
  layoutPixelPoints: [],
  telemetryFile: null,
  telemetryGeoReference: null,
  telemetryPointsMeters: [],
  telemetryWorldPoints: [],
  anchors: [],
  sectors: [],
  selectedLapTrace: [],
  selectedAnchorIndex: -1,
  anchorHistory: [],
  layoutTransform: {
    translateX: 0,
    translateY: 0,
    scale: 1,
    rotationDeg: 0,
    pivotX: 0,
    pivotY: 0,
  },
  telemetryAutoAlign: null,
  view: {
    zoom: 1,
    offsetX: 120,
    offsetY: 80,
  },
  drag: {
    active: false,
    mode: null,
    startX: 0,
    startY: 0,
    originX: 0,
    originY: 0,
  },
  startFinishCaptureActive: false,
  startFinishDraft: [],
};

const els = {
  layoutFile: document.getElementById("layoutFile"),
  layoutFileName: document.getElementById("layoutFileName"),
  csvFile: document.getElementById("csvFile"),
  csvFileName: document.getElementById("csvFileName"),
  minSpeed: document.getElementById("minSpeed"),
  darkThreshold: document.getElementById("darkThreshold"),
  autoAlignBtn: document.getElementById("autoAlignBtn"),
  translateX: document.getElementById("translateX"),
  translateY: document.getElementById("translateY"),
  scale: document.getElementById("scale"),
  rotationDeg: document.getElementById("rotationDeg"),
  pivotX: document.getElementById("pivotX"),
  pivotY: document.getElementById("pivotY"),
  centerPivotBtn: document.getElementById("centerPivotBtn"),
  resetTransformBtn: document.getElementById("resetTransformBtn"),
  fitViewBtn: document.getElementById("fitViewBtn"),
  resetViewBtn: document.getElementById("resetViewBtn"),
  dragMode: document.getElementById("dragMode"),
  anchorMode: document.getElementById("anchorMode"),
  createStartFinishBtn: document.getElementById("createStartFinishBtn"),
  clearStartFinishBtn: document.getElementById("clearStartFinishBtn"),
  undoAnchorBtn: document.getElementById("undoAnchorBtn"),
  deleteAnchorBtn: document.getElementById("deleteAnchorBtn"),
  clearAnchorsBtn: document.getElementById("clearAnchorsBtn"),
  anchorLabel: document.getElementById("anchorLabel"),
  anchorType: document.getElementById("anchorType"),
  sectorCount: document.getElementById("sectorCount"),
  sectorRadius: document.getElementById("sectorRadius"),
  autoAddSectorsBtn: document.getElementById("autoAddSectorsBtn"),
  updateSectorRadiusBtn: document.getElementById("updateSectorRadiusBtn"),
  sectorList: document.getElementById("sectorList"),
  exportJsonBtn: document.getElementById("exportJsonBtn"),
  exportSvgBtn: document.getElementById("exportSvgBtn"),
  exportPackageBtn: document.getElementById("exportPackageBtn"),
  anchorList: document.getElementById("anchorList"),
  status: document.getElementById("status"),
  stage: document.getElementById("stage"),
};

const ctx = els.stage.getContext("2d");

function setStatus(message) {
  els.status.textContent = message;
}

function downloadBlob(filename, blob) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 500);
}

function cloneAnchors() {
  return state.anchors.map((anchor) => ({
    id: anchor.id,
    name: anchor.name || "",
    type: anchor.type || "",
    layoutPoint: { ...anchor.layoutPoint },
  }));
}

function isStartFinishAnchor(anchor) {
  const label = `${anchor.name || ""} ${anchor.type || ""}`.replace(/[_-]+/g, " ").toLowerCase();
  return label.includes("start finish");
}

function pushAnchorHistory() {
  state.anchorHistory.push({
    anchors: cloneAnchors(),
    selectedAnchorIndex: state.selectedAnchorIndex,
  });
  if (state.anchorHistory.length > 50) {
    state.anchorHistory.shift();
  }
}

function restoreAnchorSnapshot(snapshot) {
  state.anchors = snapshot.anchors.map((anchor) => ({
    ...anchor,
    layoutPoint: { ...anchor.layoutPoint },
  }));
  state.startFinishCaptureActive = false;
  state.startFinishDraft = [];
  state.selectedAnchorIndex = Math.min(snapshot.selectedAnchorIndex, state.anchors.length - 1);
  syncAnchorEditor();
  updateAnchorList();
  redraw();
}

function undoAnchorChange() {
  const snapshot = state.anchorHistory.pop();
  if (!snapshot) return;
  restoreAnchorSnapshot(snapshot);
}

function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/);
  const headers = lines[0].split(",");
  return lines.slice(1).map((line) => {
    const values = line.split(",");
    const row = {};
    headers.forEach((key, idx) => {
      row[key] = values[idx] ?? "";
    });
    return row;
  });
}

function telemetryToMeters(rows, minSpeed) {
  const gps = rows.filter((row) => {
    return row.row_type === "G" && row.lat && row.lon && Number(row.speed || 0) >= minSpeed;
  });
  if (!gps.length) return { points: [], geoReference: null };
  const lat0 = gps.reduce((sum, row) => sum + Number(row.lat), 0) / gps.length;
  const lon0 = gps.reduce((sum, row) => sum + Number(row.lon), 0) / gps.length;
  const metersPerDegLat = 111320;
  const metersPerDegLon = 111320 * Math.cos((lat0 * Math.PI) / 180);
  return {
    geoReference: { lat0, lon0, metersPerDegLat, metersPerDegLon },
    points: gps.map((row) => ({
      x: (Number(row.lon) - lon0) * metersPerDegLon,
      y: -(Number(row.lat) - lat0) * metersPerDegLat,
      speed: Number(row.speed || 0),
      lat: Number(row.lat),
      lon: Number(row.lon),
    })),
  };
}

function pointCentroid(points) {
  return {
    x: points.reduce((sum, p) => sum + p.x, 0) / points.length,
    y: points.reduce((sum, p) => sum + p.y, 0) / points.length,
  };
}

function samplePointsEvenly(points, maxCount) {
  if (!points.length || points.length <= maxCount) return points.slice();
  const step = Math.max(1, Math.ceil(points.length / maxCount));
  const sampled = [];
  for (let i = 0; i < points.length; i += step) {
    sampled.push(points[i]);
  }
  if (sampled[sampled.length - 1] !== points[points.length - 1]) {
    sampled.push(points[points.length - 1]);
  }
  return sampled;
}

function haversineMeters(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function principalAngle(points) {
  const c = pointCentroid(points);
  let sxx = 0;
  let syy = 0;
  let sxy = 0;
  for (const p of points) {
    const dx = p.x - c.x;
    const dy = p.y - c.y;
    sxx += dx * dx;
    syy += dy * dy;
    sxy += dx * dy;
  }
  return 0.5 * Math.atan2(2 * sxy, sxx - syy);
}

function bounds(points) {
  return {
    minX: Math.min(...points.map((p) => p.x)),
    maxX: Math.max(...points.map((p) => p.x)),
    minY: Math.min(...points.map((p) => p.y)),
    maxY: Math.max(...points.map((p) => p.y)),
  };
}

function transformMetersPoint(point, transform) {
  const theta = (transform.rotationDeg * Math.PI) / 180;
  const ct = Math.cos(theta);
  const st = Math.sin(theta);
  return {
    x: transform.translateX + transform.scale * (point.x * ct - point.y * st),
    y: transform.translateY + transform.scale * (point.x * st + point.y * ct),
  };
}

function nearestPoint(point, cloud) {
  let best = cloud[0];
  let bestDistSq = Number.POSITIVE_INFINITY;
  for (let i = 0; i < cloud.length; i += 1) {
    const dx = point.x - cloud[i].x;
    const dy = point.y - cloud[i].y;
    const distSq = dx * dx + dy * dy;
    if (distSq < bestDistSq) {
      bestDistSq = distSq;
      best = cloud[i];
    }
  }
  return { point: best, distance: Math.sqrt(bestDistSq) };
}

function solveSimilarityTransform(sourcePoints, targetPoints) {
  if (!sourcePoints.length || sourcePoints.length !== targetPoints.length) return null;
  const sourceCenter = pointCentroid(sourcePoints);
  const targetCenter = pointCentroid(targetPoints);

  let a = 0;
  let b = 0;
  let sourceNorm = 0;
  for (let i = 0; i < sourcePoints.length; i += 1) {
    const sx = sourcePoints[i].x - sourceCenter.x;
    const sy = sourcePoints[i].y - sourceCenter.y;
    const tx = targetPoints[i].x - targetCenter.x;
    const ty = targetPoints[i].y - targetCenter.y;
    a += sx * tx + sy * ty;
    b += sx * ty - sy * tx;
    sourceNorm += sx * sx + sy * sy;
  }

  if (!sourceNorm || !Number.isFinite(sourceNorm)) return null;
  const scale = Math.sqrt(a * a + b * b) / sourceNorm;
  const angleRad = Math.atan2(b, a);
  const ct = Math.cos(angleRad);
  const st = Math.sin(angleRad);
  return {
    scale,
    rotationDeg: (angleRad * 180) / Math.PI,
    translateX: targetCenter.x - scale * (sourceCenter.x * ct - sourceCenter.y * st),
    translateY: targetCenter.y - scale * (sourceCenter.x * st + sourceCenter.y * ct),
  };
}

function refineAutoAlign(initialTransform) {
  const telemetrySample = samplePointsEvenly(state.telemetryPointsMeters, 700);
  const layoutSample = samplePointsEvenly(state.layoutPixelPoints, 2600);
  if (telemetrySample.length < 20 || layoutSample.length < 50) {
    return { transform: initialTransform, meanError: null };
  }

  let current = { ...initialTransform };
  let best = { ...initialTransform };
  let bestError = Number.POSITIVE_INFINITY;

  for (let iter = 0; iter < 7; iter += 1) {
    const transformed = telemetrySample.map((point) => transformMetersPoint(point, current));
    const targets = [];
    let totalError = 0;

    for (let i = 0; i < transformed.length; i += 1) {
      const nearest = nearestPoint(transformed[i], layoutSample);
      targets.push(nearest.point);
      totalError += nearest.distance;
    }

    const meanError = totalError / transformed.length;
    if (meanError < bestError) {
      bestError = meanError;
      best = { ...current };
    }

    const solved = solveSimilarityTransform(telemetrySample, targets);
    if (!solved) break;

    const rotationShift = Math.abs(solved.rotationDeg - current.rotationDeg);
    const scaleShift = Math.abs(solved.scale - current.scale);
    const translateShift = Math.hypot(solved.translateX - current.translateX, solved.translateY - current.translateY);
    current = solved;

    if (rotationShift < 0.02 && scaleShift < 0.0005 && translateShift < 0.2) {
      const finalProjected = telemetrySample.map((point) => transformMetersPoint(point, current));
      let finalError = 0;
      for (let i = 0; i < finalProjected.length; i += 1) {
        finalError += nearestPoint(finalProjected[i], layoutSample).distance;
      }
      bestError = finalError / finalProjected.length;
      best = { ...current };
      break;
    }
  }

  return { transform: best, meanError: Number.isFinite(bestError) ? bestError : null };
}

function applyLayoutTransform(point, transform) {
  const theta = (transform.rotationDeg * Math.PI) / 180;
  const ct = Math.cos(theta);
  const st = Math.sin(theta);
  const dx = point.x - transform.pivotX;
  const dy = point.y - transform.pivotY;
  return {
    x: transform.pivotX + transform.translateX + transform.scale * (dx * ct - dy * st),
    y: transform.pivotY + transform.translateY + transform.scale * (dx * st + dy * ct),
  };
}

function inverseLayoutTransform(point, transform) {
  const theta = (-transform.rotationDeg * Math.PI) / 180;
  const ct = Math.cos(theta);
  const st = Math.sin(theta);
  const dx = (point.x - transform.pivotX - transform.translateX) / transform.scale;
  const dy = (point.y - transform.pivotY - transform.translateY) / transform.scale;
  return {
    x: transform.pivotX + dx * ct - dy * st,
    y: transform.pivotY + dx * st + dy * ct,
  };
}

function worldToScreen(point) {
  return {
    x: state.view.offsetX + point.x * state.view.zoom,
    y: state.view.offsetY + point.y * state.view.zoom,
  };
}

function screenToWorld(point) {
  return {
    x: (point.x - state.view.offsetX) / state.view.zoom,
    y: (point.y - state.view.offsetY) / state.view.zoom,
  };
}

function syncTransformInputs() {
  els.translateX.value = state.layoutTransform.translateX.toFixed(2);
  els.translateY.value = state.layoutTransform.translateY.toFixed(2);
  els.scale.value = state.layoutTransform.scale.toFixed(4);
  els.rotationDeg.value = state.layoutTransform.rotationDeg.toFixed(3);
  els.pivotX.value = state.layoutTransform.pivotX.toFixed(2);
  els.pivotY.value = state.layoutTransform.pivotY.toFixed(2);
}

function updateTransformFromInputs() {
  state.layoutTransform.translateX = Number(els.translateX.value);
  state.layoutTransform.translateY = Number(els.translateY.value);
  state.layoutTransform.scale = Number(els.scale.value);
  state.layoutTransform.rotationDeg = Number(els.rotationDeg.value);
  state.layoutTransform.pivotX = Number(els.pivotX.value);
  state.layoutTransform.pivotY = Number(els.pivotY.value);
  redraw();
}

function setPivotToCenter() {
  if (!state.layoutWidth || !state.layoutHeight) return;
  state.layoutTransform.pivotX = state.layoutWidth / 2;
  state.layoutTransform.pivotY = state.layoutHeight / 2;
  syncTransformInputs();
  redraw();
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function parseSvgSize(svgText) {
  const doc = new DOMParser().parseFromString(svgText, "image/svg+xml");
  const svg = doc.documentElement;
  const viewBox = svg.getAttribute("viewBox");
  if (viewBox) {
    const parts = viewBox.trim().split(/[\s,]+/).map(Number);
    if (parts.length === 4 && parts.every((v) => Number.isFinite(v))) {
      return { width: parts[2], height: parts[3] };
    }
  }
  const width = Number.parseFloat(svg.getAttribute("width") || "");
  const height = Number.parseFloat(svg.getAttribute("height") || "");
  return {
    width: Number.isFinite(width) ? width : 1000,
    height: Number.isFinite(height) ? height : 1000,
  };
}

async function loadLayout(file) {
  state.layoutFile = file;
  els.layoutFileName.textContent = file.name;
  state.layoutDataUrl = await fileToDataUrl(file);
  state.layoutSvgText = "";
  if (file.name.toLowerCase().endsWith(".svg") || file.type === "image/svg+xml") {
    state.layoutSvgText = await file.text();
    const size = parseSvgSize(state.layoutSvgText);
    state.layoutWidth = size.width;
    state.layoutHeight = size.height;
  }
  state.layoutImageUrl = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => {
    state.layoutImage = img;
    if (!state.layoutSvgText) {
      state.layoutWidth = img.naturalWidth || img.width;
      state.layoutHeight = img.naturalHeight || img.height;
    }
    setPivotToCenter();
    extractLayoutPixels();
    fitViewToLayout();
    redraw();
    setStatus(`Loaded layout: ${file.name}\nImage: ${state.layoutWidth} x ${state.layoutHeight}`);
  };
  img.src = state.layoutImageUrl;
}

function extractLayoutPixels() {
  if (!state.layoutImage || !state.layoutWidth || !state.layoutHeight) return;
  const off = document.createElement("canvas");
  off.width = Math.max(1, Math.round(state.layoutWidth));
  off.height = Math.max(1, Math.round(state.layoutHeight));
  const offCtx = off.getContext("2d");
  offCtx.drawImage(state.layoutImage, 0, 0, off.width, off.height);
  const { data, width, height } = offCtx.getImageData(0, 0, off.width, off.height);
  const threshold = Number(els.darkThreshold.value);
  const points = [];
  for (let y = 0; y < height; y += 2) {
    for (let x = 0; x < width; x += 2) {
      if (x < 320 && y < 220) continue;
      const idx = (y * width + x) * 4;
      const r = data[idx];
      const g = data[idx + 1];
      const b = data[idx + 2];
      const a = data[idx + 3];
      const lum = 0.299 * r + 0.587 * g + 0.114 * b;
      if (a > 0 && lum < threshold) {
        points.push({ x, y });
      }
    }
  }
  state.layoutPixelPoints = points;
}

async function loadTelemetry(file) {
  state.telemetryFile = file;
  els.csvFileName.textContent = file.name;
  const text = await file.text();
  const rows = parseCsv(text);
  const telemetry = telemetryToMeters(rows, Number(els.minSpeed.value));
  state.telemetryGeoReference = telemetry.geoReference;
  state.telemetryPointsMeters = telemetry.points;
  state.sectors = [];
  state.selectedLapTrace = [];
  updateSectorList();
  redraw();
  setStatus(`Loaded telemetry: ${file.name}\nFiltered GPS points: ${state.telemetryPointsMeters.length}`);
}

function autoAlign() {
  if (!state.layoutPixelPoints.length || !state.telemetryPointsMeters.length || !state.layoutImage) {
    setStatus("Load both a layout and telemetry first.");
    return;
  }

  const layoutAngle = principalAngle(state.layoutPixelPoints);
  const telemetryAngle = principalAngle(state.telemetryPointsMeters);
  const layoutBounds = bounds(state.layoutPixelPoints);
  const telemetryBounds = bounds(state.telemetryPointsMeters);
  const layoutCenter = pointCentroid(state.layoutPixelPoints);
  const telemetryCenter = pointCentroid(state.telemetryPointsMeters);
  const scaleX = (layoutBounds.maxX - layoutBounds.minX) / (telemetryBounds.maxX - telemetryBounds.minX);
  const scaleY = (layoutBounds.maxY - layoutBounds.minY) / (telemetryBounds.maxY - telemetryBounds.minY);
  const scale = Math.min(scaleX, scaleY);
  const rotationDeg = ((layoutAngle - telemetryAngle) * 180) / Math.PI;
  const theta = (rotationDeg * Math.PI) / 180;
  const ct = Math.cos(theta);
  const st = Math.sin(theta);

  const initialTransform = {
    scale,
    rotationDeg,
    translateX: layoutCenter.x - scale * (telemetryCenter.x * ct - telemetryCenter.y * st),
    translateY: layoutCenter.y - scale * (telemetryCenter.x * st + telemetryCenter.y * ct),
  };
  const refined = refineAutoAlign(initialTransform);
  state.telemetryAutoAlign = refined.transform;
  const refinedTheta = (state.telemetryAutoAlign.rotationDeg * Math.PI) / 180;
  const refinedCt = Math.cos(refinedTheta);
  const refinedSt = Math.sin(refinedTheta);

  state.telemetryWorldPoints = state.telemetryPointsMeters.map((p) => ({
    x: state.telemetryAutoAlign.translateX + state.telemetryAutoAlign.scale * (p.x * refinedCt - p.y * refinedSt),
    y: state.telemetryAutoAlign.translateY + state.telemetryAutoAlign.scale * (p.x * refinedSt + p.y * refinedCt),
  }));
  state.sectors = [];
  state.selectedLapTrace = [];
  updateSectorList();

  state.layoutTransform.translateX = 0;
  state.layoutTransform.translateY = 0;
  state.layoutTransform.scale = 1;
  state.layoutTransform.rotationDeg = 0;
  setPivotToCenter();
  fitViewToContent();
  redraw();
  setStatus(
    `Auto aligned\nTelemetry mapped into layout space\nRotation: ${state.telemetryAutoAlign.rotationDeg.toFixed(2)} deg\nScale: ${state.telemetryAutoAlign.scale.toFixed(4)}${refined.meanError != null ? `\nMean fit error: ${refined.meanError.toFixed(2)} px` : ""}`
  );
}

function fitViewToLayout() {
  if (!state.layoutWidth || !state.layoutHeight) return;
  const margin = 80;
  const zoomX = (els.stage.width - margin * 2) / state.layoutWidth;
  const zoomY = (els.stage.height - margin * 2) / state.layoutHeight;
  state.view.zoom = Math.min(zoomX, zoomY);
  state.view.offsetX = (els.stage.width - state.layoutWidth * state.view.zoom) / 2;
  state.view.offsetY = (els.stage.height - state.layoutHeight * state.view.zoom) / 2;
}

function fitViewToContent() {
  const worldPoints = [];
  if (state.layoutWidth && state.layoutHeight) {
    worldPoints.push(
      applyLayoutTransform({ x: 0, y: 0 }, state.layoutTransform),
      applyLayoutTransform({ x: state.layoutWidth, y: 0 }, state.layoutTransform),
      applyLayoutTransform({ x: state.layoutWidth, y: state.layoutHeight }, state.layoutTransform),
      applyLayoutTransform({ x: 0, y: state.layoutHeight }, state.layoutTransform)
    );
  }
  if (state.telemetryWorldPoints.length) {
    worldPoints.push(...state.telemetryWorldPoints);
  }
  if (!worldPoints.length) return;
  const b = bounds(worldPoints);
  const margin = 100;
  const zoomX = (els.stage.width - margin * 2) / (b.maxX - b.minX || 1);
  const zoomY = (els.stage.height - margin * 2) / (b.maxY - b.minY || 1);
  state.view.zoom = Math.min(zoomX, zoomY);
  state.view.offsetX = margin - b.minX * state.view.zoom;
  state.view.offsetY = margin - b.minY * state.view.zoom;
  redraw();
}

function redraw() {
  ctx.clearRect(0, 0, els.stage.width, els.stage.height);
  ctx.fillStyle = "#fcfaf6";
  ctx.fillRect(0, 0, els.stage.width, els.stage.height);
  drawGrid();

  if (state.layoutImage) {
    ctx.save();
    ctx.translate(state.view.offsetX, state.view.offsetY);
    ctx.scale(state.view.zoom, state.view.zoom);
    ctx.translate(state.layoutTransform.translateX, state.layoutTransform.translateY);
    ctx.translate(state.layoutTransform.pivotX, state.layoutTransform.pivotY);
    ctx.rotate((state.layoutTransform.rotationDeg * Math.PI) / 180);
    ctx.scale(state.layoutTransform.scale, state.layoutTransform.scale);
    ctx.translate(-state.layoutTransform.pivotX, -state.layoutTransform.pivotY);
    ctx.drawImage(state.layoutImage, 0, 0, state.layoutWidth, state.layoutHeight);
    ctx.restore();
  }

  if (state.telemetryWorldPoints.length) {
    ctx.strokeStyle = "rgba(21, 101, 192, 0.65)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    state.telemetryWorldPoints.forEach((p, idx) => {
      const s = worldToScreen(p);
      if (idx === 0) ctx.moveTo(s.x, s.y);
      else ctx.lineTo(s.x, s.y);
    });
    ctx.stroke();

    ctx.fillStyle = "rgba(229, 57, 53, 0.18)";
    for (let i = 0; i < state.telemetryWorldPoints.length; i += 8) {
      const p = worldToScreen(state.telemetryWorldPoints[i]);
      ctx.beginPath();
      ctx.arc(p.x, p.y, 2.2, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  drawPivot();
  drawAnchors();
  drawStartFinishLine();
  drawSectors();
}

function drawGrid() {
  ctx.save();
  ctx.strokeStyle = "rgba(28, 47, 69, 0.06)";
  ctx.lineWidth = 1;
  for (let x = 0; x < els.stage.width; x += 40) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, els.stage.height);
    ctx.stroke();
  }
  for (let y = 0; y < els.stage.height; y += 40) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(els.stage.width, y);
    ctx.stroke();
  }
  ctx.restore();
}

function drawPivot() {
  if (!state.layoutWidth || !state.layoutHeight) return;
  const pivotWorld = applyLayoutTransform(
    { x: state.layoutTransform.pivotX, y: state.layoutTransform.pivotY },
    state.layoutTransform
  );
  const pivot = worldToScreen(pivotWorld);
  ctx.save();
  ctx.strokeStyle = "#f57c00";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(pivot.x - 10, pivot.y);
  ctx.lineTo(pivot.x + 10, pivot.y);
  ctx.moveTo(pivot.x, pivot.y - 10);
  ctx.lineTo(pivot.x, pivot.y + 10);
  ctx.stroke();
  ctx.restore();
}

function drawAnchors() {
  ctx.save();
  for (const anchor of state.anchors) {
    const world = applyLayoutTransform(anchor.layoutPoint, state.layoutTransform);
    const p = worldToScreen(world);
    ctx.fillStyle = "#c3472c";
    ctx.beginPath();
    ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#1b1b19";
    ctx.font = "12px IBM Plex Sans";
    ctx.fillText(anchor.id, p.x + 8, p.y - 8);
  }
  ctx.restore();
}

function drawStartFinishLine() {
  const anchors = findStartFinishAnchors();
  const draftPoints = state.startFinishDraft || [];
  const points = anchors.length >= 2
    ? anchors.slice(0, 2).map((anchor) => worldToScreen(applyLayoutTransform(anchor.layoutPoint, state.layoutTransform)))
    : draftPoints.map((point) => worldToScreen(applyLayoutTransform(point, state.layoutTransform)));

  if (!points.length) return;

  ctx.save();
  ctx.strokeStyle = "#ff8f00";
  ctx.fillStyle = "#ff8f00";
  ctx.lineWidth = 3;
  if (points.length === 2) {
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    ctx.lineTo(points[1].x, points[1].y);
    ctx.stroke();
  }
  points.forEach((point) => {
    ctx.beginPath();
    ctx.arc(point.x, point.y, 6, 0, Math.PI * 2);
    ctx.fill();
  });
  ctx.restore();
}

function drawSectors() {
  if (!state.sectors.length) return;
  ctx.save();
  ctx.fillStyle = "#146c43";
  ctx.strokeStyle = "rgba(20, 108, 67, 0.28)";
  ctx.lineWidth = 1.5;
  ctx.font = "12px IBM Plex Sans";
  for (const sector of state.sectors) {
    const p = worldToScreen(sector.canonical);
    ctx.beginPath();
    ctx.arc(p.x, p.y, 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(p.x, p.y, 12, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillText(sector.id, p.x + 8, p.y - 8);
  }
  ctx.restore();
}

function updateAnchorList() {
  els.anchorList.innerHTML = "";
  state.anchors.forEach((anchor, index) => {
    const li = document.createElement("li");
    const bits = [anchor.id];
    if (anchor.name) bits.push(anchor.name);
    if (anchor.type) bits.push(`[${anchor.type}]`);
    bits.push(`(${anchor.layoutPoint.x.toFixed(1)}, ${anchor.layoutPoint.y.toFixed(1)})`);
    li.textContent = bits.join(" ");
    if (index === state.selectedAnchorIndex) {
      li.classList.add("selected");
    }
    li.addEventListener("click", () => {
      state.selectedAnchorIndex = index;
      syncAnchorEditor();
      updateAnchorList();
      redraw();
    });
    els.anchorList.appendChild(li);
  });
}

function updateSectorList() {
  if (!els.sectorList) return;
  els.sectorList.innerHTML = "";
  state.sectors.forEach((sector) => {
    const li = document.createElement("li");
    const pct = sector.progressRatio != null ? `${(sector.progressRatio * 100).toFixed(1)}%` : "n/a";
    li.textContent = `${sector.id} ${pct} r=${sector.radius_m.toFixed(1)}m (${sector.lat.toFixed(6)}, ${sector.lon.toFixed(6)})`;
    els.sectorList.appendChild(li);
  });
}

function syncAnchorEditor() {
  const anchor = state.anchors[state.selectedAnchorIndex];
  els.anchorLabel.value = anchor?.name || "";
  els.anchorType.value = anchor?.type || "";
}

function updateSelectedAnchorFields() {
  const anchor = state.anchors[state.selectedAnchorIndex];
  if (!anchor) return;
  anchor.name = els.anchorLabel.value.trim();
  anchor.type = els.anchorType.value.trim();
  updateAnchorList();
  redraw();
}

function deleteSelectedAnchor() {
  if (state.selectedAnchorIndex < 0 || state.selectedAnchorIndex >= state.anchors.length) return;
  pushAnchorHistory();
  state.anchors.splice(state.selectedAnchorIndex, 1);
  state.selectedAnchorIndex = Math.min(state.selectedAnchorIndex, state.anchors.length - 1);
  syncAnchorEditor();
  updateAnchorList();
  redraw();
}

function canvasPointFromEvent(event) {
  const rect = els.stage.getBoundingClientRect();
  const sx = els.stage.width / rect.width;
  const sy = els.stage.height / rect.height;
  return {
    x: (event.clientX - rect.left) * sx,
    y: (event.clientY - rect.top) * sy,
  };
}

function pickAnchorAtScreenPoint(screenPoint, radius = 12) {
  for (let i = 0; i < state.anchors.length; i += 1) {
    const world = applyLayoutTransform(state.anchors[i].layoutPoint, state.layoutTransform);
    const p = worldToScreen(world);
    const dx = p.x - screenPoint.x;
    const dy = p.y - screenPoint.y;
    if (dx * dx + dy * dy <= radius * radius) {
      return i;
    }
  }
  return -1;
}

function handleStageMouseDown(event) {
  const screenPoint = canvasPointFromEvent(event);
  const worldPoint = screenToWorld(screenPoint);

  if (state.startFinishCaptureActive) {
    pushAnchorHistory();
    const layoutPoint = inverseLayoutTransform(worldPoint, state.layoutTransform);
    state.startFinishDraft.push(layoutPoint);
    if (state.startFinishDraft.length === 2) {
      replaceStartFinishAnchors(state.startFinishDraft);
      state.startFinishCaptureActive = false;
      state.startFinishDraft = [];
      redraw();
      setStatus("Start/finish line created. You can now auto-generate sectors.");
    } else {
      redraw();
      setStatus("Start/finish point 1 set. Click the second point.");
    }
    return;
  }

  if (els.anchorMode.checked) {
    pushAnchorHistory();
    const layoutPoint = inverseLayoutTransform(worldPoint, state.layoutTransform);
    state.anchors.push({
      id: nextAnchorId(),
      name: "",
      type: "",
      layoutPoint,
    });
    state.selectedAnchorIndex = state.anchors.length - 1;
    syncAnchorEditor();
    updateAnchorList();
    redraw();
    return;
  }

  const pickedAnchor = pickAnchorAtScreenPoint(screenPoint);
  if (pickedAnchor >= 0) {
    state.selectedAnchorIndex = pickedAnchor;
    syncAnchorEditor();
    updateAnchorList();
    redraw();
    return;
  }

  state.drag.active = true;
  state.drag.startX = screenPoint.x;
  state.drag.startY = screenPoint.y;

  if (event.shiftKey || !els.dragMode.checked) {
    state.drag.mode = "view";
    state.drag.originX = state.view.offsetX;
    state.drag.originY = state.view.offsetY;
  } else {
    state.drag.mode = "layout";
    state.drag.originX = state.layoutTransform.translateX;
    state.drag.originY = state.layoutTransform.translateY;
  }
}

function handleStageMouseMove(event) {
  if (!state.drag.active) return;
  const screenPoint = canvasPointFromEvent(event);
  const dxScreen = screenPoint.x - state.drag.startX;
  const dyScreen = screenPoint.y - state.drag.startY;

  if (state.drag.mode === "view") {
    state.view.offsetX = state.drag.originX + dxScreen;
    state.view.offsetY = state.drag.originY + dyScreen;
  } else {
    state.layoutTransform.translateX = state.drag.originX + dxScreen / state.view.zoom;
    state.layoutTransform.translateY = state.drag.originY + dyScreen / state.view.zoom;
    syncTransformInputs();
  }
  redraw();
}

function handleStageMouseUp() {
  state.drag.active = false;
}

function handleStageWheel(event) {
  event.preventDefault();
  const screenPoint = canvasPointFromEvent(event);
  const worldBefore = screenToWorld(screenPoint);
  const zoomFactor = Math.exp(-event.deltaY * 0.0012);
  state.view.zoom = Math.max(0.1, Math.min(20, state.view.zoom * zoomFactor));
  state.view.offsetX = screenPoint.x - worldBefore.x * state.view.zoom;
  state.view.offsetY = screenPoint.y - worldBefore.y * state.view.zoom;
  redraw();
}

function resetView() {
  state.view.zoom = 1;
  state.view.offsetX = 120;
  state.view.offsetY = 80;
  redraw();
}

function resetTransform() {
  state.layoutTransform.translateX = 0;
  state.layoutTransform.translateY = 0;
  state.layoutTransform.scale = 1;
  state.layoutTransform.rotationDeg = 0;
  if (state.layoutWidth && state.layoutHeight) {
    state.layoutTransform.pivotX = state.layoutWidth / 2;
    state.layoutTransform.pivotY = state.layoutHeight / 2;
  }
  syncTransformInputs();
  redraw();
}

function telemetryBoundsWorld() {
  if (!state.telemetryWorldPoints.length) return null;
  return bounds(state.telemetryWorldPoints);
}

function findStartFinishAnchors() {
  return state.anchors.filter(isStartFinishAnchor).slice(0, 2);
}

function nextAnchorId() {
  return `A${String(state.anchors.length + 1).padStart(2, "0")}`;
}

function replaceStartFinishAnchors(points) {
  state.anchors = state.anchors.filter((anchor) => !isStartFinishAnchor(anchor));
  points.forEach((layoutPoint, idx) => {
    state.anchors.push({
      id: nextAnchorId(),
      name: `Start Finish ${idx + 1}`,
      type: "start_finish",
      layoutPoint: { ...layoutPoint },
    });
  });
  state.selectedAnchorIndex = state.anchors.length - 1;
  syncAnchorEditor();
  updateAnchorList();
}

function beginStartFinishCapture() {
  state.startFinishCaptureActive = true;
  state.startFinishDraft = [];
  els.anchorMode.checked = false;
  setStatus("Click two points to define the start/finish line.");
}

function clearStartFinishAnchors() {
  const hadAny = findStartFinishAnchors().length > 0;
  state.anchors = state.anchors.filter((anchor) => !isStartFinishAnchor(anchor));
  state.sectors = [];
  state.startFinishCaptureActive = false;
  state.startFinishDraft = [];
  if (hadAny) {
    syncAnchorEditor();
    updateAnchorList();
    updateSectorList();
    redraw();
  }
  setStatus("Cleared start/finish anchors.");
}

function canonicalToLocalMeters(point) {
  if (!state.telemetryAutoAlign) return null;
  const scale = Number(state.telemetryAutoAlign.scale || 0);
  if (!scale) return null;
  const theta = (Number(state.telemetryAutoAlign.rotationDeg || 0) * Math.PI) / 180;
  const tx = Number(state.telemetryAutoAlign.translateX || 0);
  const ty = Number(state.telemetryAutoAlign.translateY || 0);
  const xScaled = (Number(point.x) - tx) / scale;
  const yScaled = (Number(point.y) - ty) / scale;
  const ct = Math.cos(theta);
  const st = Math.sin(theta);
  return {
    x: xScaled * ct + yScaled * st,
    y: -xScaled * st + yScaled * ct,
  };
}

function localMetersToLatLon(localPoint) {
  if (!state.telemetryGeoReference || !localPoint) return null;
  return {
    lat: state.telemetryGeoReference.lat0 - localPoint.y / state.telemetryGeoReference.metersPerDegLat,
    lon: state.telemetryGeoReference.lon0 + localPoint.x / state.telemetryGeoReference.metersPerDegLon,
  };
}

function fullTelemetryTrace() {
  if (!state.telemetryPointsMeters.length || !state.telemetryWorldPoints.length) return [];
  return state.telemetryPointsMeters.map((point, index) => ({
    index,
    lat: point.lat,
    lon: point.lon,
    localMeters: { x: point.x, y: point.y },
    canonical: { x: state.telemetryWorldPoints[index].x, y: state.telemetryWorldPoints[index].y },
  }));
}

function segmentCrossesLine(a1, a2, b1, b2) {
  const orient = (p, q, r) => (q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x);
  const o1 = orient(a1, a2, b1);
  const o2 = orient(a1, a2, b2);
  const o3 = orient(b1, b2, a1);
  const o4 = orient(b1, b2, a2);
  return (o1 === 0 || o2 === 0 || Math.sign(o1) !== Math.sign(o2)) &&
    (o3 === 0 || o4 === 0 || Math.sign(o3) !== Math.sign(o4));
}

function pointToSegmentDistance(point, segA, segB) {
  const vx = segB.x - segA.x;
  const vy = segB.y - segA.y;
  const wx = point.x - segA.x;
  const wy = point.y - segA.y;
  const segLenSq = vx * vx + vy * vy;
  if (segLenSq <= 1e-9) return Math.hypot(point.x - segA.x, point.y - segA.y);
  let t = (wx * vx + wy * vy) / segLenSq;
  t = Math.max(0, Math.min(1, t));
  const projX = segA.x + t * vx;
  const projY = segA.y + t * vy;
  return Math.hypot(point.x - projX, point.y - projY);
}

function orderedTraceFromStart(tracePoints, startLineA, startLineB) {
  if (!tracePoints.length || !startLineA || !startLineB) return tracePoints.slice();

  let crossingIdx = -1;
  for (let i = 0; i < tracePoints.length - 1; i += 1) {
    const p1 = tracePoints[i].canonical;
    const p2 = tracePoints[i + 1].canonical;
    if (segmentCrossesLine(p1, p2, startLineA, startLineB)) {
      crossingIdx = i + 1;
      break;
    }
  }

  if (crossingIdx < 0) {
    const startCenter = {
      x: (startLineA.x + startLineB.x) / 2,
      y: (startLineA.y + startLineB.y) / 2,
    };
    crossingIdx = tracePoints.reduce((bestIdx, point, idx) => {
      const best = tracePoints[bestIdx];
      const bestDist = pointToSegmentDistance(best.canonical, startLineA, startLineB);
      const dist = pointToSegmentDistance(point.canonical, startLineA, startLineB);
      if (dist === bestDist) {
        const bestCenterDist = Math.hypot(best.canonical.x - startCenter.x, best.canonical.y - startCenter.y);
        const centerDist = Math.hypot(point.canonical.x - startCenter.x, point.canonical.y - startCenter.y);
        return centerDist < bestCenterDist ? idx : bestIdx;
      }
      return dist < bestDist ? idx : bestIdx;
    }, 0);
  }

  return tracePoints.slice(crossingIdx).concat(tracePoints.slice(0, crossingIdx));
}

function findStartLineCrossings(tracePoints, startLineA, startLineB) {
  const raw = [];
  for (let i = 0; i < tracePoints.length - 1; i += 1) {
    if (segmentCrossesLine(tracePoints[i].canonical, tracePoints[i + 1].canonical, startLineA, startLineB)) {
      raw.push(i + 1);
    }
  }
  if (!raw.length) return [];

  const minGap = Math.max(8, Math.floor(tracePoints.length * 0.015));
  const deduped = [raw[0]];
  for (let i = 1; i < raw.length; i += 1) {
    if (raw[i] - deduped[deduped.length - 1] >= minGap) {
      deduped.push(raw[i]);
    }
  }
  return deduped;
}

function traceDistance(points) {
  let total = 0;
  for (let i = 1; i < points.length; i += 1) {
    total += haversineMeters(points[i - 1].lat, points[i - 1].lon, points[i].lat, points[i].lon);
  }
  return total;
}

function chooseLapTraceFromCrossings(tracePoints, crossingIndices) {
  if (!tracePoints.length || crossingIndices.length < 2) return null;

  const minSamples = Math.max(20, Math.floor(tracePoints.length * 0.08));

  for (let i = 0; i < crossingIndices.length - 1; i += 1) {
    const startIdx = crossingIndices[i];
    const endIdx = crossingIndices[i + 1];
    const lapPoints = tracePoints.slice(startIdx, endIdx + 1);
    if (lapPoints.length < minSamples) continue;
    return {
      startIdx,
      endIdx,
      points: lapPoints,
      distance: traceDistance(lapPoints),
    };
  }

  return null;
}

function cumulativeTraceDistances(points) {
  if (!points.length) return [];
  const cumulative = [0];
  let total = 0;
  for (let i = 1; i < points.length; i += 1) {
    total += haversineMeters(points[i - 1].lat, points[i - 1].lon, points[i].lat, points[i].lon);
    cumulative.push(total);
  }
  return cumulative;
}

function interpolateTracePoint(start, end, ratio) {
  const localMeters = {
    x: start.localMeters.x + (end.localMeters.x - start.localMeters.x) * ratio,
    y: start.localMeters.y + (end.localMeters.y - start.localMeters.y) * ratio,
  };
  const canonical = {
    x: start.canonical.x + (end.canonical.x - start.canonical.x) * ratio,
    y: start.canonical.y + (end.canonical.y - start.canonical.y) * ratio,
  };
  const geo = localMetersToLatLon(localMeters);
  return {
    lat: geo.lat,
    lon: geo.lon,
    localMeters,
    canonical,
  };
}

function deterministicSample(points, count) {
  if (points.length <= count) return points.slice();
  const keyed = points.map((point, index) => {
    const seed = Math.sin((index + 1) * 12.9898) * 43758.5453;
    const key = seed - Math.floor(seed);
    return { key, point };
  });
  keyed.sort((a, b) => a.key - b.key);
  return keyed.slice(0, count).map((entry) => entry.point);
}

function exportTraceSource() {
  return state.selectedLapTrace?.length ? state.selectedLapTrace : fullTelemetryTrace();
}

function sampledGpsReferences(sampleCount = 75) {
  const merged = exportTraceSource();
  if (!merged.length) return [];
  return deterministicSample(merged, sampleCount);
}

function orderedGpsTrace(maxPoints = 400) {
  const merged = exportTraceSource();
  if (merged.length <= maxPoints) return merged;
  const step = Math.max(1, Math.ceil(merged.length / maxPoints));
  const sampled = [];
  for (let i = 0; i < merged.length; i += step) sampled.push(merged[i]);
  if (sampled[sampled.length - 1]?.index !== merged[merged.length - 1]?.index) {
    sampled.push(merged[merged.length - 1]);
  }
  return sampled;
}

function autoGenerateSectors() {
  if (!state.telemetryGeoReference || !state.telemetryAutoAlign || !state.telemetryPointsMeters.length) {
    setStatus("Load telemetry and run Auto Align before generating sectors.");
    return;
  }
  const startAnchors = findStartFinishAnchors();
  if (startAnchors.length < 2) {
    setStatus("Mark two anchors with a name or type containing 'start finish' before generating sectors.");
    return;
  }

  const radiusM = Math.max(5, Number(els.sectorRadius.value) || 15);
  const sectorCount = Math.max(2, Math.round(Number(els.sectorCount.value) || 7));
  const startLineA = startAnchors[0].layoutPoint;
  const startLineB = startAnchors[1].layoutPoint;
  const startCenterCanonical = {
    x: (startLineA.x + startLineB.x) / 2,
    y: (startLineA.y + startLineB.y) / 2,
  };
  const fullTrace = fullTelemetryTrace();
  if (fullTrace.length < 8) {
    setStatus("Not enough sequential telemetry points to generate sectors.");
    return;
  }

  const crossingIndices = findStartLineCrossings(fullTrace, startLineA, startLineB);

  let lapTrace = [];
  if (crossingIndices.length >= 2) {
    const chosenLap = chooseLapTraceFromCrossings(fullTrace, crossingIndices);
    lapTrace = chosenLap?.points || [];
  } else {
    lapTrace = orderedTraceFromStart(fullTrace, startLineA, startLineB);
  }

  if (lapTrace.length < 4) {
    setStatus("Could not isolate a usable lap from the sequential telemetry trace.");
    return;
  }
  state.selectedLapTrace = lapTrace.map((point) => ({
    index: point.index,
    lat: point.lat,
    lon: point.lon,
    localMeters: { ...point.localMeters },
    canonical: { ...point.canonical },
  }));

  const closedTrace = lapTrace.concat([lapTrace[0]]);
  const cumulative = cumulativeTraceDistances(closedTrace);
  const lapLength = cumulative[cumulative.length - 1];
  if (!lapLength || !Number.isFinite(lapLength)) {
    setStatus("Unable to calculate lap length from telemetry.");
    return;
  }

  state.sectors = [];
  const step = lapLength / sectorCount;
  for (let sectorIdx = 1; sectorIdx <= sectorCount; sectorIdx += 1) {
    let point = closedTrace[0];
    let progressM = step * sectorIdx;

    if (sectorIdx === sectorCount) {
      const localMeters = canonicalToLocalMeters(startCenterCanonical);
      const geo = localMetersToLatLon(localMeters);
      point = { lat: geo.lat, lon: geo.lon, localMeters, canonical: startCenterCanonical };
      progressM = lapLength;
    } else {
      const segmentIdx = cumulative.findIndex((distance, index) => index > 0 && distance >= progressM);
      const safeIdx = segmentIdx > 0 ? segmentIdx : closedTrace.length - 1;
      const prevDistance = cumulative[safeIdx - 1];
      const nextDistance = cumulative[safeIdx];
      const ratio = nextDistance <= prevDistance ? 0 : (progressM - prevDistance) / (nextDistance - prevDistance);
      point = interpolateTracePoint(closedTrace[safeIdx - 1], closedTrace[safeIdx], ratio);
    }

    state.sectors.push({
      id: `S${sectorIdx}`,
      sector_index: sectorIdx,
      lat: point.lat,
      lon: point.lon,
      end_lat: point.lat,
      end_lon: point.lon,
      radius_m: radiusM,
      progress_m: Number(progressM.toFixed(3)),
      progressRatio: progressM / lapLength,
      canonical: point.canonical,
      localMeters: point.localMeters,
    });
  }

  updateSectorList();
  redraw();
  setStatus(`Generated ${state.sectors.length} sectors from sequential GPS order.\nCrossings found: ${crossingIndices.length}\nRadius: ${radiusM.toFixed(1)} m`);
}

function updateSectorRadius() {
  const radiusM = Math.max(5, Number(els.sectorRadius.value) || 15);
  if (!state.sectors.length) {
    setStatus("Generate sectors first.");
    return;
  }
  state.sectors = state.sectors.map((sector) => ({ ...sector, radius_m: radiusM }));
  updateSectorList();
  redraw();
  setStatus(`Updated sector radius to ${radiusM.toFixed(1)} m.`);
}

function buildCanonicalPayload(includeEmbeddedLayout = false) {
  return {
    version: 1,
    exportedAt: new Date().toISOString(),
    layout: {
      fileName: state.layoutFile?.name || null,
      width: state.layoutWidth || null,
      height: state.layoutHeight || null,
      embeddedDataUrl: includeEmbeddedLayout ? state.layoutDataUrl : undefined,
    },
    telemetry: {
      fileName: state.telemetryFile?.name || null,
      filteredPointCount: state.telemetryPointsMeters.length,
      minSpeed: Number(els.minSpeed.value),
      autoAlign: state.telemetryAutoAlign,
      geoReference: state.telemetryGeoReference,
      sampledGpsPoints: sampledGpsReferences(75),
      orderedGpsPoints: orderedGpsTrace(400),
    },
    transform: { ...state.layoutTransform },
    anchors: state.anchors.map((anchor) => ({
      id: anchor.id,
      name: anchor.name || "",
      type: anchor.type || "",
      x: anchor.layoutPoint.x,
      y: anchor.layoutPoint.y,
    })),
    sectorConfig: {
      count: Math.max(2, Math.round(Number(els.sectorCount.value) || 7)),
      radius_m: Math.max(5, Number(els.sectorRadius.value) || 15),
      source: state.sectors.length ? "ordered_trace_auto" : null,
    },
    sectors: state.sectors.map((sector) => ({
      id: sector.id,
      sector_index: sector.sector_index,
      end_lat: sector.end_lat,
      end_lon: sector.end_lon,
      radius_m: sector.radius_m,
      progress_m: sector.progress_m,
      progress_ratio: sector.progressRatio,
    })),
    telemetryBounds: telemetryBoundsWorld(),
    view: { ...state.view },
  };
}

function exportJson() {
  const payload = buildCanonicalPayload(false);
  downloadBlob("track-layout.json", new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
}

function exportPackage() {
  const payload = buildCanonicalPayload(true);
  downloadBlob(
    "track-layout-package.json",
    new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" })
  );
}

function exportSvg() {
  if (!state.layoutDataUrl) {
    setStatus("Load a layout first.");
    return;
  }
  const polyline = state.telemetryWorldPoints
    .filter((_, idx) => idx % 3 === 0)
    .map((p) => {
      const s = worldToScreen(p);
      return `${s.x.toFixed(2)},${s.y.toFixed(2)}`;
    })
    .join(" ");
  const dots = state.telemetryWorldPoints
    .filter((_, idx) => idx % 8 === 0)
    .map((p) => {
      const s = worldToScreen(p);
      return `<circle cx="${s.x.toFixed(2)}" cy="${s.y.toFixed(2)}" r="2.2"/>`;
    })
    .join("");
  const anchors = state.anchors
    .map((anchor) => {
      const world = applyLayoutTransform(anchor.layoutPoint, state.layoutTransform);
      const s = worldToScreen(world);
      return `<g><circle cx="${s.x.toFixed(2)}" cy="${s.y.toFixed(2)}" r="5" fill="#c3472c"/><text x="${(s.x + 8).toFixed(2)}" y="${(s.y - 8).toFixed(2)}" font-size="12" fill="#1b1b19">${anchor.id}</text></g>`;
    })
    .join("");

  const pivotWorld = applyLayoutTransform(
    { x: state.layoutTransform.pivotX, y: state.layoutTransform.pivotY },
    state.layoutTransform
  );
  const pivotScreen = worldToScreen(pivotWorld);
  const imageX = state.view.offsetX + state.view.zoom * state.layoutTransform.translateX;
  const imageY = state.view.offsetY + state.view.zoom * state.layoutTransform.translateY;
  const imageWidth = state.layoutWidth * state.layoutTransform.scale * state.view.zoom;
  const imageHeight = state.layoutHeight * state.layoutTransform.scale * state.view.zoom;

  const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${els.stage.width} ${els.stage.height}">
  <image href="${state.layoutDataUrl}" x="${imageX.toFixed(2)}" y="${imageY.toFixed(2)}" width="${imageWidth.toFixed(2)}" height="${imageHeight.toFixed(2)}" transform="rotate(${state.layoutTransform.rotationDeg.toFixed(4)} ${pivotScreen.x.toFixed(2)} ${pivotScreen.y.toFixed(2)})"/>
  <polyline fill="none" stroke="#1565c0" stroke-width="2" stroke-opacity="0.65" points="${polyline}"/>
  <g fill="#e53935" fill-opacity="0.18">${dots}</g>
  ${anchors}
</svg>`;

  downloadBlob("track-layout-preview.svg", new Blob([svg], { type: "image/svg+xml" }));
}

els.layoutFile.addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (file) loadLayout(file);
});

els.csvFile.addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (file) loadTelemetry(file);
});

els.autoAlignBtn.addEventListener("click", autoAlign);
els.centerPivotBtn.addEventListener("click", setPivotToCenter);
els.resetTransformBtn.addEventListener("click", resetTransform);
els.fitViewBtn.addEventListener("click", fitViewToContent);
els.resetViewBtn.addEventListener("click", resetView);
els.createStartFinishBtn.addEventListener("click", beginStartFinishCapture);
els.clearStartFinishBtn.addEventListener("click", clearStartFinishAnchors);
els.undoAnchorBtn.addEventListener("click", undoAnchorChange);
els.deleteAnchorBtn.addEventListener("click", deleteSelectedAnchor);
els.clearAnchorsBtn.addEventListener("click", () => {
  if (!state.anchors.length) return;
  pushAnchorHistory();
  state.anchors = [];
  state.sectors = [];
  state.selectedLapTrace = [];
  state.startFinishCaptureActive = false;
  state.startFinishDraft = [];
  state.selectedAnchorIndex = -1;
  syncAnchorEditor();
  updateAnchorList();
  updateSectorList();
  redraw();
});
els.exportJsonBtn.addEventListener("click", exportJson);
els.exportSvgBtn.addEventListener("click", exportSvg);
els.exportPackageBtn.addEventListener("click", exportPackage);
els.autoAddSectorsBtn.addEventListener("click", autoGenerateSectors);
els.updateSectorRadiusBtn.addEventListener("click", updateSectorRadius);
els.anchorLabel.addEventListener("input", updateSelectedAnchorFields);
els.anchorType.addEventListener("input", updateSelectedAnchorFields);

[
  els.translateX,
  els.translateY,
  els.scale,
  els.rotationDeg,
  els.pivotX,
  els.pivotY,
].forEach((input) => input.addEventListener("input", updateTransformFromInputs));

els.stage.addEventListener("mousedown", handleStageMouseDown);
els.stage.addEventListener("mousemove", handleStageMouseMove);
els.stage.addEventListener("wheel", handleStageWheel, { passive: false });
window.addEventListener("mouseup", handleStageMouseUp);

syncTransformInputs();
redraw();
