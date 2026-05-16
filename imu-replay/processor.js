function parseNumber(value) {
  if (value === undefined || value === null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function dot(a, b) {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function cross(a, b) {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

function norm(v) {
  return Math.sqrt(dot(v, v));
}

function normalize(v, fallback = [0, 0, 1]) {
  const mag = norm(v);
  if (mag < 1e-9) return fallback.slice();
  return [v[0] / mag, v[1] / mag, v[2] / mag];
}

function clamp(value, lo, hi) {
  return Math.max(lo, Math.min(hi, value));
}

function movingAverage(values, windowSize) {
  const out = new Array(values.length);
  let sum = 0;
  const queue = [];
  for (let i = 0; i < values.length; i += 1) {
    const v = values[i];
    queue.push(v);
    sum += v;
    if (queue.length > windowSize) {
      sum -= queue.shift();
    }
    out[i] = sum / queue.length;
  }
  return out;
}

function centeredMovingAverage(values, windowSize) {
  if (windowSize <= 1 || !values.length) return values.slice();
  const out = new Array(values.length);
  const radius = Math.floor(windowSize / 2);
  for (let index = 0; index < values.length; index += 1) {
    const start = Math.max(0, index - radius);
    const end = Math.min(values.length, index + radius + 1);
    let sum = 0;
    for (let sample = start; sample < end; sample += 1) sum += values[sample];
    out[index] = sum / Math.max(1, end - start);
  }
  return out;
}

function maybeSmooth(values, windowSize, enabled) {
  if (!enabled) return values.slice();
  return movingAverage(values, Math.max(1, windowSize));
}

function median(values) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function percentile(values, p) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = clamp(Math.floor(sorted.length * p), 0, sorted.length - 1);
  return sorted[index];
}

function hampel(values, windowRadius, sigma) {
  const out = values.slice();
  const scale = 1.4826;
  for (let i = 0; i < values.length; i += 1) {
    const cur = values[i];
    if (cur == null) continue;
    const lo = Math.max(0, i - windowRadius);
    const hi = Math.min(values.length, i + windowRadius + 1);
    const window = [];
    for (let j = lo; j < hi; j += 1) {
      const v = values[j];
      if (v != null) window.push(v);
    }
    if (window.length < 5) continue;
    const med = median(window);
    const mad = median(window.map((v) => Math.abs(v - med)));
    const threshold = mad > 1e-9 ? sigma * scale * mad : sigma * 0.5;
    if (Math.abs(cur - med) > threshold) out[i] = null;
  }
  return out;
}

function maybeHampel(values, windowRadius, sigma, enabled) {
  if (!enabled) return values.slice();
  return hampel(values, windowRadius, sigma);
}

function interpolateNulls(values) {
  const out = values.slice();
  const valid = [];
  for (let i = 0; i < out.length; i += 1) {
    if (out[i] != null) valid.push(i);
  }
  if (!valid.length) return out.map(() => 0);
  const first = valid[0];
  const last = valid[valid.length - 1];
  for (let i = 0; i < first; i += 1) out[i] = out[first];
  for (let i = last + 1; i < out.length; i += 1) out[i] = out[last];
  let prev = first;
  let i = first + 1;
  while (i <= last) {
    if (out[i] != null) {
      prev = i;
      i += 1;
      continue;
    }
    let next = i;
    while (next <= last && out[next] == null) next += 1;
    const a = out[prev];
    const b = out[next];
    const span = next - prev;
    for (let k = 1; k < span; k += 1) {
      out[prev + k] = a + ((b - a) * k) / span;
    }
    i = next;
  }
  return out;
}

function haversineMeters(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const p1 = (lat1 * Math.PI) / 180;
  const p2 = (lat2 * Math.PI) / 180;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

function latLonToMeters(rows) {
  if (!rows.length) return [];
  const originLat = rows[0].lat;
  const originLon = rows[0].lon;
  const latScale = 111320;
  const lonScale = 111320 * Math.cos((originLat * Math.PI) / 180);
  return rows.map((row) => ({
    ...row,
    x: (row.lon - originLon) * lonScale,
    y: (row.lat - originLat) * -latScale,
  }));
}

function unwrapDegrees(values) {
  if (!values.length) return [];
  const out = [values[0]];
  for (let i = 1; i < values.length; i += 1) {
    let delta = values[i] - (out[i - 1] % 360);
    while (delta > 180) delta -= 360;
    while (delta < -180) delta += 360;
    out.push(out[i - 1] + delta);
  }
  return out;
}

function computeHeadingDegrees(points) {
  const out = new Array(points.length).fill(0);
  for (let i = 1; i < points.length; i += 1) {
    const dx = points[i].x - points[i - 1].x;
    const dy = points[i].y - points[i - 1].y;
    if (Math.abs(dx) + Math.abs(dy) < 1e-6) {
      out[i] = out[i - 1];
      continue;
    }
    out[i] = (Math.atan2(dx, -dy) * 180) / Math.PI;
  }
  if (points.length > 1) out[0] = out[1];
  return out;
}

function derivative(values, dt) {
  const out = new Array(values.length).fill(0);
  if (values.length < 2) return out;
  for (let i = 1; i < values.length; i += 1) {
    out[i] = (values[i] - values[i - 1]) / dt;
  }
  out[0] = out[1] || 0;
  return out;
}

function angleDeltaDeg(target, current) {
  let delta = target - current;
  while (delta > 180) delta -= 360;
  while (delta < -180) delta += 360;
  return delta;
}

function pearsonCorrelation(xs, ys) {
  if (xs.length !== ys.length || xs.length < 3) return 0;
  const meanX = xs.reduce((sum, value) => sum + value, 0) / xs.length;
  const meanY = ys.reduce((sum, value) => sum + value, 0) / ys.length;
  let numerator = 0;
  let denomX = 0;
  let denomY = 0;
  for (let i = 0; i < xs.length; i += 1) {
    const dx = xs[i] - meanX;
    const dy = ys[i] - meanY;
    numerator += dx * dy;
    denomX += dx * dx;
    denomY += dy * dy;
  }
  if (denomX < 1e-9 || denomY < 1e-9) return 0;
  return numerator / Math.sqrt(denomX * denomY);
}

function quaternionNormalize(q) {
  const mag = Math.sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3]);
  if (mag < 1e-9) return [1, 0, 0, 0];
  return q.map((v) => v / mag);
}

function quaternionMultiply(a, b) {
  return [
    a[0] * b[0] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3],
    a[0] * b[1] + a[1] * b[0] + a[2] * b[3] - a[3] * b[2],
    a[0] * b[2] - a[1] * b[3] + a[2] * b[0] + a[3] * b[1],
    a[0] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[0],
  ];
}

function quatRotate(q, v) {
  const vq = [0, v[0], v[1], v[2]];
  const qc = [q[0], -q[1], -q[2], -q[3]];
  const out = quaternionMultiply(quaternionMultiply(q, vq), qc);
  return [out[1], out[2], out[3]];
}

function eulerFromQuaternion(q) {
  const [w, x, y, z] = q;
  const sinr = 2 * (w * x + y * z);
  const cosr = 1 - 2 * (x * x + y * y);
  const roll = Math.atan2(sinr, cosr);
  const sinp = 2 * (w * y - z * x);
  const pitch = Math.abs(sinp) >= 1 ? Math.sign(sinp) * Math.PI / 2 : Math.asin(sinp);
  const siny = 2 * (w * z + x * y);
  const cosy = 1 - 2 * (y * y + z * z);
  const yaw = Math.atan2(siny, cosy);
  return { roll, pitch, yaw };
}

function splitCsvLine(line) {
  const values = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        cur += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (ch === "," && !inQuotes) {
      values.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  values.push(cur);
  return values;
}

function buildGpsRows(rows) {
  return rows
    .filter((row) => row.row_type === "G" || row.row_type === "IG")
    .map((row) => ({
      tickMs: parseInt(row.tick_ms, 10),
      lat: parseNumber(row.lat),
      lon: parseNumber(row.lon),
      speedKmh: parseNumber(row.speed) ?? 0,
      sats: parseNumber(row.sats) ?? 0,
    }))
    .filter((row) => row.lat != null && row.lon != null);
}

function buildImuRows(rows) {
  return rows
    .filter((row) => row.row_type === "I" || row.row_type === "IG")
    .map((row) => ({
      tickMs: parseInt(row.tick_ms, 10),
      acc: [parseNumber(row.acc_x) ?? 0, parseNumber(row.acc_y) ?? 0, parseNumber(row.acc_z) ?? 0],
      gyro: [parseNumber(row.gyro_x) ?? 0, parseNumber(row.gyro_y) ?? 0, parseNumber(row.gyro_z) ?? 0],
    }));
}

function computeGpsCurvatureLean(gpsRows) {
  if (!gpsRows.length) return [];
  const points = latLonToMeters(gpsRows).map((row) => ({
    ...row,
    y: -row.y,
  }));
  const ticks = points.map((row) => row.tickMs / 1000);
  const speedMs = points.map((row) => Math.max(0, row.speedKmh) / 3.6);
  const xs = movingAverage(points.map((row) => row.x), 9);
  const ys = movingAverage(points.map((row) => row.y), 9);
  const gpsLean = new Array(points.length).fill(0);

  for (let index = 0; index < points.length; index += 1) {
    let left = index;
    while (left > 0 && ticks[index] - ticks[left] < 0.9) left -= 1;
    let right = index;
    while (right < points.length - 1 && ticks[right] - ticks[index] < 0.9) right += 1;
    if (left === index || right === index || left === right) continue;

    const ax = xs[left];
    const ay = ys[left];
    const bx = xs[index];
    const by = ys[index];
    const cx = xs[right];
    const cy = ys[right];
    const ab = Math.hypot(bx - ax, by - ay);
    const bc = Math.hypot(cx - bx, cy - by);
    const ac = Math.hypot(cx - ax, cy - ay);
    if (Math.min(ab, bc, ac) < 3 || speedMs[index] < 5) continue;

    const crossValue = ((bx - ax) * (cy - ay)) - ((by - ay) * (cx - ax));
    const area2 = Math.abs(crossValue);
    const denom = ab * bc * ac;
    if (denom <= 1e-6) continue;

    const signedCurvature = (2 * crossValue) / denom;
    const midpointDeviationM = area2 / Math.max(ac, 1e-6);
    if (midpointDeviationM < 1.25 || Math.abs(signedCurvature) < 0.0035) continue;

    const lateralAccel = speedMs[index] * speedMs[index] * signedCurvature;
    gpsLean[index] = clamp((Math.atan(lateralAccel / 9.81) * 180) / Math.PI, -60, 60);
  }

  return movingAverage(gpsLean, 7);
}

function computeGpsLongitudinalAccel(gpsRows) {
  if (!gpsRows.length) return [];
  const ticks = gpsRows.map((row) => row.tickMs / 1000);
  const speeds = centeredMovingAverage(gpsRows.map((row) => Math.max(0, row.speedKmh) / 3.6), 5);
  const accel = new Array(gpsRows.length).fill(0);

  for (let index = 0; index < gpsRows.length; index += 1) {
    let left = index;
    while (left > 0 && ticks[index] - ticks[left] < 0.55) left -= 1;
    let right = index;
    while (right < gpsRows.length - 1 && ticks[right] - ticks[index] < 0.55) right += 1;
    const dt = ticks[right] - ticks[left];
    if (dt < 0.2) continue;
    accel[index] = clamp(((speeds[right] - speeds[left]) / dt) / 9.80665, -1.5, 1.2);
  }

  return centeredMovingAverage(accel, 5);
}

function extractRuntimeValidation(rows) {
  const marker = rows.find((row) => row.row_type === "M" && row.lon === "IMU_VALIDATION");
  if (!marker) return null;
  try {
    return JSON.parse(marker.speed);
  } catch (err) {
    return null;
  }
}

function extractProfile(rows) {
  const marker = rows.find((row) => row.row_type === "M" && row.lon === "IMU_PROFILE");
  if (!marker) return null;
  try {
    return JSON.parse(marker.speed);
  } catch (err) {
    return null;
  }
}

function medianPositiveImuDtSec(imu) {
  const dts = [];
  for (let i = 1; i < imu.length; i += 1) {
    const dt = (imu[i].tickMs - imu[i - 1].tickMs) / 1000;
    if (dt > 0) dts.push(dt);
  }
  return median(dts);
}

function repairLegacyBmi323GyroScale(imu, profile, runtimeValidation) {
  const medianDt = medianPositiveImuDtSec(imu);
  const sampleRateHz = medianDt > 0 ? 1 / medianDt : 0;
  const gyroAbs = [];
  for (const row of imu) {
    gyroAbs.push(Math.abs(row.gyro[0]), Math.abs(row.gyro[1]), Math.abs(row.gyro[2]));
  }
  const gyroAbsP99 = percentile(gyroAbs, 0.99);
  const legacySignature = (
    runtimeValidation?.reason === "gyro_mismatch"
    && sampleRateHz >= 45
    && sampleRateHz <= 60
    && gyroAbsP99 > 250
  );
  if (!legacySignature) {
    return { imu, profile, repair: null };
  }

  const scale = 1 / 16;
  const repairedProfile = profile ? { ...profile } : profile;
  if (repairedProfile?.gyro_bias?.length >= 3) {
    repairedProfile.gyro_bias = repairedProfile.gyro_bias.slice(0, 3).map((value) => value * scale);
  }
  repairedProfile.postprocess_repairs = [
    ...(repairedProfile.postprocess_repairs || []),
    {
      type: "bmi323_gyro_range_scale",
      scale,
      detectedSampleRateHz: Number(sampleRateHz.toFixed(2)),
      gyroAbsP99Before: Number(gyroAbsP99.toFixed(2)),
    },
  ];

  return {
    imu: imu.map((row) => ({
      ...row,
      gyro: row.gyro.map((value) => value * scale),
    })),
    profile: repairedProfile,
    repair: repairedProfile.postprocess_repairs[repairedProfile.postprocess_repairs.length - 1],
  };
}

function joinImuToGps(session) {
  const gps = buildGpsRows(session.rows);
  let imu = buildImuRows(session.rows);
  let profile = extractProfile(session.rows);
  const runtimeValidation = extractRuntimeValidation(session.rows);
  if (!gps.length || !imu.length || !profile?.rotation_matrix) {
    return { error: "Missing GPS, IMU, or IMU profile rotation matrix." };
  }

  const repairResult = repairLegacyBmi323GyroScale(imu, profile, runtimeValidation);
  imu = repairResult.imu;
  profile = repairResult.profile;

  const gpsWithXY = latLonToMeters(gps);
  const headingsWrapped = computeHeadingDegrees(gpsWithXY);
  const headingsUnwrapped = unwrapDegrees(headingsWrapped);
  const gpsTicks = gpsWithXY.map((row) => row.tickMs / 1000);
  const gpsDt = Math.max(0.05, median(gpsTicks.slice(1).map((v, i) => v - gpsTicks[i])));
  const gpsYawRate = movingAverage(derivative(headingsUnwrapped, gpsDt), 3);
  const gpsAccel = computeGpsLongitudinalAccel(gps);
  const gpsLean = computeGpsCurvatureLean(gps);

  for (let i = 0; i < gpsWithXY.length; i += 1) {
    gpsWithXY[i].headingDeg = headingsWrapped[i];
    gpsWithXY[i].yawRateDegS = gpsYawRate[i] || 0;
    gpsWithXY[i].gpsAccelG = gpsAccel[i] || 0;
    gpsWithXY[i].gpsLeanDeg = gpsLean[i] || 0;
  }

  let gpsIndex = 0;
  const joined = [];
  for (const sample of imu) {
    while (gpsIndex + 1 < gpsWithXY.length && gpsWithXY[gpsIndex + 1].tickMs <= sample.tickMs) {
      gpsIndex += 1;
    }
    const gpsRow = gpsWithXY[gpsIndex];
    if (!gpsRow) continue;
    joined.push({
      tickMs: sample.tickMs,
      timeSec: sample.tickMs / 1000,
      gpsTickMs: gpsRow.tickMs,
      lat: gpsRow.lat,
      lon: gpsRow.lon,
      x: gpsRow.x,
      y: gpsRow.y,
      speedKmh: gpsRow.speedKmh,
      speedMs: gpsRow.speedKmh / 3.6,
      sats: gpsRow.sats,
      headingDeg: gpsRow.headingDeg,
      gpsYawRateDegS: gpsRow.yawRateDegS,
      gpsAccelG: gpsRow.gpsAccelG,
      gpsLeanDeg: gpsRow.gpsLeanDeg,
      acc: sample.acc,
      gyro: sample.gyro,
    });
  }
  return { joined, gps: gpsWithXY, profile, runtimeValidation, repair: repairResult.repair };
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function resampleJoined(joined, dtSec) {
  if (!joined.length) return [];
  const out = [];
  let src = 0;
  const start = joined[0].timeSec;
  const end = joined[joined.length - 1].timeSec;
  for (let t = start; t <= end + dtSec * 0.5; t += dtSec) {
    while (src + 1 < joined.length && joined[src + 1].timeSec < t) src += 1;
    const a = joined[src];
    const b = joined[Math.min(src + 1, joined.length - 1)];
    const span = Math.max(1e-6, b.timeSec - a.timeSec);
    const alpha = clamp((t - a.timeSec) / span, 0, 1);
    out.push({
      tickMs: Math.round(t * 1000),
      timeSec: t,
      gpsTickMs: alpha < 0.5 ? a.gpsTickMs : b.gpsTickMs,
      lat: lerp(a.lat, b.lat, alpha),
      lon: lerp(a.lon, b.lon, alpha),
      x: lerp(a.x, b.x, alpha),
      y: lerp(a.y, b.y, alpha),
      speedKmh: lerp(a.speedKmh, b.speedKmh, alpha),
      speedMs: lerp(a.speedMs, b.speedMs, alpha),
      sats: alpha < 0.5 ? a.sats : b.sats,
      headingDeg: lerp(a.headingDeg, b.headingDeg, alpha),
      gpsYawRateDegS: lerp(a.gpsYawRateDegS, b.gpsYawRateDegS, alpha),
      gpsAccelG: lerp(a.gpsAccelG, b.gpsAccelG, alpha),
      gpsLeanDeg: lerp(a.gpsLeanDeg, b.gpsLeanDeg, alpha),
      acc: [0, 1, 2].map((i) => lerp(a.acc[i], b.acc[i], alpha)),
      gyro: [0, 1, 2].map((i) => lerp(a.gyro[i], b.gyro[i], alpha)),
      accBike: a.accBike ? [0, 1, 2].map((i) => lerp(a.accBike[i], b.accBike[i], alpha)) : null,
      gyroBikeDeg: a.gyroBikeDeg ? [0, 1, 2].map((i) => lerp(a.gyroBikeDeg[i], b.gyroBikeDeg[i], alpha)) : null,
      accMag: a.accMag != null ? lerp(a.accMag, b.accMag, alpha) : null,
    });
  }
  return out;
}

function computeUniformDtSec(joined) {
  const dts = [];
  for (let i = 1; i < joined.length; i += 1) {
    const dt = joined[i].timeSec - joined[i - 1].timeSec;
    if (dt > 0.001 && dt < 0.2) dts.push(dt);
  }
  const medianDt = Math.max(0.005, median(dts.length ? dts : [0.0125]));
  return medianDt;
}

function preprocessCalibrated(joined, profile) {
  const forward = profile.rotation_matrix[0];
  const lateral = profile.rotation_matrix[1];
  const up = profile.rotation_matrix[2];
  const gyroBias = profile.gyro_bias || [0, 0, 0];
  return joined.map((row) => {
    const accBike = [dot(row.acc, forward), dot(row.acc, lateral), dot(row.acc, up)];
    const gyroBikeDeg = [
      dot(row.gyro, forward) - gyroBias[0],
      dot(row.gyro, lateral) - gyroBias[1],
      dot(row.gyro, up) - gyroBias[2],
    ];
    return {
      ...row,
      accBike,
      gyroBikeDeg,
      accMag: norm(accBike),
    };
  });
}

function addChannelSplits(rows, config) {
  const splitWindow = Math.max(1, Math.round((config.vibrationWindowMs || 500) / (config.dtSec * 1000)));
  for (const axis of ["accBike0", "accBike1", "accBike2"]) {
    const series = rows.map((row) => row[axis]);
    const low = movingAverage(series, splitWindow);
    rows.forEach((row, index) => {
      row[axis + "Low"] = low[index];
      row[axis + "High"] = series[index] - low[index];
    });
  }
}

function complementaryFusion(rows, config) {
  if (!rows.length) return [];
  const dt = rows.length > 1 ? rows[1].timeSec - rows[0].timeSec : 0.01;
  const tau = clamp(config.fusionTauSec || 0.45, 0.05, 5);
  const alpha = tau / (tau + dt);
  let roll = Math.atan2(rows[0].accBike[1], rows[0].accBike[2]);
  let pitch = Math.atan2(-rows[0].accBike[0], Math.sqrt(rows[0].accBike[1] ** 2 + rows[0].accBike[2] ** 2));
  let yaw = 0;
  const out = [];

  for (const row of rows) {
    const gx = (row.gyroBikeDeg[0] * Math.PI) / 180;
    const gy = (row.gyroBikeDeg[1] * Math.PI) / 180;
    const gz = (row.gyroBikeDeg[2] * Math.PI) / 180;
    roll += gx * dt;
    pitch += gy * dt;
    yaw += gz * dt;

    const accelTrust = clamp(1 - Math.abs(row.accMag - 1) / Math.max(0.05, config.accMagTol), 0, 1);
    const dynamicSuppression = row.speedKmh < config.lowSpeedKmh ? 0.25 : 1;
    const corr = (1 - alpha) * accelTrust * dynamicSuppression;
    const rollAcc = Math.atan2(row.accBike[1], row.accBike[2]);
    const pitchAcc = Math.atan2(-row.accBike[0], Math.sqrt(row.accBike[1] ** 2 + row.accBike[2] ** 2));
    roll = roll * (1 - corr) + rollAcc * corr;
    pitch = pitch * (1 - corr) + pitchAcc * corr;

    out.push({
      rollDeg: (roll * 180) / Math.PI,
      pitchDeg: (pitch * 180) / Math.PI,
      yawDeg: (yaw * 180) / Math.PI,
      accelTrust,
    });
  }
  return out;
}

function mahonyFusion(rows, config) {
  if (!rows.length) return [];
  const dt = rows.length > 1 ? rows[1].timeSec - rows[0].timeSec : 0.01;
  const kpBase = config.mahonyKp || 0.5;
  const kiBase = config.mahonyKi || 0.02;
  let q = [1, 0, 0, 0];
  let integral = [0, 0, 0];
  const out = [];

  for (const row of rows) {
    let [gx, gy, gz] = row.gyroBikeDeg.map((v) => (v * Math.PI) / 180);
    const accNorm = normalize(row.accBike);
    const gravityEst = quatRotate(q, [0, 0, 1]);
    const error = cross(gravityEst, accNorm);
    const accelTrust = clamp(1 - Math.abs(row.accMag - 1) / Math.max(0.05, config.accMagTol), 0, 1);
    const speedTrust = row.speedKmh < config.lowSpeedKmh ? 0.3 : 1;
    const trust = accelTrust * speedTrust;
    const kp = kpBase * trust;
    const ki = kiBase * trust;
    integral[0] += error[0] * ki * dt;
    integral[1] += error[1] * ki * dt;
    integral[2] += error[2] * ki * dt;
    gx += kp * error[0] + integral[0];
    gy += kp * error[1] + integral[1];
    gz += kp * error[2] + integral[2];

    const qDot = quaternionMultiply(q, [0, gx, gy, gz]).map((v) => 0.5 * v);
    q = quaternionNormalize([
      q[0] + qDot[0] * dt,
      q[1] + qDot[1] * dt,
      q[2] + qDot[2] * dt,
      q[3] + qDot[3] * dt,
    ]);
    const euler = eulerFromQuaternion(q);
    out.push({
      rollDeg: (euler.roll * 180) / Math.PI,
      pitchDeg: (euler.pitch * 180) / Math.PI,
      yawDeg: (euler.yaw * 180) / Math.PI,
      accelTrust,
      quaternion: q.slice(),
    });
  }
  return out;
}

function computeConfidence(row, fused, config) {
  let confidence = 1;
  if (config.maskLowSpeed) {
    if (row.speedKmh < config.lowSpeedKmh) confidence *= 0.35;
    else if (row.speedKmh < config.turnSpeedKmh) confidence *= 0.7;
  }
  if (config.maskAccelMagnitude) {
    confidence *= clamp(1 - Math.abs(row.accMag - 1) / Math.max(0.05, config.accMagTol * 1.25), 0.1, 1);
    if (Math.abs(row.accBike[2] - 1) > 0.3) confidence *= 0.7;
  }
  if (config.maskPitch && Math.abs(fused.pitchDeg) > config.pitchWarnDeg) confidence *= 0.55;
  if (config.maskLongitudinalAccel) {
    if (Math.abs(row.gpsAccelG) > 0.28) confidence *= 0.7;
    if (Math.abs(row.accBike[0]) > 0.4) confidence *= 0.75;
  }
  if (config.maskWeakTurnEvidence && Math.abs(row.gpsYawRateDegS) < 2 && row.speedKmh > config.turnSpeedKmh && Math.abs(fused.rollDeg) > 18) confidence *= 0.55;
  if (config.maskLateralVibration && Math.abs(row.accBike1High || 0) > (config.lateralVibeThresholdG || 0.06)) confidence *= 0.45;
  if (config.maskVerticalVibration && Math.abs(row.accBike2High || 0) > (config.verticalVibeThresholdG || 0.16)) confidence *= 0.45;
  return clamp(confidence, 0.05, 1);
}

function enrichFusedFrames(rows, fusedSeries, config, algorithm) {
  const leanRaw = fusedSeries.map((v) => v.rollDeg);
  const smoothWindow = Math.max(1, Math.round((config.smoothingMs || 250) / (config.dtSec * 1000)));
  const leanFiltered = maybeSmooth(interpolateNulls(maybeHampel(leanRaw, 12, 3.0, config.enableHampelFilter)), smoothWindow, config.enableMovingAverage);
  const forwardRaw = rows.map((row) => row.accBike[0]);
  const forwardFiltered = maybeSmooth(interpolateNulls(maybeHampel(forwardRaw, 12, 3.5, config.enableHampelFilter)), smoothWindow, config.enableMovingAverage);

  const frames = rows.map((row, index) => {
    const fused = fusedSeries[index];
    const leanDegRaw = leanFiltered[index];
    const forwardG = forwardFiltered[index];
    const accelG = Math.max(0, forwardG);
    const brakeG = Math.max(0, -forwardG);
    const confidence = computeConfidence(row, { ...fused, rollDeg: leanDegRaw }, config);
    const turnEvidence = clamp(Math.abs(row.gpsYawRateDegS) / 12, 0, 1);
    return {
      tickMs: row.tickMs,
      gpsTickMs: row.gpsTickMs,
      lat: row.lat,
      lon: row.lon,
      x: row.x,
      y: row.y,
      speedKmh: row.speedKmh,
      sats: row.sats,
      headingDeg: row.headingDeg,
      leanDegRaw,
      leanDeg: leanDegRaw,
      gpsLeanDeg: row.gpsLeanDeg,
      pitchDeg: fused.pitchDeg,
      yawDeg: fused.yawDeg,
      accelG,
      brakeG,
      confidence,
      accelTrust: fused.accelTrust,
      turnEvidence,
      upG: row.accBike[2],
      latG: row.accBike[1],
      latHighG: row.accBike1High || 0,
      upHighG: row.accBike2High || 0,
      forwardRawG: row.accBike[0],
      accMag: row.accMag,
      gpsYawRateDegS: row.gpsYawRateDegS,
      gpsAccelG: row.gpsAccelG,
      algorithm,
    };
  });
  if (config.holdMaskedLean) {
    let heldLean = frames.length ? frames[0].leanDegRaw : 0;
    for (const frame of frames) {
      if (frame.confidence >= 0.5) {
        heldLean = frame.leanDegRaw;
        frame.masked = false;
      } else {
        frame.leanDeg = heldLean;
        frame.masked = true;
      }
    }
  } else {
    for (const frame of frames) {
      frame.masked = frame.confidence < 0.5;
    }
  }
  return frames;
}

function summarizeFrames(frames, gps, profile, dtSec, processorMeta) {
  const leanAbs = frames.map((f) => Math.abs(f.leanDeg));
  const accelValues = frames.map((f) => f.accelG);
  const brakeValues = frames.map((f) => f.brakeG);
  const confidenceValues = frames.map((f) => f.confidence);
  const totalDistanceM = gps.reduce((acc, point, index) => {
    if (!index) return 0;
    return acc + haversineMeters(gps[index - 1].lat, gps[index - 1].lon, point.lat, point.lon);
  }, 0);
  return {
    gpsPoints: gps.length,
    imuFrames: frames.length,
    resampledHz: 1 / dtSec,
    medianDtMs: dtSec * 1000,
    totalDistanceM,
    maxLeanDeg: Math.max(...leanAbs),
    maxAccelG: Math.max(...accelValues),
    maxBrakeG: Math.max(...brakeValues),
    meanConfidence: confidenceValues.reduce((a, b) => a + b, 0) / Math.max(1, confidenceValues.length),
    lowConfidenceFraction: confidenceValues.filter((v) => v < 0.5).length / Math.max(1, confidenceValues.length),
    profileName: profile.name || profile.label || profile.id || "unknown",
    profileQuality: profile.quality_score ?? null,
    repairs: profile.postprocess_repairs || [],
    ...processorMeta,
  };
}

function calibratedProjectionProcessor(session, config, options = {}) {
  const joinedData = joinImuToGps(session);
  if (joinedData.error) {
    return { frames: [], stats: { error: joinedData.error }, algorithm: options.name || "unknown", config };
  }
  const calibrated = preprocessCalibrated(joinedData.joined, joinedData.profile);
  const dtSec = computeUniformDtSec(calibrated);
  const rows = resampleJoined(calibrated, dtSec);
  const procConfig = { ...config, dtSec };
  rows.forEach((row) => {
    row.accBike0 = row.accBike[0];
    row.accBike1 = row.accBike[1];
    row.accBike2 = row.accBike[2];
  });
  addChannelSplits(rows, procConfig);
  const leanGain = config.leanGain || 1;
  const upFloorG = config.upFloorG ?? 0.15;
  const rawLean = rows.map((row) => leanGain * (Math.atan2(row.accBike[1], Math.max(upFloorG, row.accBike[2])) * 180) / Math.PI);
  const leanValid = rows.map((row, i) => {
    if (row.speedKmh < config.minSpeed) return false;
    if (row.accBike[2] < config.upMinG) return false;
    if (Math.abs(row.accMag - 1) > config.accMagTol) return false;
    if (i > 0) {
      const rate = Math.abs(rawLean[i] - rawLean[i - 1]) / dtSec;
      if (rate > config.leanRateLimit) return false;
    }
    return true;
  });
  const smoothWindow = Math.max(1, Math.round((config.smoothingMs || 250) / (dtSec * 1000)));
  const lean = maybeSmooth(interpolateNulls(maybeHampel(rawLean.map((v, i) => (leanValid[i] ? v : null)), 12, 3.0, config.enableHampelFilter)), smoothWindow, config.enableMovingAverage);
  const forward = maybeSmooth(interpolateNulls(maybeHampel(rows.map((row) => row.accBike[0]), 12, 3.5, config.enableHampelFilter)), smoothWindow, config.enableMovingAverage);
  let heldLean = lean.length ? lean[0] : 0;
  const frames = rows.map((row, index) => {
    const confidence = computeConfidence(row, { pitchDeg: (Math.atan2(-row.accBike[0], Math.sqrt(row.accBike[1] ** 2 + row.accBike[2] ** 2)) * 180) / Math.PI, rollDeg: lean[index] }, procConfig);
    let displayLean = lean[index];
    let masked = confidence < 0.5;
    if (procConfig.holdMaskedLean) {
      if (!masked) heldLean = lean[index];
      else displayLean = heldLean;
    }
    return {
      tickMs: row.tickMs,
      gpsTickMs: row.gpsTickMs,
      lat: row.lat,
      lon: row.lon,
      x: row.x,
      y: row.y,
      speedKmh: row.speedKmh,
      sats: row.sats,
      headingDeg: row.headingDeg,
      leanDegRaw: lean[index],
      leanDeg: displayLean,
      gpsLeanDeg: row.gpsLeanDeg,
      pitchDeg: (Math.atan2(-row.accBike[0], Math.sqrt(row.accBike[1] ** 2 + row.accBike[2] ** 2)) * 180) / Math.PI,
      yawDeg: 0,
      accelG: Math.max(0, forward[index]),
      brakeG: Math.max(0, -forward[index]),
      confidence: leanValid[index] ? confidence : Math.min(confidence, 0.25),
      accelTrust: clamp(1 - Math.abs(row.accMag - 1) / Math.max(0.05, config.accMagTol), 0, 1),
      turnEvidence: clamp(Math.abs(row.gpsYawRateDegS) / 12, 0, 1),
      upG: row.accBike[2],
      latG: row.accBike[1],
      latHighG: row.accBike1High || 0,
      upHighG: row.accBike2High || 0,
      forwardRawG: row.accBike[0],
      accMag: row.accMag,
      gpsYawRateDegS: row.gpsYawRateDegS,
      gpsAccelG: row.gpsAccelG,
      masked,
      algorithm: options.name || "projection",
    };
  });
  return {
    frames,
    stats: summarizeFrames(frames, joinedData.gps, joinedData.profile, dtSec, {
      fusion: "none",
      validLeanFraction: leanValid.filter(Boolean).length / Math.max(1, leanValid.length),
    }),
    algorithm: options.name || "projection",
    config: procConfig,
  };
}

function crudeCalibratedProcessor(session, config, options = {}) {
  const joinedData = joinImuToGps(session);
  if (joinedData.error) {
    return { frames: [], stats: { error: joinedData.error }, algorithm: options.name || "unknown", config };
  }
  const calibrated = preprocessCalibrated(joinedData.joined, joinedData.profile);
  const dtSec = computeUniformDtSec(calibrated);
  const rows = resampleJoined(calibrated, dtSec);
  const procConfig = { ...config, dtSec };
  rows.forEach((row) => {
    row.accBike0 = row.accBike[0];
    row.accBike1 = row.accBike[1];
    row.accBike2 = row.accBike[2];
  });
  addChannelSplits(rows, procConfig);

  const leanGain = config.leanGain || 1;
  const upFloorG = config.upFloorG ?? 0.15;
  const rawLean = rows.map((row) => leanGain * (Math.atan2(row.accBike[1], Math.max(upFloorG, row.accBike[2])) * 180) / Math.PI);
  const rawPitch = rows.map((row) => (Math.atan2(-row.accBike[0], Math.sqrt(row.accBike[1] ** 2 + row.accBike[2] ** 2)) * 180) / Math.PI);
  const smoothWindow = Math.max(1, Math.round((config.smoothingMs || 250) / (dtSec * 1000)));
  const leanSeries = maybeSmooth(interpolateNulls(maybeHampel(rawLean, 12, 3.0, config.enableHampelFilter)), smoothWindow, config.enableMovingAverage);
  const forwardSeries = maybeSmooth(interpolateNulls(maybeHampel(rows.map((row) => row.accBike[0]), 12, 3.5, config.enableHampelFilter)), smoothWindow, config.enableMovingAverage);

  let heldLean = leanSeries.length ? leanSeries[0] : 0;
  const frames = rows.map((row, index) => {
    const fusedLike = { rollDeg: leanSeries[index], pitchDeg: rawPitch[index], yawDeg: 0, accelTrust: 1 };
    const confidence = computeConfidence(row, fusedLike, procConfig);
    let displayLean = leanSeries[index];
    let masked = confidence < 0.5;
    if (procConfig.holdMaskedLean) {
      if (!masked) heldLean = leanSeries[index];
      else displayLean = heldLean;
    }
    return {
      tickMs: row.tickMs,
      gpsTickMs: row.gpsTickMs,
      lat: row.lat,
      lon: row.lon,
      x: row.x,
      y: row.y,
      speedKmh: row.speedKmh,
      sats: row.sats,
      headingDeg: row.headingDeg,
      leanDegRaw: leanSeries[index],
      leanDeg: displayLean,
      gpsLeanDeg: row.gpsLeanDeg,
      pitchDeg: rawPitch[index],
      yawDeg: 0,
      accelG: Math.max(0, forwardSeries[index]),
      brakeG: Math.max(0, -forwardSeries[index]),
      confidence,
      accelTrust: 1,
      turnEvidence: clamp(Math.abs(row.gpsYawRateDegS) / 12, 0, 1),
      upG: row.accBike[2],
      latG: row.accBike[1],
      latHighG: row.accBike1High || 0,
      upHighG: row.accBike2High || 0,
      forwardRawG: row.accBike[0],
      accMag: row.accMag,
      gpsYawRateDegS: row.gpsYawRateDegS,
      gpsAccelG: row.gpsAccelG,
      masked,
      algorithm: options.name || "crudeCalibrated",
    };
  });
  return {
    frames,
    stats: summarizeFrames(frames, joinedData.gps, joinedData.profile, dtSec, {
      fusion: "none",
      validLeanFraction: frames.filter((f) => f.confidence >= 0.5).length / Math.max(1, frames.length),
    }),
    algorithm: options.name || "crudeCalibrated",
    config: procConfig,
  };
}

function rawAccelLeanProcessor(session, config, options = {}) {
  const joinedData = joinImuToGps(session);
  if (joinedData.error) {
    return { frames: [], stats: { error: joinedData.error }, algorithm: options.name || "unknown", config };
  }
  const calibrated = preprocessCalibrated(joinedData.joined, joinedData.profile);
  const dtSec = computeUniformDtSec(calibrated);
  const rows = resampleJoined(calibrated, dtSec);
  const procConfig = { ...config, dtSec };

  const frames = rows.map((row) => {
    const leanDeg = (Math.atan2(row.accBike[1], row.accBike[2]) * 180) / Math.PI;
    const pitchDeg = (Math.atan2(-row.accBike[0], Math.sqrt(row.accBike[1] ** 2 + row.accBike[2] ** 2)) * 180) / Math.PI;
    return {
      tickMs: row.tickMs,
      gpsTickMs: row.gpsTickMs,
      lat: row.lat,
      lon: row.lon,
      x: row.x,
      y: row.y,
      speedKmh: row.speedKmh,
      sats: row.sats,
      headingDeg: row.headingDeg,
      leanDegRaw: leanDeg,
      leanDeg,
      gpsLeanDeg: row.gpsLeanDeg,
      pitchDeg,
      yawDeg: 0,
      accelG: Math.max(0, row.accBike[0]),
      brakeG: Math.max(0, -row.accBike[0]),
      confidence: 1,
      accelTrust: 1,
      turnEvidence: clamp(Math.abs(row.gpsYawRateDegS) / 12, 0, 1),
      upG: row.accBike[2],
      latG: row.accBike[1],
      latHighG: 0,
      upHighG: 0,
      forwardRawG: row.accBike[0],
      accMag: row.accMag,
      gpsYawRateDegS: row.gpsYawRateDegS,
      gpsAccelG: row.gpsAccelG,
      masked: false,
      algorithm: options.name || "rawAccelLean",
    };
  });

  return {
    frames,
    stats: summarizeFrames(frames, joinedData.gps, joinedData.profile, dtSec, {
      fusion: "none",
      validLeanFraction: 1,
    }),
    algorithm: options.name || "rawAccelLean",
    config: procConfig,
  };
}

function buildFixedTelemetryRows(rows) {
  const dataRows = [];
  const gpsRows = [];
  const gpsIndices = [];
  for (const row of rows) {
    if (row.row_type !== "I" && row.row_type !== "G" && row.row_type !== "IG") continue;
    const tickMs = parseInt(row.tick_ms, 10);
    if (!Number.isFinite(tickMs)) continue;
    const item = {
      rowType: row.row_type,
      tickMs,
      acc: [parseNumber(row.acc_x) ?? 0, parseNumber(row.acc_y) ?? 0, parseNumber(row.acc_z) ?? 0],
      gyro: [parseNumber(row.gyro_x) ?? 0, parseNumber(row.gyro_y) ?? 0, parseNumber(row.gyro_z) ?? 0],
      lat: parseNumber(row.lat),
      lon: parseNumber(row.lon),
      speedKmh: parseNumber(row.speed),
      sats: parseNumber(row.sats) ?? 0,
    };
    const index = dataRows.length;
    dataRows.push(item);
    if ((row.row_type === "G" || row.row_type === "IG") && item.lat != null && item.lon != null) {
      gpsIndices.push(index);
      gpsRows.push({ tickMs, lat: item.lat, lon: item.lon, speedKmh: item.speedKmh ?? 0, sats: item.sats });
    }
  }
  return { dataRows, gpsRows, gpsIndices };
}

function repairGyroScaleForCalibratedV2(dataRows, profile, config = {}) {
  const dts = [];
  const gyroAbs = [];
  for (let i = 1; i < dataRows.length; i += 1) {
    const dt = (dataRows[i].tickMs - dataRows[i - 1].tickMs) / 1000;
    if (dt > 0) dts.push(dt);
  }
  for (const row of dataRows) {
    gyroAbs.push(Math.abs(row.gyro[0]), Math.abs(row.gyro[1]), Math.abs(row.gyro[2]));
  }
  const sampleRateHz = dts.length ? 1 / median(dts) : 0;
  const gyroAbsP99 = percentile(gyroAbs, 0.99);
  const shouldRepair = sampleRateHz >= 45 && sampleRateHz <= 60 && gyroAbsP99 > 250;
  const configuredScale = Number(config.gyroScale);
  const hasConfiguredScale = Number.isFinite(configuredScale) && configuredScale > 0;
  const scale = hasConfiguredScale ? configuredScale : (shouldRepair ? 1 / 16 : 1);
  const gyroBias = (profile.gyro_bias || [0, 0, 0]).slice(0, 3);
  while (gyroBias.length < 3) gyroBias.push(0);
  return {
    scale,
    gyroBias: gyroBias.map((value) => value * scale),
    repair: hasConfiguredScale ? {
      type: "manual_gyro_scale",
      scale,
      detectedSampleRateHz: Number(sampleRateHz.toFixed(2)),
      gyroAbsP99Before: Number(gyroAbsP99.toFixed(2)),
    } : shouldRepair ? {
      type: "bmi323_gyro_range_scale",
      scale,
      detectedSampleRateHz: Number(sampleRateHz.toFixed(2)),
      gyroAbsP99Before: Number(gyroAbsP99.toFixed(2)),
    } : null,
  };
}

function calibratedV2AccelLeanDeg(row, rotation, accelBias) {
  const accel = [
    row.acc[0] - accelBias[0],
    row.acc[1] - accelBias[1],
    row.acc[2] - accelBias[2],
  ];
  return (Math.atan2(-dot(accel, rotation[1]), Math.max(0.15, dot(accel, rotation[2]))) * 180) / Math.PI;
}

function profileStaticLeanOffsetDeg(profile) {
  const rotation = profile.rotation_matrix;
  const gravity = profile.gravity_vector;
  if (!rotation || !gravity || gravity.length < 3) return 0;
  const lateral = dot(gravity, rotation[1]);
  const up = dot(gravity, rotation[2]);
  return (Math.atan2(-lateral, Math.max(0.15, up)) * 180) / Math.PI;
}

function softTrust(value, good, bad) {
  if (good === bad) return value <= good ? 1 : 0;
  if (good < bad) return clamp((bad - value) / (bad - good), 0, 1);
  return clamp((value - bad) / (good - bad), 0, 1);
}

function calibratedV2CorrectionGain(forceError, aUp, aLong, rollRate, gyroActivity, options) {
  const strongGain = Number.isFinite(options.accelCorrectionStrong) ? options.accelCorrectionStrong : 0.045;
  const weakGain = Number.isFinite(options.accelCorrectionWeak) ? options.accelCorrectionWeak : 0.010;
  if (options.accelBlendMode === "soft") {
    const forceTrust = softTrust(forceError, 0.08, 0.24);
    const upTrust = softTrust(aUp, 0.75, 0.45);
    const longTrust = softTrust(Math.abs(aLong), 0.10, 0.45);
    const rollTrust = softTrust(Math.abs(rollRate), 45, 160);
    const gyroTrust = softTrust(gyroActivity, 180, 520);
    const trust = forceTrust * upTrust * longTrust * rollTrust * gyroTrust;
    return weakGain + ((strongGain - weakGain) * trust);
  }

  const stableForce = forceError < 0.16 && aUp > 0.65 && Math.abs(aLong) < 0.35;
  const stableRotation = Math.abs(rollRate) < 90 && gyroActivity < 450;
  if (stableForce && stableRotation) return strongGain;
  if (forceError < 0.24 && aUp > 0.45 && Math.abs(rollRate) < 140) return weakGain;
  return 0;
}

function runCalibratedV2Filter(dataRows, profile, rollAxis, gyroRepair, smoothingSamples = 5, correctionOptions = {}) {
  const rotation = profile.rotation_matrix;
  const accelBias = (profile.accel_bias || [0, 0, 0]).slice(0, 3);
  while (accelBias.length < 3) accelBias.push(0);
  let roll = clamp(calibratedV2AccelLeanDeg(dataRows[0], rotation, accelBias), -45, 45);
  const leans = [];

  for (let index = 0; index < dataRows.length; index += 1) {
    const row = dataRows[index];
    const dt = index === 0 ? 0.02 : clamp((row.tickMs - dataRows[index - 1].tickMs) / 1000, 0.005, 0.08);
    const gyro = [
      (row.gyro[0] * gyroRepair.scale) - gyroRepair.gyroBias[0],
      (row.gyro[1] * gyroRepair.scale) - gyroRepair.gyroBias[1],
      (row.gyro[2] * gyroRepair.scale) - gyroRepair.gyroBias[2],
    ];
    const rollRate = dot(gyro, rollAxis);
    roll += rollRate * dt;

    const accel = [
      row.acc[0] - accelBias[0],
      row.acc[1] - accelBias[1],
      row.acc[2] - accelBias[2],
    ];
    const accMag = norm(accel);
    const aLong = dot(accel, rotation[0]);
    const aLat = dot(accel, rotation[1]);
    const aUp = dot(accel, rotation[2]);
    const accelLean = (Math.atan2(-aLat, Math.max(0.15, aUp)) * 180) / Math.PI;
    const gyroActivity = norm(gyro);
    const forceError = Math.abs(accMag - 1);
    const correctionGain = calibratedV2CorrectionGain(forceError, aUp, aLong, rollRate, gyroActivity, correctionOptions);
    if (correctionGain) roll += correctionGain * angleDeltaDeg(accelLean, roll);
    roll = clamp(roll, -60, 60);
    leans.push(roll);
  }
  return movingAverage(leans, smoothingSamples);
}

function selectCalibratedV2Axis(dataRows, profile, gpsIndices, gpsLeans, gyroRepair, smoothingSamples, correctionOptions) {
  const rotation = profile.rotation_matrix;
  const candidates = [
    { name: "calibrated_forward", axis: rotation[0] },
    { name: "negative_calibrated_forward", axis: rotation[0].map((value) => -value) },
    { name: "calibrated_lateral", axis: rotation[1] },
    { name: "negative_calibrated_lateral", axis: rotation[1].map((value) => -value) },
    { name: "calibrated_up", axis: rotation[2] },
    { name: "negative_calibrated_up", axis: rotation[2].map((value) => -value) },
    { name: "raw_x", axis: [1, 0, 0] },
    { name: "raw_y", axis: [0, 1, 0] },
    { name: "raw_z", axis: [0, 0, 1] },
  ];
  let best = {
    name: "calibrated_forward",
    leans: runCalibratedV2Filter(dataRows, profile, rotation[0], gyroRepair, smoothingSamples, correctionOptions),
    score: -1,
  };
  for (const candidate of candidates) {
    const leans = runCalibratedV2Filter(dataRows, profile, candidate.axis, gyroRepair, smoothingSamples, correctionOptions);
    const sampled = gpsIndices.map((index) => leans[index]).slice(0, gpsLeans.length);
    const score = pearsonCorrelation(sampled, gpsLeans.slice(0, sampled.length));
    if (sampled.length >= 10 && score > best.score) {
      best = { ...candidate, leans, score };
    }
  }
  return best;
}

function robustMean(values) {
  if (!values.length) return 0;
  if (values.length < 4) return values.reduce((sum, value) => sum + value, 0) / values.length;
  const center = median(values);
  const deviations = values.map((value) => Math.abs(value - center));
  const mad = median(deviations);
  const threshold = Math.max(0.08, 2.5 * 1.4826 * mad);
  const kept = values.filter((value) => Math.abs(value - center) <= threshold);
  return (kept.length ? kept : [center]).reduce((sum, value) => sum + value, 0) / (kept.length || 1);
}

function sampleAccelAxisAtGps(dataRows, gpsIndices, axis) {
  return gpsIndices.map((gpsIndex) => {
    const start = Math.max(0, gpsIndex - 2);
    const end = Math.min(dataRows.length, gpsIndex + 3);
    const values = [];
    for (let index = start; index < end; index += 1) {
      values.push(dot(dataRows[index].acc, axis));
    }
    return robustMean(values);
  });
}

function centerImuForwardSamples(samples, gpsAccel, gpsRows, smoothingSamples = 5) {
  const quiet = samples.filter((value, index) => Math.abs(gpsAccel[index] || 0) < 0.04 && (gpsRows[index]?.speedKmh || 0) > 15);
  const baseline = median(quiet.length >= 20 ? quiet : samples);
  return {
    baseline,
    samples: centeredMovingAverage(samples.map((value) => value - baseline), smoothingSamples),
  };
}

function selectCalibratedV2AccelAxis(dataRows, profile, gpsIndices, gpsRows, gpsAccel, smoothingSamples) {
  const rotation = profile.rotation_matrix;
  const candidates = [
    { name: "calibrated_forward", axis: normalize(rotation[0]) },
    { name: "negative_calibrated_forward", axis: normalize(rotation[0].map((value) => -value)) },
    { name: "calibrated_lateral", axis: normalize(rotation[1]) },
    { name: "negative_calibrated_lateral", axis: normalize(rotation[1].map((value) => -value)) },
    { name: "raw_x", axis: [1, 0, 0] },
    { name: "negative_raw_x", axis: [-1, 0, 0] },
    { name: "raw_y", axis: [0, 1, 0] },
    { name: "negative_raw_y", axis: [0, -1, 0] },
    { name: "raw_z", axis: [0, 0, 1] },
    { name: "negative_raw_z", axis: [0, 0, -1] },
  ];
  const mask = gpsAccel
    .map((value, index) => ({ value, index }))
    .filter(({ value, index }) => Math.abs(value) >= 0.035 && (gpsRows[index]?.speedKmh || 0) >= 15)
    .map(({ index }) => index);
  let best = {
    name: "calibrated_forward",
    axis: candidates[0].axis,
    samples: [],
    baseline: 0,
    score: -1,
  };

  for (const candidate of candidates) {
    const rawSamples = sampleAccelAxisAtGps(dataRows, gpsIndices, candidate.axis);
    const centered = centerImuForwardSamples(rawSamples, gpsAccel, gpsRows, smoothingSamples);
    const sampledImu = mask.length >= 10 ? mask.map((index) => centered.samples[index]) : centered.samples;
    const sampledGps = mask.length >= 10 ? mask.map((index) => gpsAccel[index]) : gpsAccel;
    const score = pearsonCorrelation(sampledImu, sampledGps);
    if (score > best.score) {
      best = { ...candidate, samples: centered.samples, baseline: centered.baseline, score };
    }
  }

  return best;
}

function calibratedV2Processor(session, config, options = {}) {
  const profile = extractProfile(session.rows);
  if (!profile?.rotation_matrix) {
    return { frames: [], stats: { error: "Missing IMU profile rotation matrix." }, algorithm: options.name || "calibratedV2", config };
  }
  const { dataRows, gpsRows, gpsIndices } = buildFixedTelemetryRows(session.rows);
  if (!dataRows.length || !gpsRows.length) {
    return { frames: [], stats: { error: "Missing GPS or IMU rows." }, algorithm: options.name || "calibratedV2", config };
  }
  const gpsWithXY = latLonToMeters(gpsRows);
  const gpsLeans = computeGpsCurvatureLean(gpsRows);
  const gpsAccel = computeGpsLongitudinalAccel(gpsRows);
  const gyroRepair = repairGyroScaleForCalibratedV2(dataRows, profile, config);
  const smoothingSamples = clamp(Math.round(Number(config.smoothingSamples) || 5), 1, 51);
  const correctionOptions = {
    accelBlendMode: config.accelBlendMode || "hard",
    accelCorrectionStrong: Number(config.accelCorrectionStrong),
    accelCorrectionWeak: Number(config.accelCorrectionWeak),
  };
  const axisResult = selectCalibratedV2Axis(dataRows, profile, gpsIndices, gpsLeans, gyroRepair, smoothingSamples, correctionOptions);
  const accelAxisResult = selectCalibratedV2AccelAxis(dataRows, profile, gpsIndices, gpsRows, gpsAccel, smoothingSamples);
  const calibratedLeanGain = Number.isFinite(config.calibratedLeanGain) ? config.calibratedLeanGain : 1;
  const leanOffsetDeg = Number.isFinite(config.leanOffsetDeg) ? config.leanOffsetDeg : 0;
  const longitudinalGain = Number.isFinite(config.longitudinalGain) ? config.longitudinalGain : 1;
  const staticLeanOffsetDeg = profileStaticLeanOffsetDeg(profile);

  for (let i = 1; i < gpsWithXY.length; i += 1) {
    const dx = gpsWithXY[i].x - gpsWithXY[i - 1].x;
    const dy = gpsWithXY[i].y - gpsWithXY[i - 1].y;
    gpsWithXY[i].headingDeg = Math.abs(dx) + Math.abs(dy) > 1e-6 ? (Math.atan2(dx, -dy) * 180) / Math.PI : gpsWithXY[i - 1].headingDeg || 0;
  }
  if (gpsWithXY.length > 1) gpsWithXY[0].headingDeg = gpsWithXY[1].headingDeg;

  const frames = gpsRows.map((gpsRow, index) => {
    const sourceIndex = gpsIndices[index];
    const source = dataRows[sourceIndex];
    const leanDeg = clamp(((axisResult.leans[sourceIndex] ?? 0) * calibratedLeanGain) + leanOffsetDeg, -60, 60);
    const gpsLeanDeg = gpsLeans[index] ?? 0;
    const imuForwardG = (accelAxisResult.samples[index] ?? 0) * longitudinalGain;
    const gpsAccelG = gpsAccel[index] ?? 0;
    return {
      tickMs: source.tickMs,
      gpsTickMs: gpsRow.tickMs,
      lat: gpsRow.lat,
      lon: gpsRow.lon,
      x: gpsWithXY[index].x,
      y: gpsWithXY[index].y,
      speedKmh: gpsRow.speedKmh,
      sats: gpsRow.sats,
      headingDeg: gpsWithXY[index].headingDeg || 0,
      leanDegRaw: leanDeg,
      leanDeg,
      gpsLeanDeg,
      pitchDeg: 0,
      yawDeg: 0,
      accelG: Math.max(0, imuForwardG),
      brakeG: Math.max(0, -imuForwardG),
      confidence: 1,
      accelTrust: 1,
      turnEvidence: clamp(Math.abs(gpsLeanDeg) / 30, 0, 1),
      upG: 0,
      latG: 0,
      latHighG: 0,
      upHighG: 0,
      forwardRawG: imuForwardG,
      accMag: norm(source.acc),
      gpsYawRateDegS: 0,
      gpsAccelG,
      masked: false,
      algorithm: options.name || "calibratedV2",
    };
  });
  const dts = [];
  for (let i = 1; i < frames.length; i += 1) {
    const dt = (frames[i].tickMs - frames[i - 1].tickMs) / 1000;
    if (dt > 0) dts.push(dt);
  }
  const stats = summarizeFrames(frames, gpsRows, profile, median(dts.length ? dts : [0.1]), {
    fusion: "calibratedV2",
    validLeanFraction: 1,
  });
  stats.axisName = axisResult.name;
  stats.axisCorrelation = Number(axisResult.score.toFixed(3));
  stats.accelAxisName = accelAxisResult.name;
  stats.accelAxisCorrelation = Number(accelAxisResult.score.toFixed(3));
  stats.accelAxisBaselineG = Number(accelAxisResult.baseline.toFixed(4));
  stats.gyroScale = Number(gyroRepair.scale.toFixed(6));
  stats.smoothingSamples = smoothingSamples;
  stats.leanOffsetDeg = Number(leanOffsetDeg.toFixed(3));
  stats.profileStaticLeanOffsetDeg = Number(staticLeanOffsetDeg.toFixed(3));
  stats.accelBlendMode = correctionOptions.accelBlendMode;
  stats.accelCorrectionStrong = Number((Number.isFinite(correctionOptions.accelCorrectionStrong) ? correctionOptions.accelCorrectionStrong : 0.045).toFixed(4));
  stats.accelCorrectionWeak = Number((Number.isFinite(correctionOptions.accelCorrectionWeak) ? correctionOptions.accelCorrectionWeak : 0.010).toFixed(4));
  stats.repairs = gyroRepair.repair ? [gyroRepair.repair] : [];
  return {
    frames,
    stats,
    algorithm: options.name || "calibratedV2",
    config,
  };
}

function fusedProcessor(session, config, fusionType, options = {}) {
  const joinedData = joinImuToGps(session);
  if (joinedData.error) {
    return { frames: [], stats: { error: joinedData.error }, algorithm: options.name || "unknown", config };
  }
  const calibrated = preprocessCalibrated(joinedData.joined, joinedData.profile);
  const dtSec = computeUniformDtSec(calibrated);
  const rows = resampleJoined(calibrated, dtSec);
  const fusionConfig = { ...config, dtSec };
  rows.forEach((row) => {
    row.accBike0 = row.accBike[0];
    row.accBike1 = row.accBike[1];
    row.accBike2 = row.accBike[2];
  });
  addChannelSplits(rows, fusionConfig);
  const fusedSeries = fusionType === "mahony" ? mahonyFusion(rows, fusionConfig) : complementaryFusion(rows, fusionConfig);
  const frames = enrichFusedFrames(rows, fusedSeries, fusionConfig, options.name || fusionType);
  return {
    frames,
    stats: summarizeFrames(frames, joinedData.gps, joinedData.profile, dtSec, {
      fusion: fusionType,
      validLeanFraction: frames.filter((f) => f.confidence >= 0.5).length / Math.max(1, frames.length),
    }),
    algorithm: options.name || fusionType,
    config: fusionConfig,
  };
}

export const processors = {
  rawAccelLeanV1: {
    id: "rawAccelLeanV1",
    label: "Raw Accel Lean",
    visible: false,
    description: "Raw calibrated accelerometer lean: rotate IMU into the bike frame and compute atan2(lateral, up). No smoothing, filters, masking, gain, or up-floor.",
    process(session, config) {
      return rawAccelLeanProcessor(session, config, { name: "rawAccelLeanV1" });
    },
  },
  accelOnlyV1: {
    id: "accelOnlyV1",
    label: "Accel Only",
    visible: false,
    description: "Lean from the calibrated accelerometer only. Uses the global smoothing controls exactly as configured, with no extra forced smoothing.",
    process(session, config) {
      return crudeCalibratedProcessor(session, config, { name: "accelOnlyV1" });
    },
  },
  accelOnlySmoothedV1: {
    id: "accelOnlySmoothedV1",
    label: "Accel Only Smoothed",
    visible: false,
    description: "Lean from the calibrated accelerometer only, with stronger smoothing than the global setting and the existing confidence masking. No gyro fusion.",
    process(session, config) {
      const smoothConfig = {
        ...config,
        smoothingMs: Math.max(config.smoothingMs || 250, 400),
      };
      return crudeCalibratedProcessor(session, smoothConfig, { name: "accelOnlySmoothedV1" });
    },
  },
  crudeCalibratedV1: {
    id: "crudeCalibratedV1",
    label: "Crude Calibrated Lean",
    visible: false,
    description: "Very crude lean from accelerometer geometry only: rotate IMU into the bike frame using calibration, then compute lean as atan2(lateral, up). No fusion.",
    process(session, config) {
      return crudeCalibratedProcessor(session, config, { name: "crudeCalibratedV1" });
    },
  },
  calibratedV1: {
    id: "calibratedV1",
    label: "Projection Baseline",
    visible: false,
    description: "Calibrated bike-frame projection with heuristics only. Useful as a baseline, not the target estimator.",
    process(session, config) {
      return calibratedProjectionProcessor(session, config, { name: "calibratedV1" });
    },
  },
  calibratedV2Raw: {
    id: "calibratedV2Raw",
    label: "Calibrated V2 Raw",
    description: "Same calibratedV2 estimator without post-fit display gains or GPS lag. Kept as a raw reference for tuning.",
    params: [
      { key: "gyroScale", label: "Gyro Scale", type: "number", default: 0.0625, step: 0.001 },
      { key: "smoothingSamples", label: "Smoothing Samples", type: "number", default: 5, step: 1 },
      { key: "accelBlendMode", label: "Accel Blend Mode", type: "text", default: "hard" },
      { key: "accelCorrectionStrong", label: "Accel Strong Gain", type: "number", default: 0.045, step: 0.005 },
      { key: "accelCorrectionWeak", label: "Accel Weak Gain", type: "number", default: 0.010, step: 0.001 },
      { key: "calibratedLeanGain", label: "Lean Gain", type: "number", default: 1.0, step: 0.05 },
      { key: "leanOffsetDeg", label: "Lean Offset Deg", type: "number", default: 0.0, step: 0.1 },
      { key: "longitudinalGain", label: "Longitudinal Gain", type: "number", default: 1.0, step: 0.05 },
      { key: "autoGpsLag", label: "Auto GPS Lag (0/1)", type: "number", default: 0, step: 1 },
      { key: "gpsLagMs", label: "GPS Lag Ms", type: "number", default: 0, step: 25 },
      { key: "autoLagMinMs", label: "Auto Lag Min Ms", type: "number", default: -800, step: 25 },
      { key: "autoLagMaxMs", label: "Auto Lag Max Ms", type: "number", default: 2200, step: 25 },
      { key: "autoLagStepMs", label: "Auto Lag Step Ms", type: "number", default: 25, step: 25 },
    ],
    process(session, config) {
      return calibratedV2Processor(session, config, { name: "calibratedV2Raw" });
    },
  },
  calibratedV2: {
    id: "calibratedV2",
    label: "Calibrated V2 Tuned",
    description: "Best current tuning candidate. Gyro attitude lean + GPS-assisted axis selection + tuned display gains from sess_008 simulation.",
    params: [
      { key: "gyroScale", label: "Gyro Scale", type: "number", default: 0.07143, step: 0.001 },
      { key: "smoothingSamples", label: "Smoothing Samples", type: "number", default: 5, step: 1 },
      { key: "accelBlendMode", label: "Accel Blend Mode", type: "text", default: "hard" },
      { key: "accelCorrectionStrong", label: "Accel Strong Gain", type: "number", default: 0.045, step: 0.005 },
      { key: "accelCorrectionWeak", label: "Accel Weak Gain", type: "number", default: 0.010, step: 0.001 },
      { key: "calibratedLeanGain", label: "Lean Gain", type: "number", default: 1.1, step: 0.05 },
      { key: "leanOffsetDeg", label: "Lean Offset Deg", type: "number", default: 0.0, step: 0.1 },
      { key: "longitudinalGain", label: "Longitudinal Gain", type: "number", default: 0.65, step: 0.05 },
      { key: "autoGpsLag", label: "Auto GPS Lag (0/1)", type: "number", default: 0, step: 1 },
      { key: "gpsLagMs", label: "GPS Lag Ms", type: "number", default: 250, step: 25 },
      { key: "autoLagMinMs", label: "Auto Lag Min Ms", type: "number", default: -800, step: 25 },
      { key: "autoLagMaxMs", label: "Auto Lag Max Ms", type: "number", default: 2200, step: 25 },
      { key: "autoLagStepMs", label: "Auto Lag Step Ms", type: "number", default: 25, step: 25 },
    ],
    process(session, config) {
      return calibratedV2Processor(session, config, { name: "calibratedV2" });
    },
  },
  complementaryV1: {
    id: "complementaryV1",
    label: "Complementary Fusion V1",
    visible: false,
    description: "Uniform resample plus complementary roll/pitch fusion using gyro as the fast path and accel as a low-frequency gravity correction.",
    process(session, config) {
      return fusedProcessor(session, config, "complementary", { name: "complementaryV1" });
    },
  },
  mahonyV1: {
    id: "mahonyV1",
    label: "Mahony Fusion V1",
    visible: false,
    description: "Uniform resample plus 6-axis Mahony fusion in the calibrated bike frame with confidence-aware accel correction.",
    process(session, config) {
      return fusedProcessor(session, config, "mahony", { name: "mahonyV1" });
    },
  },
};

function gpsOriginFromRows(gpsRows) {
  if (!gpsRows.length) return null;
  const originLat = gpsRows[0].lat;
  const originLon = gpsRows[0].lon;
  return {
    originLat,
    originLon,
    latScale: 111320,
    lonScale: 111320 * Math.cos((originLat * Math.PI) / 180),
  };
}

function metersToLatLon(x, y, origin) {
  return {
    lat: origin.originLat - (y / origin.latScale),
    lon: origin.originLon + (x / origin.lonScale),
  };
}

function estimateHermiteTangents(points) {
  return points.map((point, index) => {
    if (index === 0) {
      const next = points[1];
      const dt = Math.max(1, next.tickMs - point.tickMs);
      return { dx: (next.x - point.x) / dt, dy: (next.y - point.y) / dt };
    }
    if (index === points.length - 1) {
      const prev = points[index - 1];
      const dt = Math.max(1, point.tickMs - prev.tickMs);
      return { dx: (point.x - prev.x) / dt, dy: (point.y - prev.y) / dt };
    }
    const prev = points[index - 1];
    const next = points[index + 1];
    const dt = Math.max(1, next.tickMs - prev.tickMs);
    return { dx: (next.x - prev.x) / dt, dy: (next.y - prev.y) / dt };
  });
}

function positiveTickStep(rows, fallback = 120) {
  const dts = [];
  for (let i = 1; i < rows.length; i += 1) {
    const dt = rows[i].tickMs - rows[i - 1].tickMs;
    if (dt > 0) dts.push(dt);
  }
  return Math.max(1, Math.round(median(dts.length ? dts : [fallback])));
}

function findSegmentIndex(rows, tickMs) {
  if (tickMs <= rows[0].tickMs) return 0;
  for (let index = 0; index < rows.length - 1; index += 1) {
    if (tickMs <= rows[index + 1].tickMs) return index;
  }
  return rows.length - 2;
}

function interpolateScalar(rows, tickMs, key) {
  if (tickMs <= rows[0].tickMs) return rows[0][key];
  if (tickMs >= rows[rows.length - 1].tickMs) return rows[rows.length - 1][key];
  const index = findSegmentIndex(rows, tickMs);
  const a = rows[index];
  const b = rows[index + 1];
  const alpha = clamp((tickMs - a.tickMs) / Math.max(1e-9, b.tickMs - a.tickMs), 0, 1);
  return a[key] + ((b[key] - a[key]) * alpha);
}

function hermiteBasis(u) {
  return {
    h00: (2 * u * u * u) - (3 * u * u) + 1,
    h10: (u * u * u) - (2 * u * u) + u,
    h01: (-2 * u * u * u) + (3 * u * u),
    h11: (u * u * u) - (u * u),
  };
}

function hermiteInterpolateGps(gpsRows, targetTicks = []) {
  if (gpsRows.length < 2) {
    return {
      rows: gpsRows.map((row) => ({ ...row })),
      stats: {
        originalGpsPoints: gpsRows.length,
        enrichedGpsPoints: gpsRows.length,
        baseStepMs: 0,
        enrichedStepMs: 0,
      },
    };
  }

  const origin = gpsOriginFromRows(gpsRows);
  const points = latLonToMeters(gpsRows);
  const tangents = estimateHermiteTangents(points);
  const ticks = targetTicks.length ? targetTicks : gpsRows.map((row) => row.tickMs);
  const stepMs = positiveTickStep(ticks.map((tickMs) => ({ tickMs })), positiveTickStep(gpsRows, 120));
  const baseStepMs = positiveTickStep(gpsRows, 120);
  const rows = ticks.map((tickMs) => {
    const segmentIndex = findSegmentIndex(points, tickMs);
    const a = points[segmentIndex];
    const b = points[Math.min(segmentIndex + 1, points.length - 1)];
    const tangentA = tangents[segmentIndex];
    const tangentB = tangents[Math.min(segmentIndex + 1, tangents.length - 1)];
    const dt = Math.max(1, b.tickMs - a.tickMs);
    const u = clamp((tickMs - a.tickMs) / dt, 0, 1);
    const { h00, h10, h01, h11 } = hermiteBasis(u);
    const x = (h00 * a.x) + (h10 * dt * tangentA.dx) + (h01 * b.x) + (h11 * dt * tangentB.dx);
    const y = (h00 * a.y) + (h10 * dt * tangentA.dy) + (h01 * b.y) + (h11 * dt * tangentB.dy);
    const { lat, lon } = metersToLatLon(x, y, origin);
    return {
      tickMs,
      lat,
      lon,
      speedKmh: interpolateScalar(gpsRows, tickMs, "speedKmh"),
      sats: Math.round(interpolateScalar(gpsRows, tickMs, "sats")),
    };
  });

  return {
    rows,
    stats: {
      originalGpsPoints: gpsRows.length,
      enrichedGpsPoints: rows.length,
      baseStepMs,
      enrichedStepMs: stepMs,
    },
  };
}

function rowTypeOrder(rowType) {
  if (rowType === "M") return 0;
  if (rowType === "G") return 1;
  if (rowType === "IG") return 2;
  if (rowType === "I") return 3;
  return 3;
}

function gpsAnchorRows(rows) {
  return rows.filter((row) => row.row_type === "G");
}

function imuOnlyRows(rows) {
  return rows.filter((row) => row.row_type === "I");
}

function selectPromotionTicks(rows, factor = 3) {
  const anchors = gpsAnchorRows(rows)
    .map((row) => ({
      tickMs: parseInt(row.tick_ms, 10),
      lat: parseNumber(row.lat),
      lon: parseNumber(row.lon),
      speedKmh: parseNumber(row.speed) ?? 0,
      sats: parseNumber(row.sats) ?? 0,
    }))
    .filter((row) => Number.isFinite(row.tickMs) && row.lat != null && row.lon != null);
  if (anchors.length < 2) {
    return {
      ticks: [],
      requestedFactor: factor,
      appliedFactor: 1,
      originalGpsPoints: anchors.length,
      promotedRows: 0,
      totalGpsPoints: anchors.length,
      maxFactor: 1,
    };
  }

  const imuRows = imuOnlyRows(rows)
    .map((row) => parseInt(row.tick_ms, 10))
    .filter((tickMs) => Number.isFinite(tickMs));
  const imuTickSet = new Set(imuRows);
  const availablePromotions = [];
  for (let index = 0; index < anchors.length - 1; index += 1) {
    const start = anchors[index].tickMs;
    const end = anchors[index + 1].tickMs;
    availablePromotions.push(imuRows.filter((tickMs) => tickMs > start && tickMs < end));
  }

  const originalGpsPoints = anchors.length;
  const totalAvailablePromotions = availablePromotions.reduce((sum, ticks) => sum + ticks.length, 0);
  const maxFactor = Math.max(1, Math.floor((originalGpsPoints + totalAvailablePromotions) / originalGpsPoints));
  const appliedFactor = clamp(Math.max(1, Math.round(Number(factor) || 1)), 1, maxFactor);
  const extraPerInterval = Math.max(0, appliedFactor - 1);
  const selectedTicks = [];

  for (let index = 0; index < anchors.length - 1; index += 1) {
    const start = anchors[index].tickMs;
    const end = anchors[index + 1].tickMs;
    const candidates = availablePromotions[index];
    if (!candidates.length || extraPerInterval === 0) continue;
    const picks = [];
    for (let sampleIndex = 1; sampleIndex <= extraPerInterval; sampleIndex += 1) {
      const targetTickMs = start + (((end - start) * sampleIndex) / appliedFactor);
      let bestTickMs = null;
      let bestDistance = Infinity;
      for (const candidateTickMs of candidates) {
        if (picks.includes(candidateTickMs)) continue;
        const distance = Math.abs(candidateTickMs - targetTickMs);
        if (distance < bestDistance) {
          bestDistance = distance;
          bestTickMs = candidateTickMs;
        }
      }
      if (bestTickMs != null) picks.push(bestTickMs);
    }
    picks.sort((a, b) => a - b);
    selectedTicks.push(...picks.filter((tickMs) => imuTickSet.has(tickMs)));
  }

  return {
    ticks: selectedTicks,
    requestedFactor: factor,
    appliedFactor,
    originalGpsPoints,
    promotedRows: selectedTicks.length,
    totalGpsPoints: originalGpsPoints + selectedTicks.length,
    maxFactor,
  };
}

export function enrichSessionWithHermite(session, options = {}) {
  const requestedFactor = Math.max(1, Math.round(Number(options.factor) || 3));
  const anchors = buildGpsRows(session.rows.filter((row) => row.row_type === "G"));
  if (anchors.length < 2) {
    return {
      session,
      stats: {
        error: "Need at least two original G rows for Hermite enrichment.",
        requestedFactor,
        appliedFactor: 1,
        originalGpsPoints: anchors.length,
        promotedRows: 0,
        totalGpsPoints: anchors.length,
        maxFactor: 1,
      },
    };
  }

  const target = selectPromotionTicks(session.rows, requestedFactor);
  const enriched = hermiteInterpolateGps(anchors, target.ticks);
  const enrichedByTick = new Map(enriched.rows.map((row) => [Math.round(row.tickMs), row]));
  const mergedRows = session.rows.map((row) => {
      if (row.row_type !== "I") return { ...row };
      const tickMs = parseInt(row.tick_ms, 10);
      const enrichedRow = enrichedByTick.get(tickMs);
      if (!enrichedRow) {
        return {
          ...row,
          row_type: "I",
          lat: "",
          lon: "",
          alt: "",
          speed: "",
          sats: "",
          gps_epoch: "",
        };
      }
      return {
        ...row,
        row_type: "IG",
        lat: enrichedRow.lat.toFixed(7),
        lon: enrichedRow.lon.toFixed(7),
        alt: row.alt || "",
        speed: enrichedRow.speedKmh.toFixed(1),
        sats: String(Math.max(0, enrichedRow.sats || 0)),
        gps_epoch: "",
      };
    })
    .sort((a, b) => {
      const tickDelta = (parseInt(a.tick_ms, 10) || 0) - (parseInt(b.tick_ms, 10) || 0);
      if (tickDelta !== 0) return tickDelta;
      return rowTypeOrder(a.row_type) - rowTypeOrder(b.row_type);
    });

  return {
    session: {
      header: session.header?.length ? session.header.slice() : Object.keys(mergedRows[0] || {}),
      rows: mergedRows,
    },
    stats: {
      requestedFactor: target.requestedFactor,
      appliedFactor: target.appliedFactor,
      originalGpsPoints: target.originalGpsPoints,
      promotedRows: target.promotedRows,
      totalGpsPoints: target.totalGpsPoints,
      maxFactor: target.maxFactor,
      enrichedStepMs: enriched.stats.enrichedStepMs,
      baseStepMs: enriched.stats.baseStepMs,
      mode: "ig_rows",
    },
  };
}

function escapeCsvValue(value) {
  const text = value == null ? "" : String(value);
  if (!/[",\n\r]/.test(text)) return text;
  return `"${text.replace(/"/g, "\"\"")}"`;
}

export function serializeSessionCsv(session) {
  const header = session.header?.length ? session.header : Object.keys(session.rows[0] || {});
  const lines = [header.join(",")];
  for (const row of session.rows) {
    lines.push(header.map((key) => escapeCsvValue(row[key] ?? "")).join(","));
  }
  return `${lines.join("\n")}\n`;
}

export function parseSessionCsv(text) {
  const lines = text.replace(/\r/g, "").split("\n").filter((line) => line.length);
  if (lines.length < 2) return { header: [], rows: [] };
  const header = splitCsvLine(lines[0]);
  const rows = lines.slice(1).map((line) => {
    const values = splitCsvLine(line);
    const row = {};
    header.forEach((key, index) => {
      row[key] = values[index] ?? "";
    });
    return row;
  });
  return { header, rows };
}
