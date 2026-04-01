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
  undoAnchorBtn: document.getElementById("undoAnchorBtn"),
  deleteAnchorBtn: document.getElementById("deleteAnchorBtn"),
  clearAnchorsBtn: document.getElementById("clearAnchorsBtn"),
  anchorLabel: document.getElementById("anchorLabel"),
  anchorType: document.getElementById("anchorType"),
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

  state.telemetryAutoAlign = {
    scale,
    rotationDeg,
    translateX: layoutCenter.x - scale * (telemetryCenter.x * ct - telemetryCenter.y * st),
    translateY: layoutCenter.y - scale * (telemetryCenter.x * st + telemetryCenter.y * ct),
  };

  state.telemetryWorldPoints = state.telemetryPointsMeters.map((p) => ({
    x: state.telemetryAutoAlign.translateX + scale * (p.x * ct - p.y * st),
    y: state.telemetryAutoAlign.translateY + scale * (p.x * st + p.y * ct),
  }));

  state.layoutTransform.translateX = 0;
  state.layoutTransform.translateY = 0;
  state.layoutTransform.scale = 1;
  state.layoutTransform.rotationDeg = 0;
  setPivotToCenter();
  fitViewToContent();
  redraw();
  setStatus(
    `Auto aligned\nTelemetry mapped into layout space\nRotation: ${rotationDeg.toFixed(2)} deg\nScale: ${scale.toFixed(4)}`
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

  if (els.anchorMode.checked) {
    pushAnchorHistory();
    const layoutPoint = inverseLayoutTransform(worldPoint, state.layoutTransform);
    state.anchors.push({
      id: `A${String(state.anchors.length + 1).padStart(2, "0")}`,
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

function sampledGpsReferences(sampleCount = 75) {
  if (!state.telemetryPointsMeters.length || !state.telemetryWorldPoints.length) return [];
  const merged = state.telemetryPointsMeters.map((point, index) => ({
    index,
    lat: point.lat,
    lon: point.lon,
    localMeters: { x: point.x, y: point.y },
    canonical: { x: state.telemetryWorldPoints[index].x, y: state.telemetryWorldPoints[index].y },
  }));
  return deterministicSample(merged, sampleCount);
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
    },
    transform: { ...state.layoutTransform },
    anchors: state.anchors.map((anchor) => ({
      id: anchor.id,
      name: anchor.name || "",
      type: anchor.type || "",
      x: anchor.layoutPoint.x,
      y: anchor.layoutPoint.y,
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
els.undoAnchorBtn.addEventListener("click", undoAnchorChange);
els.deleteAnchorBtn.addEventListener("click", deleteSelectedAnchor);
els.clearAnchorsBtn.addEventListener("click", () => {
  if (!state.anchors.length) return;
  pushAnchorHistory();
  state.anchors = [];
  state.selectedAnchorIndex = -1;
  syncAnchorEditor();
  updateAnchorList();
  redraw();
});
els.exportJsonBtn.addEventListener("click", exportJson);
els.exportSvgBtn.addEventListener("click", exportSvg);
els.exportPackageBtn.addEventListener("click", exportPackage);
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
