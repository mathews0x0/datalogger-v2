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
    .filter((row) => row.row_type === "G")
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
    .filter((row) => row.row_type === "I")
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
  const gpsSpeedMs = gpsWithXY.map((row) => row.speedKmh / 3.6);
  const gpsAccel = movingAverage(derivative(gpsSpeedMs, gpsDt).map((v) => v / 9.80665), 5);

  for (let i = 0; i < gpsWithXY.length; i += 1) {
    gpsWithXY[i].headingDeg = headingsWrapped[i];
    gpsWithXY[i].yawRateDegS = gpsYawRate[i] || 0;
    gpsWithXY[i].gpsAccelG = gpsAccel[i] || 0;
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
    if (row.row_type !== "I" && row.row_type !== "G") continue;
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
    if (row.row_type === "G" && item.lat != null && item.lon != null) {
      gpsIndices.push(index);
      gpsRows.push({ tickMs, lat: item.lat, lon: item.lon, speedKmh: item.speedKmh ?? 0, sats: item.sats });
    }
  }
  return { dataRows, gpsRows, gpsIndices };
}

function repairGyroScaleForCalibratedV2(dataRows, profile) {
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
  const scale = shouldRepair ? 1 / 16 : 1;
  const gyroBias = (profile.gyro_bias || [0, 0, 0]).slice(0, 3);
  while (gyroBias.length < 3) gyroBias.push(0);
  return {
    scale,
    gyroBias: gyroBias.map((value) => value * scale),
    repair: shouldRepair ? {
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

function runCalibratedV2Filter(dataRows, profile, rollAxis, gyroRepair) {
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
    const stableForce = forceError < 0.16 && aUp > 0.65 && Math.abs(aLong) < 0.35;
    const stableRotation = Math.abs(rollRate) < 90 && gyroActivity < 450;
    let correctionGain = 0;
    if (stableForce && stableRotation) correctionGain = 0.045;
    else if (forceError < 0.24 && aUp > 0.45 && Math.abs(rollRate) < 140) correctionGain = 0.010;
    if (correctionGain) roll += correctionGain * angleDeltaDeg(accelLean, roll);
    roll = clamp(roll, -60, 60);
    leans.push(roll);
  }
  return movingAverage(leans, 5);
}

function selectCalibratedV2Axis(dataRows, profile, gpsIndices, gpsLeans, gyroRepair) {
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
    leans: runCalibratedV2Filter(dataRows, profile, rotation[0], gyroRepair),
    score: -1,
  };
  for (const candidate of candidates) {
    const leans = runCalibratedV2Filter(dataRows, profile, candidate.axis, gyroRepair);
    const sampled = gpsIndices.map((index) => leans[index]).slice(0, gpsLeans.length);
    const score = pearsonCorrelation(sampled, gpsLeans.slice(0, sampled.length));
    if (sampled.length >= 10 && score > best.score) {
      best = { ...candidate, leans, score };
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
  const gyroRepair = repairGyroScaleForCalibratedV2(dataRows, profile);
  const axisResult = selectCalibratedV2Axis(dataRows, profile, gpsIndices, gpsLeans, gyroRepair);

  for (let i = 1; i < gpsWithXY.length; i += 1) {
    const dx = gpsWithXY[i].x - gpsWithXY[i - 1].x;
    const dy = gpsWithXY[i].y - gpsWithXY[i - 1].y;
    gpsWithXY[i].headingDeg = Math.abs(dx) + Math.abs(dy) > 1e-6 ? (Math.atan2(dx, -dy) * 180) / Math.PI : gpsWithXY[i - 1].headingDeg || 0;
  }
  if (gpsWithXY.length > 1) gpsWithXY[0].headingDeg = gpsWithXY[1].headingDeg;

  const frames = gpsRows.map((gpsRow, index) => {
    const sourceIndex = gpsIndices[index];
    const source = dataRows[sourceIndex];
    const leanDeg = axisResult.leans[sourceIndex] ?? 0;
    const gpsLeanDeg = gpsLeans[index] ?? 0;
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
      accelG: 0,
      brakeG: 0,
      confidence: 1,
      accelTrust: 1,
      turnEvidence: clamp(Math.abs(gpsLeanDeg) / 30, 0, 1),
      upG: 0,
      latG: 0,
      latHighG: 0,
      upHighG: 0,
      forwardRawG: 0,
      accMag: norm(source.acc),
      gpsYawRateDegS: 0,
      gpsAccelG: 0,
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
    description: "Raw calibrated accelerometer lean: rotate IMU into the bike frame and compute atan2(lateral, up). No smoothing, filters, masking, gain, or up-floor.",
    process(session, config) {
      return rawAccelLeanProcessor(session, config, { name: "rawAccelLeanV1" });
    },
  },
  accelOnlyV1: {
    id: "accelOnlyV1",
    label: "Accel Only",
    description: "Lean from the calibrated accelerometer only. Uses the global smoothing controls exactly as configured, with no extra forced smoothing.",
    process(session, config) {
      return crudeCalibratedProcessor(session, config, { name: "accelOnlyV1" });
    },
  },
  accelOnlySmoothedV1: {
    id: "accelOnlySmoothedV1",
    label: "Accel Only Smoothed",
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
    description: "Very crude lean from accelerometer geometry only: rotate IMU into the bike frame using calibration, then compute lean as atan2(lateral, up). No fusion.",
    process(session, config) {
      return crudeCalibratedProcessor(session, config, { name: "crudeCalibratedV1" });
    },
  },
  calibratedV1: {
    id: "calibratedV1",
    label: "Projection Baseline",
    description: "Calibrated bike-frame projection with heuristics only. Useful as a baseline, not the target estimator.",
    process(session, config) {
      return calibratedProjectionProcessor(session, config, { name: "calibratedV1" });
    },
  },
  calibratedV2: {
    id: "calibratedV2",
    label: "Calibrated V2",
    description: "GPS-fix report view using gyro attitude integration, automatic BMI323 gyro scale repair, session axis selection, and gated accelerometer drift correction.",
    process(session, config) {
      return calibratedV2Processor(session, config, { name: "calibratedV2" });
    },
  },
  complementaryV1: {
    id: "complementaryV1",
    label: "Complementary Fusion V1",
    description: "Uniform resample plus complementary roll/pitch fusion using gyro as the fast path and accel as a low-frequency gravity correction.",
    process(session, config) {
      return fusedProcessor(session, config, "complementary", { name: "complementaryV1" });
    },
  },
  mahonyV1: {
    id: "mahonyV1",
    label: "Mahony Fusion V1",
    description: "Uniform resample plus 6-axis Mahony fusion in the calibrated bike frame with confidence-aware accel correction.",
    process(session, config) {
      return fusedProcessor(session, config, "mahony", { name: "mahonyV1" });
    },
  },
};

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
