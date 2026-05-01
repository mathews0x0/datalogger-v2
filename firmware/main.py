import machine
import time
import os
import gc
import _thread
import math
import network
import ujson
import socket
import ssl


# Drivers
import ubinascii
from drivers.gps import GPS
from drivers.bmi323 import BMI323
from lib.session_manager import SessionManager
from lib.led_manager import LEDManager
from lib.track_engine import TrackEngine
from lib.memory_profile import get_memory_profile, format_memory_profile
from lib import boot_diagnostics as diag
from lib.display_config import display_config_exists, iter_display_presets, load_display_config, save_display_config

TRACK_RESPONSE_LIMIT = 16 * 1024
TRACK_RESPONSE_READ_SIZE = 1024
TRACK_PULL_TIMEOUT = 12
RAM_SAMPLE_INTERVAL_MS = 1000
_ram_sample_ms = 0
_ram_used_mb = 0.0
_ram_total_mb = 0.0
BATTERY_SAMPLE_INTERVAL_MS = 250
BUTTON_SAMPLE_INTERVAL_MS = 60
SOFT_SHUTDOWN_HOLD_MS = 3000
SOFT_SHUTDOWN_SCREEN_MS = 2000
BUTTON_SENSE_PRESS_DELTA_V = 0.12
BUTTON_SENSE_BASELINE_HYST_V = 0.06
BATTERY_DIVIDER_SCALE = 2.10

# --- MASTER PINOUT CONFIG (ESP32-S3 RS-CORE V2) ---
PIN_POWER_HOLD = 41    # Soft-power self-hold output
PIN_BUTTON_POWER_SENSE = 8  # Divided power button sense
PIN_LED_FEEDBACK = 4    # Feedback NeoPixel (16-LED matrix)
PIN_BUTTON_SYNC = None  # Temporarily disabled; IO5 used for TFT_CS
PIN_LED_ONBOARD = None  # Temporarily disabled; IO6 used for TFT_DC
PIN_GPS_RX = 18
PIN_GPS_TX = 17
PIN_I2C_SDA = 21
PIN_I2C_SCL = 39
PIN_SD_SCK = 12
PIN_SD_MOSI = 11
PIN_SD_MISO = 13
PIN_SD_CS = 10
PIN_SD_CD = 40          # Card Detect (active LOW when card inserted)
PIN_BATTERY_ADC = 14     # Temporary battery sense remap
PIN_DEBUG_LED = 2       # Blue Debug LED
PIN_TFT_CS = 5
PIN_TFT_DC = 6
PIN_TFT_RST = 42
PIN_TOUCH_CS = 7
PIN_TOUCH_IRQ = 38
PIN_TFT_SCK = 15
PIN_TFT_MOSI = 16
PIN_TFT_MISO = 9

# Sensitivity constants now handled by IMU driver class

_battery_last_ms = 0
_battery_raw_v = 0.0
_battery_filtered_v = 0.0
_battery_slow_v = 0.0
_battery_pct_cached = 0
_battery_charging = False
_battery_prev_raw_v = 0.0
_battery_charge_score = 0
_battery_debug_last_ms = 0
_button_sense_adc = None
_button_sense_last_ms = 0
_button_sense_v = 0.0
_button_sense_baseline_v = 0.0
_button_sense_pressed = False
_button_press_start_ms = None


def calculate_battery_percentage(voltage):
    if voltage >= 4.2:
        return 100
    if voltage <= 3.3:
        return 0

    curve = (
        (4.2, 100),
        (4.05, 90),
        (3.95, 80),
        (3.85, 60),
        (3.75, 40),
        (3.7, 20),
        (3.6, 10),
        (3.4, 5),
        (3.3, 0),
    )

    for i in range(len(curve) - 1):
        high_v, high_p = curve[i]
        low_v, low_p = curve[i + 1]
        if voltage <= high_v and voltage >= low_v:
            range_v = high_v - low_v
            range_p = high_p - low_p
            v_offset = voltage - low_v
            return int(round(low_p + (v_offset / range_v) * range_p))
    return 0


def read_vbatt(vbat_adc):
    try:
        return (vbat_adc.read_uv() / 1000000.0) * BATTERY_DIVIDER_SCALE
    except Exception:
        return 0.0


def _read_vbatt_average(vbat_adc, samples=6):
    if vbat_adc is None:
        return 0.0
    total_uv = 0
    count = 0
    for _ in range(samples):
        try:
            total_uv += int(vbat_adc.read_uv())
            count += 1
        except Exception:
            pass
    if count <= 0:
        return 0.0
    return ((total_uv / count) / 1000000.0) * BATTERY_DIVIDER_SCALE


def get_battery_state(vbat_adc, force=False):
    global _battery_last_ms, _battery_raw_v, _battery_filtered_v, _battery_slow_v
    global _battery_pct_cached, _battery_charging, _battery_prev_raw_v, _battery_charge_score
    global _battery_debug_last_ms
    now = time.ticks_ms()
    if force or time.ticks_diff(now, _battery_last_ms) >= BATTERY_SAMPLE_INTERVAL_MS:
        raw_v = _read_vbatt_average(vbat_adc)
        prev_raw_v = _battery_prev_raw_v
        rise_v = 0.0
        fast_delta = 0.0
        _battery_raw_v = raw_v
        if raw_v > 0:
            if _battery_filtered_v <= 0:
                _battery_filtered_v = raw_v
                _battery_slow_v = raw_v
                _battery_prev_raw_v = raw_v
                _battery_charge_score = 0
            else:
                alpha_fast = 0.22 if raw_v >= _battery_filtered_v else 0.10
                _battery_filtered_v = (_battery_filtered_v * (1.0 - alpha_fast)) + (raw_v * alpha_fast)
                _battery_slow_v = (_battery_slow_v * 0.97) + (raw_v * 0.03)
                rise_v = raw_v - prev_raw_v if prev_raw_v > 0 else 0.0
                fast_delta = _battery_filtered_v - _battery_slow_v
                evidence = 0
                if raw_v >= 3.70 and fast_delta >= 0.025:
                    evidence += 1
                if raw_v >= 3.70 and rise_v >= 0.012:
                    evidence += 1
                if raw_v >= 3.85 and fast_delta >= 0.045:
                    evidence += 1
                if evidence > 0:
                    _battery_charge_score = min(6, _battery_charge_score + evidence)
                else:
                    # Keep USB-charge detection sticky enough to survive noisy ADC
                    # samples once charging has already been inferred.
                    if _battery_charging and raw_v >= 3.85 and fast_delta >= -0.004:
                        decay = 0
                    else:
                        decay = 2 if (raw_v <= 3.62 or fast_delta <= 0.008) else 1
                    _battery_charge_score = max(0, _battery_charge_score - decay)
                _battery_charging = (_battery_charge_score >= 2) or (
                    _battery_charging and _battery_charge_score >= 1 and raw_v >= 3.80
                )
                _battery_prev_raw_v = raw_v
            pct = calculate_battery_percentage(_battery_filtered_v)
            if _battery_pct_cached == 0:
                _battery_pct_cached = pct
            elif abs(pct - _battery_pct_cached) >= 2:
                step = 2 if pct > _battery_pct_cached else -2
                next_pct = _battery_pct_cached + step
                if (step > 0 and next_pct > pct) or (step < 0 and next_pct < pct):
                    next_pct = pct
                _battery_pct_cached = max(0, min(100, next_pct))
        else:
            _battery_filtered_v = 0.0
            _battery_slow_v = 0.0
            _battery_pct_cached = 0
            _battery_charging = False
            _battery_prev_raw_v = 0.0
            _battery_charge_score = 0
        if force or time.ticks_diff(now, _battery_debug_last_ms) >= 1000:
            print(
                "[BATDBG] raw=%.3f filt=%.3f slow=%.3f rise=%.3f score=%d charging=%s pct=%d"
                % (
                    raw_v,
                    _battery_filtered_v,
                    _battery_slow_v,
                    rise_v,
                    _battery_charge_score,
                    "yes" if _battery_charging else "no",
                    _battery_pct_cached,
                )
            )
            _battery_debug_last_ms = now
        _battery_last_ms = now
    return _battery_filtered_v, _battery_pct_cached, _battery_charging


def get_battery_voltage(vbat_adc, force=False):
    return get_battery_state(vbat_adc, force=force)[0]


def get_battery_pct(vbat_adc, force=False):
    return get_battery_state(vbat_adc, force=force)[1]


def is_battery_charging(vbat_adc, force=False):
    return get_battery_state(vbat_adc, force=force)[2]


def init_shutdown_button_sense():
    global _button_sense_adc
    try:
        _button_sense_adc = machine.ADC(machine.Pin(PIN_BUTTON_POWER_SENSE))
        _button_sense_adc.atten(machine.ADC.ATTN_11DB)
        return _button_sense_adc
    except Exception as e:
        print("[PWR] Button sense init failed:", e)
        _button_sense_adc = None
        return None


def read_shutdown_button_sense(force=False):
    global _button_sense_last_ms, _button_sense_v
    if _button_sense_adc is None:
        return 0.0
    now = time.ticks_ms()
    if force or time.ticks_diff(now, _button_sense_last_ms) >= BUTTON_SAMPLE_INTERVAL_MS:
        total_uv = 0
        count = 0
        for _ in range(4):
            try:
                total_uv += int(_button_sense_adc.read_uv())
                count += 1
            except Exception:
                pass
        if count > 0:
            _button_sense_v = (total_uv / count) / 1000000.0
        _button_sense_last_ms = now
    return _button_sense_v


def poll_shutdown_button(now_ms=None):
    global _button_sense_baseline_v, _button_sense_pressed, _button_press_start_ms
    now_ms = time.ticks_ms() if now_ms is None else now_ms
    sense_v = read_shutdown_button_sense()
    if sense_v <= 0:
        return False
    if _button_sense_baseline_v <= 0:
        _button_sense_baseline_v = sense_v
        return False

    if not _button_sense_pressed and sense_v <= (_button_sense_baseline_v + BUTTON_SENSE_BASELINE_HYST_V):
        _button_sense_baseline_v = (_button_sense_baseline_v * 0.97) + (sense_v * 0.03)

    pressed_now = sense_v >= (_button_sense_baseline_v + BUTTON_SENSE_PRESS_DELTA_V)
    if pressed_now:
        if not _button_sense_pressed:
            _button_sense_pressed = True
            _button_press_start_ms = now_ms
        elif _button_press_start_ms is not None and time.ticks_diff(now_ms, _button_press_start_ms) >= SOFT_SHUTDOWN_HOLD_MS:
            return True
    else:
        _button_sense_pressed = False
        _button_press_start_ms = None
    return False


def show_shutdown_notice(tft=None):
    if tft:
        try:
            tft.invalidate()
            tft.show_message("SHUTDOWN", "Powering off", "")
        except Exception:
            pass


def release_power_hold(power_hold=None):
    try:
        if power_hold is None:
            power_hold = machine.Pin(PIN_POWER_HOLD, machine.Pin.OUT, value=1)
        power_hold.value(0)
    except Exception as e:
        print("[PWR] Failed to release hold:", e)


def perform_soft_shutdown(sm=None, tft=None, power_hold=None, reason="soft_shutdown"):
    print("[PWR] Soft shutdown:", reason)
    diag.record_phase("SOFT_SHUTDOWN", reason)
    try:
        os.sync()
    except Exception:
        pass
    if sm and getattr(sm, "sd_mounted", False):
        try:
            os.sync()
        except Exception:
            pass
        try:
            os.umount("/sd")
            print("[PWR] /sd unmounted")
        except Exception as e:
            print("[PWR] /sd unmount skipped:", e)
    show_shutdown_notice(tft=tft)
    time.sleep_ms(SOFT_SHUTDOWN_SCREEN_MS)
    diag.mark_expected_reset(reason)
    release_power_hold(power_hold=power_hold)
    time.sleep_ms(250)
    machine.reset()


def update_display_context(tft, sm, vbat_adc, ram_used_mb=None, ram_total_mb=None, force_battery=False):
    _, battery_pct, charging = get_battery_state(vbat_adc, force=force_battery)
    if tft:
        tft.set_context(
            battery_pct=battery_pct,
            charging=charging,
            sd_ok=getattr(sm, "sd_mounted", None),
            sd_pct=get_storage_used_percent(sm),
            ram_used_mb=ram_used_mb,
            ram_total_mb=ram_total_mb,
        )
    return battery_pct, charging


def sd_card_inserted():
    try:
        return machine.Pin(PIN_SD_CD, machine.Pin.IN, machine.Pin.PULL_UP).value() == 0
    except Exception as e:
        print("[SD] Card detect read failed:", e)
        return None


def get_storage_used_percent(sm):
    try:
        info = sm.get_active_storage_info()
        if not info or info.get('total_kb', 0) <= 0:
            return None
        return int(round((info['used_kb'] * 100.0) / info['total_kb']))
    except Exception:
        return None


def get_ram_usage_mb(force=False):
    global _ram_sample_ms, _ram_used_mb, _ram_total_mb
    now = time.ticks_ms()
    if force or time.ticks_diff(now, _ram_sample_ms) >= RAM_SAMPLE_INTERVAL_MS:
        try:
            free_b = int(gc.mem_free())
            alloc_b = int(gc.mem_alloc())
            total_b = free_b + alloc_b
            _ram_used_mb = alloc_b / (1024.0 * 1024.0)
            _ram_total_mb = total_b / (1024.0 * 1024.0)
        except Exception:
            pass
        _ram_sample_ms = now
    return _ram_used_mb, _ram_total_mb


def sanitize_active_track_payload(track_info):
    if not isinstance(track_info, dict):
        return None

    sanitized = dict(track_info)
    sectors = sanitized.get("sectors")
    if not isinstance(sectors, list):
        sanitized["sectors"] = []
    else:
        sanitized["sectors"] = sectors[:16]

    tbl = sanitized.get("tbl")
    if not isinstance(tbl, dict):
        sanitized["tbl"] = {}
    else:
        tbl_sectors = tbl.get("sectors")
        if isinstance(tbl_sectors, list):
            sanitized["tbl"] = {"sectors": tbl_sectors[:16]}
        else:
            sanitized["tbl"] = {}

    layout = sanitized.get("device_layout")
    if isinstance(layout, dict):
        polyline = layout.get("polyline")
        sector_markers = layout.get("sector_markers")
        if not isinstance(polyline, list) or len(polyline) > 160:
            sanitized.pop("device_layout", None)
        else:
            layout_copy = dict(layout)
            layout_copy["polyline"] = polyline[:160]
            layout_copy["sector_markers"] = sector_markers[:16] if isinstance(sector_markers, list) else []
            start_marker = layout_copy.get("start_marker")
            if start_marker is not None and not isinstance(start_marker, dict):
                layout_copy["start_marker"] = None
            sanitized["device_layout"] = layout_copy
    else:
        sanitized.pop("device_layout", None)

    return sanitized


def prepare_shared_spi_bus():
    # Keep TFT control lines idle. TFT now uses a dedicated SPI bus.
    for pin_no, value in ((PIN_TFT_CS, 1), (PIN_TOUCH_CS, 1), (PIN_TFT_DC, 0), (PIN_TFT_RST, 1)):
        if pin_no is None:
            continue
        try:
            machine.Pin(pin_no, machine.Pin.OUT, value=value)
        except Exception as e:
            print("[SPI] Pin prep failed on", pin_no, e)
    if PIN_TOUCH_IRQ is not None:
        try:
            machine.Pin(PIN_TOUCH_IRQ, machine.Pin.IN, machine.Pin.PULL_UP)
        except Exception as e:
            print("[SPI] Touch IRQ prep failed on", PIN_TOUCH_IRQ, e)


def assert_power_hold():
    try:
        hold = machine.Pin(PIN_POWER_HOLD, machine.Pin.OUT, value=1)
        hold.value(1)
        return hold
    except Exception as e:
        print("[PWR] Failed to assert hold:", e)
        return None


def save_device_config(data):
    try:
        try:
            os.mkdir("/data")
        except OSError:
            pass
        try:
            os.mkdir("/data/metadata")
        except OSError:
            pass
        with open("/data/metadata/device.json", "w") as f:
            ujson.dump(data, f)
        return True
    except Exception as e:
        print("[Config] Save failed:", e)
        return False


def get_active_track_name():
    try:
        with open("/data/metadata/track.json", "r") as f:
            data = ujson.load(f)
        return data.get("track_name") or data.get("name") or ""
    except Exception:
        return ""


def load_active_track_data():
    try:
        with open("/data/metadata/track.json", "r") as f:
            data = ujson.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _csv_escape(value):
    if value is None:
        return ""
    text = str(value)
    if '"' in text:
        text = text.replace('"', '""')
    if "," in text or "\n" in text or "\r" in text or '"' in text:
        return '"' + text + '"'
    return text


def _format_csv_row(values):
    return ",".join(_csv_escape(value) for value in values) + "\n"


def _sample_imu_window(imu, duration_ms=1800, step_ms=10, wdt=None):
    samples = []
    if not imu:
        return samples
    buf = [0, 0, 0, 0, 0, 0]
    end_ms = time.ticks_add(time.ticks_ms(), int(duration_ms))
    while time.ticks_diff(end_ms, time.ticks_ms()) > 0:
        if wdt:
            try:
                wdt.feed()
            except Exception:
                pass
        try:
            imu.get_values_into(buf)
            samples.append({
                "acc": [
                    buf[0] / imu.ACC_SENSITIVITY,
                    buf[1] / imu.ACC_SENSITIVITY,
                    buf[2] / imu.ACC_SENSITIVITY,
                ],
                "gyro": [
                    buf[3] / imu.GYR_SENSITIVITY,
                    buf[4] / imu.GYR_SENSITIVITY,
                    buf[5] / imu.GYR_SENSITIVITY,
                ],
            })
        except Exception:
            pass
        time.sleep_ms(step_ms)
    return samples


def _wait_imu_prompt_capture(tft, wdt, title, body, footer="Tap capture"):
    if not tft:
        return True
    tft.invalidate()
    tft.show_imu_calibration_prompt(title, body, footer)
    while True:
        if wdt:
            wdt.feed()
        action = tft.settings_touch()
        if action == "capture":
            return True
        if action == "back":
            return False
        time.sleep_ms(30)


def _run_imu_profile_calibration(tft, imu, label, wdt):
    from lib.imu_calibration import build_capture_summary, solve_profile, upsert_profile

    if not imu:
        if tft:
            tft.show_message("IMU", "Sensor missing", "Cannot calibrate")
        return None

    steps = (
        ("STATIC", "Hold bike still\nEngine OFF", "Captures gyro bias and gravity"),
        ("ENGINE", "Hold bike still\nEngine ON", "Captures vibration baseline"),
        ("LEAN LEFT", "Lean bike left\nthen tap capture", "Keep device mounted"),
        ("LEAN RIGHT", "Lean bike right\nthen tap capture", "Keep device mounted"),
        ("PUSH", "Push bike forward\nsmoothly for 2 sec", "Tap then perform motion"),
    )
    captures = []
    for title, body, footer in steps:
        if not _wait_imu_prompt_capture(tft, wdt, title, body, footer):
            if tft:
                tft.show_message("IMU", "Cancelled", "Calibration not saved")
            return None
        if tft:
            tft.show_message(title, "Capturing...", "Hold steady")
        duration_ms = 2200 if title == "PUSH" else 1800
        samples = _sample_imu_window(imu, duration_ms=duration_ms, wdt=wdt)
        if len(samples) < 40:
            if tft:
                tft.show_message("IMU", "Capture failed", "Try again")
            return None
        captures.append(build_capture_summary(samples))
        time.sleep_ms(250)

    profile = solve_profile(label, captures[0], captures[1], captures[2], captures[3], captures[4])
    if float(profile.get("quality_score") or 0.0) < 0.45:
        if tft:
            tft.show_message("IMU", "Low quality", "Re-run calibration")
        return None
    if not upsert_profile(profile):
        if tft:
            tft.show_message("IMU", "Save failed", "Check storage")
        return None
    if tft:
        tft.show_message("IMU", "Saved %s" % str(label).upper(), "Quality %.2f" % float(profile.get("quality_score") or 0.0))
    return profile


def _rollout_validation_status(profile, gps_samples, imu_samples):
    status = "ORIENTATION OK"
    source_mode = "imu_trusted"
    reason = ""
    confidence = 0.9
    if not profile:
        return {"status_text": "LOW CONFIDENCE", "source_mode": "gps_assisted", "reason": "no_profile", "confidence": 0.2}

    rotation = profile.get("rotation_matrix") or [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    gyro_bias = profile.get("gyro_bias") or [0.0, 0.0, 0.0]
    vibration = (((profile.get("vibration") or {}).get("delta_acc_rms")) or [0.0, 0.0, 0.0])
    forward = rotation[0]
    up = rotation[2]

    speed_gain = 0.0
    prev_speed = None
    for item in gps_samples:
        speed = item.get("speed")
        if speed is None:
            continue
        if prev_speed is not None and speed > prev_speed:
            speed_gain += (speed - prev_speed)
        prev_speed = speed

    longitudinal_sum = 0.0
    up_error_sum = 0.0
    yaw_energy = 0.0
    count = 0
    for sample in imu_samples:
        acc = sample.get("acc") or [0.0, 0.0, 0.0]
        gyro = sample.get("gyro") or [0.0, 0.0, 0.0]
        longitudinal_sum += (acc[0] * forward[0]) + (acc[1] * forward[1]) + (acc[2] * forward[2])
        up_mag = abs((acc[0] * up[0]) + (acc[1] * up[1]) + (acc[2] * up[2]))
        up_error_sum += abs(1.0 - up_mag)
        yaw_energy += abs(gyro[0] - gyro_bias[0]) + abs(gyro[1] - gyro_bias[1]) + abs(gyro[2] - gyro_bias[2])
        count += 1
    mean_longitudinal = longitudinal_sum / count if count else 0.0
    mean_up_error = up_error_sum / count if count else 1.0
    mean_yaw = yaw_energy / count if count else 0.0
    vib_strength = math.sqrt((vibration[0] * vibration[0]) + (vibration[1] * vibration[1]) + (vibration[2] * vibration[2]))

    if speed_gain > 4.0 and mean_longitudinal < -0.03:
        status = "LOW CONFIDENCE"
        source_mode = "gps_assisted"
        reason = "forward_sign_conflict"
        confidence = 0.25
    elif mean_up_error > 0.28 or vib_strength > 0.65:
        status = "CHECK MOUNT"
        source_mode = "imu_warn"
        reason = "tilt_or_vibration_mismatch"
        confidence = 0.55
    elif mean_yaw > 20.0 and speed_gain < 1.0:
        status = "CHECK MOUNT"
        source_mode = "imu_warn"
        reason = "gyro_mismatch"
        confidence = 0.6

    return {
        "status_text": status,
        "source_mode": source_mode,
        "reason": reason,
        "confidence": confidence,
        "mean_longitudinal": round(mean_longitudinal, 4),
        "mean_up_error": round(mean_up_error, 4),
        "mean_yaw": round(mean_yaw, 4),
        "speed_gain": round(speed_gain, 2),
    }


def _profile_heading_deg(profile):
    if not profile:
        return 0.0
    rotation = profile.get("rotation_matrix") or [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    forward = rotation[0]
    forward_flat = [float(forward[0]), float(forward[1]), 0.0]
    mag = math.sqrt((forward_flat[0] * forward_flat[0]) + (forward_flat[1] * forward_flat[1]))
    if mag <= 1e-6:
        return 0.0
    display_up = [0.0, 1.0, 0.0]
    display_right = [1.0, 0.0, 0.0]
    up_component = ((forward_flat[0] * display_up[0]) + (forward_flat[1] * display_up[1])) / mag
    right_component = ((forward_flat[0] * display_right[0]) + (forward_flat[1] * display_right[1])) / mag
    return math.degrees(math.atan2(right_component, up_component if abs(up_component) > 1e-6 else 1e-6))


def _profile_mount_angles(profile):
    if not profile:
        return 0.0, 0.0
    rotation = profile.get("rotation_matrix") or [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    sensor_z_bike = [rotation[0][2], rotation[1][2], rotation[2][2]]
    pitch_deg = math.degrees(math.atan2(sensor_z_bike[0], max(0.1, sensor_z_bike[2])))
    roll_deg = math.degrees(math.atan2(-sensor_z_bike[1], max(0.1, sensor_z_bike[2])))
    return pitch_deg, roll_deg

def setup():
    print("\n--- ESP32-S3 RACESENSE V2 DATALOGGER ---")
    diag.record_phase("BOOT_SETUP_START")
    mem_info = get_memory_profile()
    print("[Memory] Boot:", format_memory_profile(mem_info))
    diag.update_runtime_stats(
        psram_present=mem_info.get("psram_present"),
        gc_total_kb=mem_info.get("gc_total", 0) // 1024,
        gc_free_kb=mem_info.get("gc_free", 0) // 1024,
        idf_total_kb=mem_info.get("idf_total", 0) // 1024,
        idf_free_kb=mem_info.get("idf_free", 0) // 1024,
        idf_largest_kb=mem_info.get("idf_largest", 0) // 1024,
    )
    # 1. LED Manager (Dual NeoPixel: IO4 feedback + IO6 onboard)
    diag.record_phase("BOOT_LED_INIT")
    led = LEDManager(pin=PIN_LED_FEEDBACK, count=16, onboard_neo_pin=PIN_LED_ONBOARD, onboard_led_pin=PIN_DEBUG_LED)
    led.start_animation_thread()
    led.play_booting()
    
    # 2. Power Stability Delay
    print("Stabilizing power...")
    time.sleep_ms(1000)

    # Ensure shared SPI peripherals are idle before SD init.
    prepare_shared_spi_bus()
    
    # 3. Battery Monitor
    diag.record_phase("BOOT_BATTERY_INIT")
    vbat_adc = None
    if PIN_BATTERY_ADC is not None:
        vbat_adc = machine.ADC(machine.Pin(PIN_BATTERY_ADC))
        vbat_adc.atten(machine.ADC.ATTN_11DB)
        get_battery_state(vbat_adc, force=True)
    init_shutdown_button_sense()

    # 4. Mount SD Card (Native ESP32 SD driver — proven working in full_system_test.py)
    sd_mounted = False
    diag.record_phase("BOOT_SD_INIT")
    card_present = sd_card_inserted()
    if card_present is True:
        print("[SD] Card detect: inserted")
    elif card_present is False:
        print("[SD] Card detect: not inserted")
    else:
        print("[SD] Card detect: unavailable, attempting mount anyway")
    try:
        if card_present is False:
            raise OSError("card detect open")
        sd = machine.SDCard(slot=2, width=1, sck=machine.Pin(PIN_SD_SCK), mosi=machine.Pin(PIN_SD_MOSI), miso=machine.Pin(PIN_SD_MISO), cs=machine.Pin(PIN_SD_CS))
        os.mount(sd, '/sd')
        print("Storage: SD CARD MOUNTED SUCCESS")
        sd_mounted = True
    except Exception as e:
        print(f"Storage: SD Mount Failed ({e}). Using Onboard Flash.")

    # 5. Session Manager
    sm = SessionManager(sd_mounted=sd_mounted)
    tft = None
    if sd_mounted:
        s_info = sm.get_active_storage_info()
        if s_info:
            print(f"Storage: SD Total: {s_info['total_kb']/1024:.2f} MB, Used: {s_info['used_kb']/1024:.2f} MB ({s_info['used_kb']*100/s_info['total_kb']:.1f}%)")
        
        # --- AUTO-COPY MECHANISM ---
        # If files exist on flash and SD is mounted, move them and reboot
        if sm.has_flash_sessions():
            print("\n[System] Found session files on internal flash. Moving to SD card...")
            diag.record_phase("BOOT_AUTO_COPY")
            led.play_auto_copy()
            # Feed WDT during potentially long copy
            wdt = machine.WDT(timeout=20000) # Ensure WDT is active
            
            if sm.move_flash_to_sd():
                print("[System] Auto-copy complete! Rebooting...")
                time.sleep(1)
                diag.mark_expected_reset("auto_copy_complete")
                machine.reset()
            else:
                print("[System] Auto-copy failed. Continuing normal boot.")
                led.play_booting()
    
    # 6. I2C Sensors (IMU)
    imu = None
    diag.record_phase("BOOT_IMU_INIT")
    try:
        i2c = machine.I2C(0, sda=machine.Pin(PIN_I2C_SDA), scl=machine.Pin(PIN_I2C_SCL), freq=100000)
        imu = BMI323(i2c, address=0x69)
        print("IMU: BMI323 Initialized Success")
        
        # Diagnostic: Print 5 consecutive IMU readings
        print("IMU: Diagnostic — 5 consecutive readings:")
        for i in range(5):
            d = imu.get_values()
            ax, ay, az = d["acc"]["x"]/imu.ACC_SENSITIVITY, d["acc"]["y"]/imu.ACC_SENSITIVITY, d["acc"]["z"]/imu.ACC_SENSITIVITY
            gx, gy, gz = d["gyro"]["x"]/imu.GYR_SENSITIVITY, d["gyro"]["y"]/imu.GYR_SENSITIVITY, d["gyro"]["z"]/imu.GYR_SENSITIVITY
            print(f"  [{i+1}] ACC: {ax:>6.3f}, {ay:>6.3f}, {az:>6.3f} | GYR: {gx:>7.2f}, {gy:>7.2f}, {gz:>7.2f}")
            time.sleep_ms(10)
    except Exception as e:
        print(f"IMU: Failed to initialize ({e})")

    # 7. GPS — Must start at 9600 (module default on power-up), then shift to 115200
    diag.record_phase("BOOT_GPS_INIT")
    gps_uart = machine.UART(1, baudrate=9600, tx=machine.Pin(PIN_GPS_TX), rx=machine.Pin(PIN_GPS_RX), timeout=0, rxbuf=2048)
    gps = GPS(gps_uart)
    print("GPS: Neo-M8N — Shifting from 9600 → 115200 baud...")
    gps.set_baudrate(115200)
    time.sleep_ms(100)
    gps_uart.init(baudrate=115200, tx=machine.Pin(PIN_GPS_TX), rx=machine.Pin(PIN_GPS_RX), timeout=0, rxbuf=2048)
    gps.set_rate(10)
    print("GPS: Neo-M8N Ready at 115200 baud / 10Hz (2KB Buffer)")

    # Diagnostic: Measure frequency over 5 NMEA sentences
    print("GPS: Diagnostic — Measuring frequency (5 sentences)...")
    sentences_received = 0
    start_ms = time.ticks_ms()
    timeout_ms = 2000 # 2 seconds total timeout
    
    while sentences_received < 5 and time.ticks_diff(time.ticks_ms(), start_ms) < timeout_ms:
        if gps_uart.any():
            line = gps_uart.readline()
            if line and line.startswith(b'$'):
                sentences_received += 1
                try:
                    print("[GPS] Sentence %d: %s" % (sentences_received, line[:72].decode(errors="ignore").strip()))
                except Exception:
                    print("[GPS] Sentence %d: <decode failed>" % sentences_received)
    
    end_ms = time.ticks_ms()
    duration = time.ticks_diff(end_ms, start_ms)
    if sentences_received >= 5:
        freq = 5 / (duration / 1000.0)
        print(f"GPS: Received 5 sentences in {duration}ms ({freq:.2f}Hz)")
    else:
        print(f"GPS: Diagnostic timeout. Received only {sentences_received} sentences in {duration}ms.")
    # 8. Track Engine
    diag.record_phase("BOOT_TRACK_INIT")
    track_eng = TrackEngine()
    track_eng.load_track()

    # 8.5 TFT boot UI init. This board shares SPI with SD and handles boot/home/sync UX.
    try:
        print("[TFT] Init start")
        try:
            print("[TFT] /drivers:", os.listdir('/drivers'))
        except Exception as e:
            print("[TFT] Could not list /drivers:", e)
        try:
            import sys
            print("[TFT] sys.path:", sys.path)
        except Exception as e:
            print("[TFT] Could not read sys.path:", e)
        print("[TFT] Importing TFTBootUI from lib.tft_ui")
        from lib.tft_ui import TFTBootUI
        print("[TFT] TFTBootUI import OK")
        saved_display_cfg = load_display_config()
        tft = TFTBootUI(
            pin_sck=PIN_TFT_SCK,
            pin_mosi=PIN_TFT_MOSI,
            pin_miso=PIN_TFT_MISO,
            pin_tft_cs=PIN_TFT_CS,
            pin_tft_dc=PIN_TFT_DC,
            pin_tft_rst=PIN_TFT_RST,
            pin_touch_cs=PIN_TOUCH_CS,
            pin_touch_irq=PIN_TOUCH_IRQ,
            display_config=saved_display_cfg,
        )
        print("[TFT] TFTBootUI instance created")
        if not display_config_exists():
            print("[TFT] No display config found. Starting first-boot panel selection.")
            selected_preset = tft.select_display_preset(iter_display_presets())
            if selected_preset and save_display_config(selected_preset):
                print("[TFT] Display config saved:", selected_preset)
                diag.mark_expected_reset("display_config_saved")
                machine.reset()
            print("[TFT] Display selection failed or timed out.")
        else:
            tft._boot_logo_visible = True
            if not tft.has_touch_calibration():
                print("[TFT] No touch calibration found. Starting touch + display calibration.")
                if tft.calibrate_touch_and_display():
                    diag.mark_expected_reset("touch_display_calibration_saved")
                    machine.reset()
        print("[TFT] Boot UI initialized")
    except Exception as e:
        tft = None
        print("[TFT] Init failed:", e)
        try:
            import sys
            sys.print_exception(e)
        except Exception:
            pass

    # 9. Watchdog Timer (Increase to 20s for network operations)
    diag.record_phase("BOOT_WDT_INIT")
    wdt = machine.WDT(timeout=20000)

    imu_ok = imu is not None
    gps_ok = sentences_received >= 5

    return led, gps, imu, sm, track_eng, tft, i2c, vbat_adc, wdt, sd_mounted, imu_ok, gps_ok, gps_uart, sentences_received

def run_home_window(led, imu, sm, tft, i2c, vbat_adc, wdt, sd_mounted, imu_ok, gps_ok, gps_uart, sentences_received, sync_btn, power_hold):
    from lib.wifi_manager import load_device_config
    from lib.imu_calibration import list_profiles, get_selected_profile, set_selected_profile
    config = load_device_config()
    auto_log_enabled = bool(config.get("auto_log_enabled", True))
    active_track_data = load_active_track_data()
    home_track_name = (active_track_data or {}).get("track_name") or (active_track_data or {}).get("name") or ""
    selected_profile = get_selected_profile()
    selected_mount_label = str((selected_profile or {}).get("label") or "")
    if not config.get('ssid'):
        print("\n[System] No WiFi configured — staying on Home. Use SYNC or Settings > WIFI to configure.")
        auto_log_enabled = False
    
    print("\n[System] Home — 10s Auto Log Window")
    diag.record_phase("BOOT_HOME_WINDOW")
    if not gps_ok:
        print("[System] GPS ERROR: No NMEA data detected. Holding on Home.")
    
    sync_requested = False
    force_pairing_requested = False
    settings_open = False
    settings_page = "settings"
    settings_scroll_index = 0
    start = time.ticks_ms()
    paused = False
    paused_started_ms = 0
    paused_accum_ms = 0
    settings_rendered = False
    home_rendered_once = False
    
    while True:
        now_ms = time.ticks_ms()
        elapsed = time.ticks_diff(now_ms, start) - paused_accum_ms
        if paused:
            elapsed = time.ticks_diff(paused_started_ms, start) - paused_accum_ms
        wdt.feed()
        if poll_shutdown_button(now_ms):
            perform_soft_shutdown(sm=sm, tft=tft, power_hold=power_hold, reason="button_long_press_home")

        if tft and not home_rendered_once:
            ram_used_mb, ram_total_mb = get_ram_usage_mb()
            update_display_context(tft, sm, vbat_adc, ram_used_mb=ram_used_mb, ram_total_mb=ram_total_mb)
            tft.invalidate()
            tft.show_home(
                sd_mounted,
                imu_ok,
                gps_ok,
                gps_sentences=sentences_received,
                countdown_ms=10000,
                paused=paused,
                auto_log_enabled=auto_log_enabled,
                track_name=home_track_name,
                mount_label=selected_mount_label,
            )
            home_rendered_once = True
            print("[TFT] Home shown")

        if settings_open and tft:
            if not settings_rendered:
                pending_summary = sm.get_pending_summary() if sm else {"count": 0}
                if settings_page == "wifi_options":
                    tft.show_wifi_options(config.get('ssid', ''))
                elif settings_page == "track_layout":
                    active_track_data = load_active_track_data()
                    tft.show_track_view(active_track_data, page=0)
                elif settings_page == "track_detail":
                    active_track_data = load_active_track_data()
                    tft.show_track_view(active_track_data, page=1)
                elif settings_page == "archive_confirm":
                    tft.show_archive_confirm(pending_count=pending_summary.get("count", 0))
                elif settings_page == "imu_profiles":
                    tft.show_imu_profiles(list_profiles(), selected_id=(selected_profile or {}).get("id", ""))
                else:
                    tft.show_settings(
                        config.get('ssid', ''),
                        auto_log_enabled=auto_log_enabled,
                        pending_count=pending_summary.get("count", 0),
                        scroll_index=settings_scroll_index,
                    )
                settings_rendered = True
                time.sleep_ms(30)
                continue
            settings_action = tft.settings_touch()
            if settings_action == "settings_up":
                settings_scroll_index = max(0, settings_scroll_index - 1)
                settings_rendered = False
                tft.invalidate()
                continue
            if settings_action == "settings_down":
                settings_scroll_index = min(3, settings_scroll_index + 1)
                settings_rendered = False
                tft.invalidate()
                continue
            if settings_action == "wifi":
                settings_page = "wifi_options"
                settings_rendered = False
                tft.invalidate()
                continue
            if settings_action == "track":
                settings_page = "track_layout"
                settings_rendered = False
                tft.invalidate()
                continue
            if settings_action == "imu_profiles":
                settings_page = "imu_profiles"
                settings_rendered = False
                tft.invalidate()
                continue
            if settings_action == "track_next":
                settings_page = "track_detail"
                settings_rendered = False
                tft.invalidate()
                continue
            if settings_action == "track_prev":
                settings_page = "track_layout"
                settings_rendered = False
                tft.invalidate()
                continue
            if settings_action == "wifi_change":
                if paused:
                    paused_accum_ms += time.ticks_diff(now_ms, paused_started_ms)
                    paused = False
                sync_requested = True
                force_pairing_requested = True
                print("[System] WiFi change requested from settings.")
                break
            if settings_action == "calibrate":
                print("[System] Touch + display calibration requested from settings.")
                tft.calibrate_touch_and_display()
                tft.invalidate()
                settings_page = "settings"
                settings_rendered = False
                continue
            if settings_action and settings_action.startswith("imu_profile_"):
                label = settings_action.replace("imu_profile_", "")
                existing = None
                for profile in list_profiles():
                    if str(profile.get("label") or "").lower() == label:
                        existing = profile
                        break
                should_calibrate = existing is None or str((selected_profile or {}).get("id") or "") == str((existing or {}).get("id") or "")
                if should_calibrate:
                    print("[System] IMU calibration requested for profile:", label)
                    new_profile = _run_imu_profile_calibration(tft, imu, label, wdt)
                    if new_profile:
                        selected_profile = new_profile
                        selected_mount_label = str(new_profile.get("label") or "")
                else:
                    if set_selected_profile(existing.get("id")):
                        selected_profile = existing
                        selected_mount_label = str(existing.get("label") or "")
                        tft.show_message("IMU", "Selected %s" % label.upper(), "Ready to log")
                settings_page = "imu_profiles"
                settings_rendered = False
                tft.invalidate()
                continue
            if settings_action == "archive":
                settings_page = "archive_confirm"
                settings_rendered = False
                tft.invalidate()
                continue
            if settings_action == "archive_yes":
                tft.show_message("ARCHIVE", "Moving files", "No cloud sync")
                archive_result = sm.archive_all_pending_entries(wdt=wdt) if sm else {"total": 0, "archived": 0, "failed": 0}
                print(
                    "[System] Archive all complete: %d/%d archived, %d failed."
                    % (
                        archive_result.get("archived", 0),
                        archive_result.get("total", 0),
                        archive_result.get("failed", 0),
                    )
                )
                if archive_result.get("failed", 0):
                    tft.show_message(
                        "ARCHIVE",
                        "%d archived\n%d failed" % (archive_result.get("archived", 0), archive_result.get("failed", 0)),
                        "Check storage",
                    )
                else:
                    tft.show_message(
                        "ARCHIVE",
                        "%d file%s archived"
                        % (
                            archive_result.get("archived", 0),
                            "" if archive_result.get("archived", 0) == 1 else "s",
                        ),
                        "Moved to uploaded/",
                    )
                time.sleep_ms(1000)
                settings_page = "settings"
                settings_rendered = False
                tft.invalidate()
                continue
            if settings_action == "toggle_auto_log":
                auto_log_enabled = not auto_log_enabled
                config["auto_log_enabled"] = auto_log_enabled
                save_device_config(config)
                settings_page = "settings"
                settings_rendered = False
                tft.invalidate()
                print("[System] Auto log %s from settings." % ("enabled" if auto_log_enabled else "disabled"))
                continue
            if settings_action == "back":
                if settings_page == "settings":
                    if paused:
                        paused_accum_ms += time.ticks_diff(now_ms, paused_started_ms)
                        paused = False
                    settings_open = False
                    settings_page = "settings"
                    settings_rendered = False
                    if tft:
                        tft.invalidate()
                else:
                    settings_page = "settings"
                    settings_rendered = False
                    if tft:
                        tft.invalidate()
            if settings_open:
                pending_summary = sm.get_pending_summary() if sm else {"count": 0}
                if settings_page == "wifi_options":
                    tft.show_wifi_options(config.get('ssid', ''))
                elif settings_page == "track_layout":
                    active_track_data = load_active_track_data()
                    tft.show_track_view(active_track_data, page=0)
                elif settings_page == "track_detail":
                    active_track_data = load_active_track_data()
                    tft.show_track_view(active_track_data, page=1)
                elif settings_page == "archive_confirm":
                    tft.show_archive_confirm(pending_count=pending_summary.get("count", 0))
                elif settings_page == "imu_profiles":
                    tft.show_imu_profiles(list_profiles(), selected_id=(selected_profile or {}).get("id", ""))
                else:
                    tft.show_settings(
                        config.get('ssid', ''),
                        auto_log_enabled=auto_log_enabled,
                        pending_count=pending_summary.get("count", 0),
                        scroll_index=settings_scroll_index,
                    )
                settings_rendered = True
            time.sleep_ms(30)
            continue
        
        # Dynamic GPS check if not already OK
        if not gps_ok:
            while gps_uart.any():
                line = gps_uart.readline()
                if line and line.startswith(b'$'):
                    sentences_received += 1
                    if sentences_received >= 5:
                        gps_ok = True
                        print("[System] GPS RECOVERED: NMEA detected. Window will now proceed.")
                        break
        
        # Update LED with current health status
        led.play_decision(sd_mounted, imu_ok, gps_ok)

        # Check input before repainting the TFT; full-screen SPI transfers can
        # otherwise make touch feel delayed.
        if sync_btn and sync_btn.value() == 0:
            sync_requested = True
            print("[System] SYNC button pressed! Entering Sync Mode.")
            break
        if tft:
            touch_action = tft.home_touch()
            if touch_action == "yes":
                if paused:
                    paused_accum_ms += time.ticks_diff(now_ms, paused_started_ms)
                    paused = False
                sync_requested = True
                print("[System] SYNC requested from touchscreen.")
                break
            if touch_action == "settings":
                if not paused:
                    paused = True
                    paused_started_ms = now_ms
                settings_open = True
                settings_page = "settings"
                settings_scroll_index = 0
                settings_rendered = False
                tft.invalidate()
                print("[System] Settings opened from touchscreen.")
                continue
            if touch_action == "no" and gps_ok:
                if paused:
                    paused_accum_ms += time.ticks_diff(now_ms, paused_started_ms)
                    paused = False
                print("[System] LOGGING selected from touchscreen.")
                break

        ram_used_mb, ram_total_mb = get_ram_usage_mb()
        update_display_context(tft, sm, vbat_adc, ram_used_mb=ram_used_mb, ram_total_mb=ram_total_mb)
        if tft:
            remaining_ms = 10000 - elapsed
            tft.show_home(
                sd_mounted,
                imu_ok,
                gps_ok,
                gps_sentences=sentences_received,
                countdown_ms=remaining_ms,
                paused=paused,
                auto_log_enabled=auto_log_enabled,
                track_name=home_track_name,
                mount_label=selected_mount_label,
            )
        
        # Exit condition: 10s passed AND GPS is okay
        # If GPS is NOT okay, we stay here forever (or until SYNC is pressed)
        if gps_ok and auto_log_enabled and elapsed > 10000:
            break
            
        # Optional: Re-check GPS if it was previously failed? 
        # For now, we stick to the initial check as per requirement ("stays on Home if problem with GPS")
        
        time.sleep_ms(30)

    wdt.feed()
    
    if sync_requested:
        return "sync", force_pairing_requested
    return "log", False


def main():
    power_hold = assert_power_hold()
    prev_state, current_state = diag.boot_start()
    print("[Diag] Reset cause:", current_state.get("reset_cause"))
    if prev_state:
        print("[Diag] Previous phase:", prev_state.get("last_phase", "n/a"))
        if prev_state.get("exception"):
            print("[Diag] Previous exception:", prev_state.get("exception"))

    led, gps, imu, sm, track_eng, tft, i2c, vbat_adc, wdt, sd_mounted, imu_ok, gps_ok, gps_uart, sentences_received = setup()
    
    sync_btn = None
    if PIN_BUTTON_SYNC is not None:
        sync_btn = machine.Pin(PIN_BUTTON_SYNC, machine.Pin.IN, machine.Pin.PULL_UP)

    while True:
        action, force_pairing_requested = run_home_window(
            led, imu, sm, tft, i2c, vbat_adc, wdt, sd_mounted, imu_ok, gps_ok, gps_uart, sentences_received, sync_btn, power_hold
        )
        if action == "sync":
            print("\n[System] ==> SYNC MODE")
            diag.record_phase("MODE_SYNC")
            prepare_shared_spi_bus()
            result = run_sync_mode(led, sm, tft, sync_btn, wdt, vbat_adc, power_hold, force_pairing=force_pairing_requested)
            if result == "home":
                print("[System] Returning to Home.")
                if tft:
                    tft.invalidate()
                continue
            continue

        print("\n[System] ==> LOGGING MODE")
        diag.record_phase("MODE_LOGGING")
        from lib.wifi_manager import stop_wifi
        stop_wifi()
        prepare_shared_spi_bus()
        logging_loop(led, gps, imu, sm, track_eng, tft, vbat_adc, wdt, power_hold)
        return


# ==================================================================
# SYNC MODE — WiFi upload / Pairing. No logging.
# ==================================================================

def run_sync_mode(led, sm, tft, sync_btn, wdt, vbat_adc, power_hold, force_pairing=False):
    """
    Exclusive sync mode. No telemetry logging occurs.
    
    Flow:
    1. Search for known WiFi (purple fade).
    2. If found: upload pending files (green blink → green fade on success).
    3. Stay in sync mode after completion.
    4. Long press (>3s) on sync button → enter Pairing mode (blue breathing).
    """
    from lib.wifi_manager import load_device_config, stop_wifi, get_unique_ap_name
    
    config = load_device_config()
    wifi_connected = False
    needs_setup = force_pairing or not config.get('ssid')
    if tft:
        tft.invalidate()

    def load_saved_track_name():
        try:
            with open('/data/metadata/track.json', 'r') as f:
                data = ujson.load(f)
            return data.get('track_name') or data.get('name') or ""
        except Exception:
            return ""

    def update_display_runtime():
        ram_used_mb, ram_total_mb = get_ram_usage_mb()
        update_display_context(tft, sm, vbat_adc, ram_used_mb=ram_used_mb, ram_total_mb=ram_total_mb)
    
    if needs_setup:
        # No saved network — auto-enter pairing mode with rainbow animation
        if force_pairing:
            print("[Sync] WiFi configuration requested. Starting Pairing Mode...")
            diag.record_phase("SYNC_PORTAL_START", "settings_wifi")
        else:
            print("[Sync] No WiFi credentials. Starting Pairing Mode automatically...")
            diag.record_phase("SYNC_PORTAL_START", "no_saved_wifi")
        from lib.captive_portal import start_background_portal
        ap_name = get_unique_ap_name()
        gc.collect()
        _thread.stack_size(16384) # 16KB for portal
        _thread.start_new_thread(start_background_portal, (led,))
        diag.mark_boot_completed("pairing_portal_running")
        
        # Stay in rainbow loop — portal runs in background
        while True:
            wdt.feed()
            if poll_shutdown_button():
                perform_soft_shutdown(sm=sm, tft=tft, power_hold=power_hold, reason="button_long_press_pairing")
            led.play_setup_needed()
            if tft:
                tft.show_first_time_setup(ap_name)
            time.sleep_ms(50)
    
    # --- Phase 2 & 3: Dual-Core Sync Architecture ---
    # Core 1: Background Uploader
    # Core 0: Main Heartbeat & Active Track loop
    
    wdt.feed()
    # Shared state for thread coordination
    global network_lock
    network_lock = _thread.allocate_lock()
    state_lock = _thread.allocate_lock()
    sync_state = {
        "uploader_busy": False,
        "uploader_started": False,
        "sync_complete": False,
        "synced_files_count": 0,
        "hb_ok": False,
        "wifi_connected": wifi_connected,
        "wifi_failed": not wifi_connected and bool(config.get('ssid')),
        "wifi_retry_requested": False,
        "pairing_active": False,
        "portal_requested": False,
        "reboot_requested": False,
        "allow_reboot": False,
        "low_power_mode": False,
        "last_track_name": load_saved_track_name(),
        "phase_label": "Boot",
        "last_result": "",
        "pending_bytes": 0,
    }

    def set_state(**kwargs):
        with state_lock:
            sync_state.update(kwargs)

    def get_state(key):
        with state_lock:
            return sync_state.get(key)

    def spawn_uploader():
        if get_state("uploader_started"):
            return False
        vbatt_now = get_vbatt()
        _, critical_power = apply_power_policy(vbatt_now, network.WLAN(network.STA_IF) if wifi_connected else None)
        if critical_power:
            print("[Sync] Battery too low for upload. Deferring uploader start.")
            diag.record_phase("SYNC_LOW_BATTERY_DEFER", "%.2f" % vbatt_now)
            return False
        print("[Sync] Spawning uploader thread.")
        diag.record_phase("SYNC_UPLOADER_START")
        set_state(
            allow_reboot=False,
            reboot_requested=False,
            phase_label="Queueing",
            last_result="",
            sync_complete=False,
            synced_files_count=0,
        )
        gc.collect()
        _thread.stack_size(32768) # 32KB for SSL uploader
        _thread.start_new_thread(uploader_thread_func, (sm, led))
        set_state(uploader_started=True)
        return True

    def attempt_wifi_connect():
        nonlocal wifi_connected
        ssid = config.get('ssid', '')
        if not ssid:
            return False
        print(f"[Sync] Searching for WiFi: {ssid}")
        diag.record_phase("SYNC_WIFI_PREP", ssid)
        set_state(phase_label="WiFi scan")
        led.set_state("SYNC_SEARCHING")
        if tft:
            update_display_runtime()
            tft.invalidate()
            tft.show_sync_searching(ssid, frame=0)

        gc.collect()
        sta = network.WLAN(network.STA_IF)
        try:
            sta.disconnect()
        except:
            pass
        try:
            sta.active(False)
            time.sleep_ms(150)
        except:
            pass
        gc.collect()
        diag.record_phase("SYNC_WIFI_ACTIVE")
        sta.active(True)
        time.sleep_ms(200)
        gc.collect()
        try:
            sta.config(txpower=8.5)
        except:
            pass
        try:
            _vbatt_init = get_battery_voltage(vbat_adc, force=True)
            if _vbatt_init > 0 and _vbatt_init < 3.55:
                led.set_brightness(0.10)
                sta.config(txpower=2.0)
            elif _vbatt_init > 0 and _vbatt_init < 3.70:
                led.set_brightness(0.18)
                sta.config(txpower=5.0)
        except:
            pass
        diag.record_phase("SYNC_WIFI_CONNECT", ssid)
        set_state(phase_label="WiFi connect")
        sta.connect(ssid, config.get('password', ''))

        wifi_connected = False
        for attempt in range(300):
            wdt.feed()
            if poll_shutdown_button():
                perform_soft_shutdown(sm=sm, tft=tft, power_hold=power_hold, reason="button_long_press_wifi_search")
            if tft and attempt % 3 == 0:
                tft.show_sync_searching(ssid, frame=(attempt // 3))
            if tft:
                touch_action = tft.sync_touch()
                if touch_action == "exit":
                    print("[Sync] Exit requested during WiFi search.")
                    try:
                        sta.active(False)
                    except:
                        pass
                    return "exit"
            if sta.isconnected():
                wifi_connected = True
                ip = sta.ifconfig()[0]
                print(f"[Sync] WiFi Connected! IP: {ip}")
                diag.record_phase("SYNC_WIFI_CONNECTED", ip)
                led.play_sync_found()
                set_state(wifi_connected=True, wifi_failed=False, wifi_retry_requested=False, phase_label="Cloud link")
                if tft:
                    tft.show_sync_connected(ssid, ip)
                wdt.feed()
                time.sleep(1)
                wdt.feed()
                return True
            time.sleep_ms(100)

        print("[Sync] WiFi connection failed.")
        diag.record_phase("SYNC_WIFI_FAILED")
        set_state(wifi_connected=False, wifi_failed=True, wifi_retry_requested=False, hb_ok=False, phase_label="WiFi failed", last_result="Connect failed")
        if tft:
            tft.show_sync_wifi_failed(ssid, allow_retry=True)
        try:
            sta.active(False)
        except:
            pass
        gc.collect()
        return False
    
    # Helper function to get battery voltage
    def get_vbatt():
        """Returns battery voltage in volts using calibrated ADC."""
        return get_battery_voltage(vbat_adc)

    def apply_power_policy(vbatt, wifi_sta=None):
        low_power = vbatt > 0 and vbatt < 3.70
        critical_power = vbatt > 0 and vbatt < 3.55
        set_state(low_power_mode=low_power)
        if critical_power:
            led.set_brightness(0.10)
            if wifi_sta:
                try:
                    wifi_sta.config(txpower=2.0)
                except:
                    pass
        elif low_power:
            led.set_brightness(0.18)
            if wifi_sta:
                try:
                    wifi_sta.config(txpower=5.0)
                except:
                    pass
        else:
            led.set_brightness(0.40)
            if wifi_sta:
                try:
                    wifi_sta.config(txpower=8.5)
                except:
                    pass
        return low_power, critical_power

    def perform_heartbeat():
        """Single heartbeat + active track pull using raw sockets for stability."""
        set_state(phase_label="Handshake")
        # Setup URLs
        api_url = config.get('api_url', '')
        try:
            proto, _, host_port, path = api_url.split('/', 3)
            host = host_port.split(':')[0] if ':' in host_port else host_port
            port = int(host_port.split(':')[1]) if ':' in host_port else (443 if proto == 'https:' else 80)
            
            p_base = '/' + path.rstrip('/')
            if p_base.endswith('/upload'): p_base = p_base.replace('/upload', '/device')
            else: p_base = p_base + '/device'
            
            ping_path = p_base + '/ping'
            track_path = p_base + '/active_track'
        except Exception as e:
            print(f"[Sync] URL Parse Error: {e}")
            if tft:
                tft.show_heartbeat("URL error", detail=str(e))
            set_state(last_result="URL error")
            return False

        # Gather Telemetry
        vbatt = get_vbatt()
        try:
            stats = os.statvfs('/sd')
            sd_free = (stats[0] * stats[3]) // (1024 * 1024)
            sd_total = (stats[0] * stats[2]) // (1024 * 1024)
        except: 
            sd_free = 0
            sd_total = 0
        try:
            f_stats = os.statvfs('/')
            flash_free = (f_stats[0] * f_stats[3]) // 1024 # KB
            flash_total = (f_stats[0] * f_stats[2]) // 1024 # KB
        except: 
            flash_free = 0
            flash_total = 0
        
        device_uid = ubinascii.hexlify(machine.unique_id()).decode()
        telemetry = ujson.dumps({
            "device_uid": device_uid,
            "vbatt_sense": vbatt,
            "storage_sd_free": sd_free,
            "storage_sd_total": sd_total,
            "storage_flash_free": flash_free,
            "storage_flash_total": flash_total
        })
        print(f"[Heartbeat] Payload: {telemetry}")

        success = False
        s = None
        ss = None
        
        try:
            gc.collect()
            print(f"[Heartbeat] Pinging {host}:{port}{ping_path}...")
            diag.record_phase("SYNC_SSL_HEARTBEAT", host)
            led.play_heartbeat_send()
            if tft:
                tft.show_heartbeat("Sending", host=host, detail="POST /ping")
            
            # 1. Opening Raw Socket
            ai = socket.getaddrinfo(host, port)[0]
            s = socket.socket(ai[0], ai[1], ai[2])
            s.settimeout(5)
            s.connect(ai[-1])
            
            # 2. SSL Wrap if needed
            if proto == 'https:':
                ss = ssl.wrap_socket(s, server_hostname=host)
            else:
                ss = s
            
            # 3. Send PING
            req = f"POST {ping_path} HTTP/1.1\r\n"
            req += f"Host: {host}\r\n"
            req += f"Authorization: Bearer {config.get('token', '')}\r\n"
            req += "Content-Type: application/json\r\n"
            req += f"Content-Length: {len(telemetry)}\r\n"
            req += "Connection: close\r\n\r\n"
            ss.write(req.encode() + telemetry.encode())
            
            # 4. Read Response Line
            resp_line = ss.readline().decode()
            if "200 OK" in resp_line:
                print("[Heartbeat] Server ACK OK.")
                led.play_heartbeat_ack()
                if tft:
                    tft.show_heartbeat("ACK OK", host=host, detail="Heartbeat accepted")
                set_state(phase_label="Track sync")
                time.sleep(1) # Visual confirmation
                success = True
            else:
                print(f"[Heartbeat] Server Rejected: {resp_line.strip()}")
                if tft:
                    tft.show_heartbeat("Rejected", host=host, detail=resp_line.strip())
                set_state(last_result=resp_line.strip() or "Heartbeat rejected")
            
            # 5. Active Track Pull (Separate connection for safety)
            if success:
                s_tr = None
                ss_tr = None
                try:
                    gc.collect()
                    diag.record_phase("SYNC_SSL_TRACK_PULL", host)
                    s_tr = socket.socket(ai[0], ai[1], ai[2])
                    s_tr.settimeout(TRACK_PULL_TIMEOUT)
                    s_tr.connect(ai[-1])
                    if proto == 'https:':
                        ss_tr = ssl.wrap_socket(s_tr, server_hostname=host)
                    else:
                        ss_tr = s_tr
                    
                    req_tr = f"GET {track_path} HTTP/1.1\r\n"
                    req_tr += f"Host: {host}\r\n"
                    req_tr += f"Authorization: Bearer {config.get('token', '')}\r\n"
                    req_tr += "Connection: close\r\n\r\n"
                    
                    print(f"[Sync] Pulling track: {track_path}")
                    ss_tr.write(req_tr.encode())
                    
                    # Skip headers and read body
                    status_line = ss_tr.readline().decode().strip()
                    headers = {}
                    while True:
                        header_line = ss_tr.readline().decode()
                        if not header_line or header_line == "\r\n":
                            break
                        if ':' in header_line:
                            key, value = header_line.split(':', 1)
                            headers[key.strip().lower()] = value.strip()

                    content_len = int(headers.get("content-length", "0") or "0")
                    body_bytes = bytearray()
                    while content_len > 0:
                        chunk = ss_tr.read(min(TRACK_RESPONSE_READ_SIZE, content_len))
                        if not chunk:
                            break
                        if len(body_bytes) < TRACK_RESPONSE_LIMIT:
                            remaining = TRACK_RESPONSE_LIMIT - len(body_bytes)
                            body_bytes.extend(chunk[:remaining])
                        content_len -= len(chunk)

                    body = body_bytes.decode() if body_bytes else ""
                    print(f"[Sync] Track response: {status_line} body_len={len(body_bytes)}")
                    
                    if "200 OK" in status_line and body:
                        try:
                            t_data = ujson.loads(body)
                            if t_data and "active_track" in t_data:
                                track_info = sanitize_active_track_payload(t_data["active_track"])
                                if track_info:
                                    with open('/data/metadata/track.json', 'w') as f:
                                        ujson.dump(track_info, f)
                                    print(f"[Sync] Active track saved: {track_info.get('track_name', 'Unknown')}")
                                    set_state(
                                        last_track_name=track_info.get('track_name') or track_info.get('name', 'Unknown'),
                                        phase_label="Cloud ready",
                                    )
                                    if tft:
                                        tft.show_track_sync(track_info.get('track_name') or track_info.get('name', 'Unknown'))
                                else:
                                    print("[Sync] Active track is null on server.")
                                    set_state(last_track_name="", last_result="No active track")
                            else:
                                print("[Sync] No 'active_track' key in response.")
                                set_state(last_result="No active track data")
                        except Exception as json_e:
                            print(f"[Sync] JSON Parse Error: {json_e}")
                            set_state(last_result="Track JSON error")
                    else:
                        print(f"[Sync] Invalid response (No 200 OK or body separator)")
                        set_state(last_result=status_line or "Track sync failed")
                except Exception as tr_e:
                    print(f"[Sync] Track Pull Error: {tr_e}")
                    set_state(last_result="Track refresh timeout" if "ETIMEDOUT" in str(tr_e) else (str(tr_e) or "Track pull error"))
                finally:
                    if ss_tr: ss_tr.close()
                    if s_tr: s_tr.close()

        except Exception as e:
            print(f"[Heartbeat] Network Error: {e}")
            if tft:
                tft.show_heartbeat("Network error", host=host if 'host' in locals() else "", detail=str(e))
            set_state(last_result=str(e) or "Network error")
        finally:
            if ss: ss.close()
            if s: s.close()
            gc.collect()
        
        # Update: Only set status LED if uploader is not busy
        if not get_state("uploader_busy"):
            if success:
                led.play_heartbeat_success()
            else:
                led.play_heartbeat_error()
        
        return success

    # Background Uploader Thread
    def uploader_thread_func(sm_ref, led_ref):
        set_state(uploader_busy=True)
        try:
            pending_summary = sm_ref.get_pending_summary()
            pending = pending_summary.get("names", [])
            set_state(
                pending_bytes=pending_summary.get("total_bytes", 0),
                phase_label="Queue ready" if pending else "Idle",
            )
            if tft:
                tft.show_sync_queue(pending, total_bytes=pending_summary.get("total_bytes", 0))

            def upload_status(event, **info):
                if not tft:
                    return
                if event == "queue":
                    set_state(
                        pending_bytes=info.get("global_total", 0),
                        phase_label="Queue ready" if info.get("files") else "Idle",
                    )
                    if tft:
                        tft.show_sync_queue(info.get("files", []), total_bytes=info.get("global_total", 0))
                elif event in ("upload_start", "upload_progress", "upload_done"):
                    phase = "Preparing" if event == "upload_start" else "Uploading"
                    set_state(
                        phase_label=phase,
                        pending_bytes=max(0, info.get("global_total", 0) - info.get("global_current", 0)),
                    )
                    if tft:
                        tft.show_sync_upload(
                            info.get("filename", ""),
                            info.get("file_index", 0),
                            info.get("total_files", 1),
                            info.get("sent_bytes", 0),
                            info.get("total_bytes", 0),
                            info.get("global_current", 0),
                            info.get("global_total", 0),
                            phase=phase,
                            detail=info.get("detail", ""),
                            batch_count=info.get("batch_count", 0),
                            total_batches=info.get("total_batches", 0),
                        )
                    if event == "upload_done":
                        set_state(
                            last_result="Uploaded " + info.get("filename", "").split("/")[-1],
                            phase_label="Uploading",
                        )
                elif event == "upload_failed":
                    set_state(last_result=info.get("detail", "Upload failed"), phase_label="Upload failed")
                    if tft:
                        tft.show_sync_result(False, info.get("filename", ""), info.get("detail", "Upload failed"), allow_reboot=False)

            if pending:
                print(f"[Sync] Starting upload of {len(pending)} file(s)...")
                from lib.uploader import sync_all
                # sync_all now handles its own per-request locking via network_lock
                success = sync_all(sm_ref, led_ref, wdt, network_lock, status_cb=upload_status)
                if success:
                    print("[Sync] All files uploaded successfully!")
                    led_ref.play_idle() # Back to idle/ready
                    synced_count = len(pending)
                    set_state(
                        allow_reboot=True,
                        phase_label="Complete",
                        last_result="All files uploaded",
                        pending_bytes=0,
                        sync_complete=True,
                        synced_files_count=synced_count,
                    )
                    if tft:
                        tft.show_sync_complete(
                            synced_count=synced_count,
                            track_name=get_state("last_track_name"),
                            allow_reboot=True,
                        )
                else:
                    print("[Sync] One or more uploads failed.")
                    led_ref.play_heartbeat_error()
                    fail_reason = get_state("last_result") or "One or more uploads failed"
                    set_state(allow_reboot=False, phase_label="Upload failed", last_result=fail_reason, sync_complete=False)
                    if tft:
                        tft.show_sync_result(False, detail=fail_reason, allow_reboot=False)
            else:
                print("[Sync] No pending files.")
                led_ref.play_idle()
                set_state(phase_label="Idle", pending_bytes=0)
                if tft:
                    tft.show_sync_queue([], allow_reboot=get_state("allow_reboot"), total_bytes=0)
        except Exception as e:
            print(f"[Sync] Uploader Thread Fatal: {e}")
            led_ref.play_heartbeat_error()
            set_state(allow_reboot=False, phase_label="Fatal error", last_result=str(e))
            if tft:
                tft.show_sync_result(False, detail=str(e), allow_reboot=False)
        finally:
            set_state(uploader_busy=False, uploader_started=False)

    # --- PHASE 1: INITIAL HANDSHAKE ---
    hb_ok = False

    if not needs_setup and config.get('ssid') and not wifi_connected:
        connect_result = attempt_wifi_connect()
        if connect_result == "exit":
            return "home"
    
    if wifi_connected:
        print("[Sync] Performing initial handshake...")
        set_state(phase_label="Handshake")
        # Try initial handshake up to 3 times
        for i in range(3):
            with network_lock:
                hb_ok = perform_heartbeat()
            set_state(hb_ok=hb_ok)
            if hb_ok: break
            print(f"[Sync] Handshake retry {i+1}/3...")
            time.sleep(2)
        
        if hb_ok:
            print("[Sync] Handshake successful.")
            set_state(phase_label="Cloud ready")
            spawn_uploader()
        else:
            print("[Sync] Handshake failed. Will retry in background.")
            diag.record_phase("SYNC_HANDSHAKE_FAILED")
            set_state(phase_label="Handshake failed", last_result="Will retry")

    # --- PHASE 2: MAIN SYNC LOOP (Core 0) ---
    print("[Sync] Sync Engine Ready.")
    diag.record_phase("SYNC_READY")
    diag.mark_boot_completed("sync_loop_running")
    press_start = 0
    last_ping = time.ticks_ms()
    pending_count = -1
    pending_bytes = 0
    last_pending_refresh = time.ticks_ms()
    wdt.feed()
    
    while True:
        wdt.feed()
        current_time = time.ticks_ms()
        if poll_shutdown_button(current_time):
            perform_soft_shutdown(sm=sm, tft=tft, power_hold=power_hold, reason="button_long_press_sync")
        vbatt_now = get_vbatt()
        low_power, critical_power = apply_power_policy(vbatt_now, network.WLAN(network.STA_IF) if wifi_connected else None)
        
        if get_state("pairing_active"):
            led.play_pairing()
            ap_name = get_unique_ap_name()
            if tft:
                tft.show_pairing(ap_name)
            time.sleep_ms(50)
            continue

        if get_state("reboot_requested") and not get_state("uploader_busy"):
            print("[Sync] Reboot requested from screen.")
            diag.record_phase("SYNC_REBOOT_REQUESTED")
            stop_wifi()
            time.sleep_ms(300)
            diag.mark_expected_reset("sync_reboot")
            machine.reset()

        if get_state("wifi_retry_requested") and not get_state("uploader_busy"):
            set_state(wifi_retry_requested=False)
            connect_result = attempt_wifi_connect()
            if connect_result == "exit":
                return "home"
            if wifi_connected:
                print("[Sync] WiFi retry succeeded.")
                print("[Sync] Performing initial handshake...")
                set_state(phase_label="Handshake")
                for i in range(3):
                    with network_lock:
                        hb_ok = perform_heartbeat()
                    set_state(hb_ok=hb_ok)
                    if hb_ok:
                        break
                    print(f"[Sync] Handshake retry {i+1}/3...")
                    time.sleep(2)
                if hb_ok:
                    spawn_uploader()
                else:
                    print("[Sync] Handshake failed. Will retry in background.")
                    diag.record_phase("SYNC_HANDSHAKE_FAILED")
                    set_state(phase_label="Handshake failed", last_result="Will retry")
            time.sleep_ms(50)
            continue

        if get_state("portal_requested") and not get_state("uploader_busy"):
            if network_lock.acquire(False):
                try:
                    print("[Sync] Entering Pairing Mode...")
                    diag.record_phase("SYNC_PORTAL_START", "deferred")
                    stop_wifi()
                    time.sleep_ms(200)
                    from lib.captive_portal import start_background_portal
                    gc.collect()
                    _thread.stack_size(16384)
                    _thread.start_new_thread(start_background_portal, (led,))
                    set_state(pairing_active=True, portal_requested=False, hb_ok=False)
                    diag.mark_boot_completed("pairing_portal_running")
                    if tft:
                        tft.show_pairing(get_unique_ap_name())
                finally:
                    network_lock.release()
                time.sleep_ms(50)
                continue
            
        # Periodic Heartbeat (Every 15s)
        if wifi_connected and not get_state("uploader_busy") and not get_state("portal_requested") and not get_state("sync_complete") and time.ticks_diff(current_time, last_ping) > 15000:
            if network_lock.acquire(False): # Only heartbeat if lock is free
                try:
                    last_ping = current_time
                    success = perform_heartbeat()
                    hb_ok = success
                    set_state(hb_ok=success)
                    if success and not get_state("uploader_started"):
                        spawn_uploader()
                    
                finally:
                    network_lock.release()
                    gc.collect()

        if tft and not get_state("uploader_busy"):
            touch_action = tft.sync_touch()
            if touch_action == "retry_wifi":
                print("[Sync] WiFi rescan requested from touchscreen.")
                set_state(wifi_retry_requested=True)
            elif touch_action == "exit":
                print("[Sync] Exit requested from touchscreen.")
                try:
                    stop_wifi()
                except Exception:
                    pass
                return "home"
            elif touch_action == "repair":
                print("[Sync] Pairing requested from touchscreen.")
                set_state(portal_requested=True)
            elif touch_action == "reboot" and get_state("allow_reboot") and not get_state("uploader_busy"):
                print("[Sync] Reboot requested from touchscreen.")
                set_state(reboot_requested=True)
        
        # Visual Status
        if not get_state("uploader_busy"):
            if pending_count < 0 or time.ticks_diff(current_time, last_pending_refresh) > 2000:
                try:
                    pending_summary = sm.get_pending_summary()
                    pending_count = pending_summary.get("count", 0)
                    pending_bytes = pending_summary.get("total_bytes", 0)
                    set_state(pending_bytes=pending_bytes)
                except:
                    pending_count = 0
                    pending_bytes = 0
                last_pending_refresh = current_time
            if needs_setup:
                led.play_setup_needed()
            elif critical_power:
                led.play_storage_critical()
            elif get_state("hb_ok"):
                led.play_sync_ok()
            elif get_state("wifi_failed"):
                led.play_sync_fail()
            elif wifi_connected:
                led.play_heartbeat_error()
            else:
                led.play_sync_fail()
            if tft:
                if get_state("wifi_failed"):
                    tft.show_sync_wifi_failed(config.get('ssid', ''), allow_retry=True)
                elif get_state("sync_complete"):
                    tft.show_sync_complete(
                        synced_count=get_state("synced_files_count"),
                        track_name=get_state("last_track_name"),
                        allow_reboot=get_state("allow_reboot"),
                    )
                else:
                    tft.show_sync_idle(
                        get_state("hb_ok"),
                        pending_count=pending_count,
                        pending_bytes=pending_bytes,
                        low_power=get_state("low_power_mode"),
                        allow_reboot=(pending_count == 0 and get_state("allow_reboot")),
                        phase_label=get_state("phase_label"),
                        last_result=get_state("last_result"),
                        track_name=get_state("last_track_name"),
                    )

        if sync_btn and sync_btn.value() == 0:
            if press_start == 0:
                press_start = time.ticks_ms()
            elif time.ticks_diff(time.ticks_ms(), press_start) > 3000:
                print("[Sync] Pairing requested. Waiting for network activity to quiesce.")
                set_state(portal_requested=True)
                press_start = 0
        else:
            press_start = 0
        
        time.sleep_ms(50)


# ==================================================================
# LOGGING MODE — Pure telemetry capture. No radio.
# ==================================================================

def logging_loop(led, gps, imu, sm, track_eng, tft, vbat_adc, wdt, power_hold):
    """
    Dual-rate logging loop:
      - IMU sampled at 100 Hz (every tick)
      - GPS sampled at  10 Hz (every 10th tick)
      - Buffered writes flushed every 20 rows (~200ms)
    """
    
    loop_count = 0
    FLUSH_INTERVAL = 20  # rows before flushing to SD
    LOGGING_UI_INTERVAL_TICKS = 6000  # 60s at 100Hz
    IMU_VALIDATION_DURATION_MS = 5000
    
    print("\n[System] Logging Active — 100Hz IMU / 10Hz GPS — All radios OFF")
    diag.record_phase("LOGGING_START")
    diag.mark_boot_completed("logging_loop_running")
    prepare_shared_spi_bus()
    log_file = sm.get_log_file()
    try:
        from lib.imu_calibration import get_selected_profile
        selected_profile = get_selected_profile()
    except Exception:
        selected_profile = None
    selected_profile_name = str((selected_profile or {}).get("name") or (selected_profile or {}).get("label") or "")
    print(f"[System] Session file: {log_file}")
    if tft:
        track_status = track_eng.get_status()
        ram_used_mb, ram_total_mb = get_ram_usage_mb(force=True)
        update_display_context(tft, sm, vbat_adc, ram_used_mb=ram_used_mb, ram_total_mb=ram_total_mb, force_battery=True)
        tft.show_logging_started(
            log_file,
            track_name=track_status.get("track_name"),
            elapsed_minutes=0,
            force=True,
            track_data=track_eng.track,
        )
    
    # RTC sync flag
    rtc_synced = False
    
    # Write buffers for batched SD writes
    write_buf = []
    flush_buf = []
    storage_fault = False
    storage_critical = False
    stop_logging = False
    hard_stop_reason = ""
    max_loop_ms = 0
    overrun_count = 0
    marker_seq = 0
    dropped_rows = 0
    max_queue_depth = 0
    min_heap = -1
    rollout_imu_samples = []
    rollout_gps_samples = []
    rollout_validation = {
        "status_text": "LOW CONFIDENCE" if not selected_profile else "ORIENTATION OK",
        "source_mode": "gps_assisted" if not selected_profile else "imu_trusted",
        "reason": "no_profile" if not selected_profile else "",
        "confidence": 0.2 if not selected_profile else 0.9,
    }
    last_validation_render_tick = -100
    validation_start_ms = time.ticks_ms()
    validation_complete = False
    validation_live_shown = False
    
    # Cached values
    vbat = get_battery_voltage(vbat_adc, force=True)
    imu_buf = [0, 0, 0, 0, 0, 0]
    fix = {'valid': False, 'lat': None, 'lon': None, 'altitude': 0.0,
           'speed_kmh': 0.0, 'satellites': 0, 'timestamp': None, 'date': None}
    base_state = "SEARCHING"
    
    try:
        f = open(log_file, 'w')
        f.write("tick_ms,row_type,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,lat,lon,alt,speed,sats,vbat,gps_epoch\n")
        f.flush()
        print(f"[System] Log file opened: {log_file}")
    except Exception as e:
        print(f"[System] FAILED to open log file: {e}")
        f = None

    def sample_heap():
        nonlocal min_heap
        try:
            current = gc.mem_free()
            if min_heap < 0 or current < min_heap:
                min_heap = current
            return current
        except:
            return -1

    def close_log_file():
        nonlocal f
        if f:
            try:
                f.close()
            except:
                pass
            f = None

    def queue_row(line):
        nonlocal dropped_rows, max_queue_depth
        pending = len(write_buf) + len(flush_buf)
        if pending >= 800:
            dropped_rows += 1
            if dropped_rows == 1 or dropped_rows % 100 == 0:
                print(f"[System] WRITE QUEUE OVERFLOW: dropped_rows={dropped_rows}")
            return False
        write_buf.append(line)
        pending += 1
        if pending > max_queue_depth:
            max_queue_depth = pending
        return True

    def schedule_flush(force=False):
        nonlocal write_buf, flush_buf
        if not f or storage_fault or flush_buf:
            return
        if write_buf and (force or len(write_buf) >= FLUSH_INTERVAL):
            flush_buf, write_buf = write_buf, []

    def flush_write_buf():
        nonlocal storage_fault, stop_logging, hard_stop_reason, flush_buf
        if not f or not flush_buf or storage_fault:
            return
        try:
            f.write(''.join(flush_buf))
            f.flush()
            flush_buf = []
        except Exception as e:
            storage_fault = True
            stop_logging = True
            hard_stop_reason = "storage_write_failure"
            print(f"[System] STORAGE WRITE FAILURE: {e}")
            diag.record_phase("LOGGING_STORAGE_FAULT", str(e))
            diag.update_runtime_stats(storage_fault=True, storage_fault_reason=str(e), min_heap=min_heap)
            try:
                marker_seq_local = marker_seq + 1
                row = [
                    str(time.ticks_ms()),
                    'M',
                    '',
                    '',
                    '',
                    '',
                    '',
                    '',
                    'MARKER',
                    'LOG_STOP',
                    str(marker_seq_local),
                    hard_stop_reason,
                    '',
                    f"{vbat:.2f}",
                ]
                flush_buf.append(','.join(row) + '\n')
            except:
                pass
            close_log_file()

    def append_marker(marker_name, marker_value=""):
        nonlocal marker_seq
        if not f or storage_fault:
            return
        marker_seq += 1
        row = [
            str(time.ticks_ms()),
            'M',
            '',
            '',
            '',
            '',
            '',
            '',
            'MARKER',
            marker_name,
            str(marker_seq),
            marker_value,
            '',
            f"{vbat:.2f}",
        ]
        queue_row(_format_csv_row(row))

    def append_json_marker(marker_name, payload):
        try:
            append_marker(marker_name, ujson.dumps(payload))
        except Exception as e:
            append_marker(marker_name, "json_error:%s" % e)

    append_marker("LOG_OPEN", log_file.split('/')[-1])
    if selected_profile:
        append_json_marker("IMU_PROFILE", selected_profile)
    else:
        append_marker("IMU_PROFILE", "none")
    
    while True:
        tick_start = time.ticks_ms()
        tick_ms = tick_start
        loop_count += 1
        
        # Feed watchdog every tick
        wdt.feed()
        if poll_shutdown_button(tick_ms):
            print("[PWR] Long press detected during logging.")
            if not stop_logging:
                stop_logging = True
                hard_stop_reason = "button_shutdown"
                append_marker("LOG_STOP", hard_stop_reason)
            schedule_flush(force=True)
            if f and flush_buf:
                flush_write_buf()
            if f and write_buf:
                schedule_flush(force=True)
                if flush_buf:
                    flush_write_buf()
            close_log_file()
            perform_soft_shutdown(sm=sm, tft=tft, power_hold=power_hold, reason="button_long_press_logging")

        # ── 1. IMU READ (every tick = 100 Hz) ──
        acc_x, acc_y, acc_z = 0.0, 0.0, 0.0
        gyr_x, gyr_y, gyr_z = 0.0, 0.0, 0.0
        if imu:
            try:
                imu.get_values_into(imu_buf)
                acc_x = imu_buf[0] / imu.ACC_SENSITIVITY
                acc_y = imu_buf[1] / imu.ACC_SENSITIVITY
                acc_z = imu_buf[2] / imu.ACC_SENSITIVITY
                gyr_x = imu_buf[3] / imu.GYR_SENSITIVITY
                gyr_y = imu_buf[4] / imu.GYR_SENSITIVITY
                gyr_z = imu_buf[5] / imu.GYR_SENSITIVITY
            except:
                pass
        
        # Write IMU row (row_type = I, GPS fields empty, including gps_epoch)
        if f and not stop_logging:
            queue_row(f"{tick_ms},I,{acc_x:.4f},{acc_y:.4f},{acc_z:.4f},{gyr_x:.2f},{gyr_y:.2f},{gyr_z:.2f},,,,,,\n")
            if loop_count <= 500:
                rollout_imu_samples.append({
                    "acc": [acc_x, acc_y, acc_z],
                    "gyro": [gyr_x, gyr_y, gyr_z],
                })
        
        # ── 2. GPS READ (every 10th tick = 10 Hz) ──
        if loop_count % 10 == 0:
            fix = gps.update(max_lines=4)
            
            # Sync RTC to GPS once
            if not rtc_synced and fix.get('valid'):
                try:
                    d = fix['date']
                    t = fix['timestamp']
                    year = 2000 + int(d[4:6])
                    month = int(d[2:4])
                    day = int(d[0:2])
                    hour = int(t[0:2])
                    minute = int(t[2:4])
                    second = int(t[4:6])
                    
                    # Convert to standard UNIX epoch (1970)
                    # MicroPython time.mktime operates on 2000 epoch, so add 946684800
                    try:
                        fix['gps_epoch'] = time.mktime((year, month, day, hour, minute, second, 0, 0)) + 946684800
                    except:
                        fix['gps_epoch'] = 0
                    machine.RTC().datetime((year, month, day, 0, hour, minute, second, 0))
                    rtc_synced = True
                    print(f"[System] RTC Synced to GPS: {year}-{month}-{day} {hour}:{minute}:{second}")
                except:
                    pass
            
            # Write GPS row if we have a fresh valid fix
            if f and not stop_logging and fix['valid'] and gps.new_fix:
                epoch_val = fix.get('gps_epoch', 0)
                queue_row(f"{tick_ms},G,{acc_x:.4f},{acc_y:.4f},{acc_z:.4f},{gyr_x:.2f},{gyr_y:.2f},{gyr_z:.2f}," +
                          f"{fix['lat']:.15g},{fix['lon']:.15g},{fix['altitude']:.1f},{fix['speed_kmh']:.2f},{fix['satellites']},{vbat:.2f},{epoch_val}\n")
                if loop_count <= 500:
                    rollout_gps_samples.append({
                        "speed": float(fix.get("speed_kmh") or 0.0),
                        "lat": fix.get("lat"),
                        "lon": fix.get("lon"),
                    })
                
                # Track Engine (only on GPS rows)
                try:
                    event = track_eng.update(fix['lat'], fix['lon'], float(tick_ms))
                    if event:
                        led_event = event.get("led_event") if isinstance(event, dict) else event
                        if led_event:
                            led.trigger_event(led_event)
                        if led_event == "TRACK_FOUND":
                            led.set_track_mode(True)
                        if tft:
                            track_status = track_eng.get_status()
                            tft.show_track_event(
                                event,
                                track_name=track_status.get("track_name"),
                                sector=(event.get("sector_index") if isinstance(event, dict) else (track_status.get("current_sector", 0) + 1)),
                                track_data=track_eng.track,
                            )
                except Exception as e:
                    if loop_count % 100 == 0:
                        print(f"TrackEng Error: {e}")
            
            # LOGGING is solid green
            if not storage_critical and not stop_logging:
                base_state = "LOGGING" if fix['valid'] else "SEARCHING"
                if fix['valid']:
                    led.play_logging()
                else:
                    led.play_searching()
            
            # Debug output (every ~1s = every 10 GPS ticks)
            if loop_count % 100 == 0:
                print(f"[DBG] valid={fix['valid']} lat={fix['lat']} lon={fix['lon']} sats={fix['satellites']} queue={len(write_buf)+len(flush_buf)} dropped={dropped_rows}")
        
        # ── 3. FLUSH WRITE BUFFER ──
        if f and len(write_buf) >= FLUSH_INTERVAL:
            schedule_flush()
        if f and flush_buf:
            flush_write_buf()
        
        # ── 4. BATTERY (every 100th tick = ~1 Hz) ──
        if loop_count % 100 == 0:
            try:
                vbat = get_battery_voltage(vbat_adc, force=True)
                if vbat > 0 and vbat < 3.55:
                    led.set_brightness(0.08)
                elif vbat > 0 and vbat < 3.70:
                    led.set_brightness(0.15)
                else:
                    led.set_brightness(0.35)
            except:
                vbat = 0.0
        
        # ── 5. STORAGE CHECK (every 1000th tick = ~10s) ──
        if loop_count % LOGGING_UI_INTERVAL_TICKS == 0:
            elapsed_minutes = loop_count // LOGGING_UI_INTERVAL_TICKS
            ram_used_mb, ram_total_mb = get_ram_usage_mb(force=True)
            track_status = track_eng.get_status()
            update_display_context(tft, sm, vbat_adc, ram_used_mb=ram_used_mb, ram_total_mb=ram_total_mb)
            if tft and loop_count > 500:
                tft.show_logging_live(
                    log_file,
                    sats=fix.get('satellites', 0),
                    gps_ok=fix.get('valid', False),
                    track_name=track_status.get("track_name"),
                    elapsed_minutes=elapsed_minutes,
                    track_data=track_eng.track,
                )
        validation_active = not validation_complete and time.ticks_diff(tick_ms, validation_start_ms) < IMU_VALIDATION_DURATION_MS
        if tft and validation_active and (loop_count - last_validation_render_tick) >= 10:
            last_validation_render_tick = loop_count
            pitch_deg, roll_deg = _profile_mount_angles(selected_profile)
            tft.show_logging_validation(
                selected_profile_name or "UNSET",
                _profile_heading_deg(selected_profile),
                pitch_deg,
                roll_deg,
                rollout_validation.get("status_text"),
            )
        if not validation_complete and time.ticks_diff(tick_ms, validation_start_ms) >= IMU_VALIDATION_DURATION_MS:
            validation_complete = True
            rollout_validation = _rollout_validation_status(selected_profile, rollout_gps_samples, rollout_imu_samples)
            append_json_marker("IMU_VALIDATION", rollout_validation)
            if tft:
                pitch_deg, roll_deg = _profile_mount_angles(selected_profile)
                tft.show_logging_validation(
                    selected_profile_name or "UNSET",
                    _profile_heading_deg(selected_profile),
                    pitch_deg,
                    roll_deg,
                    rollout_validation.get("status_text"),
                )
        if validation_complete and not validation_live_shown and tft:
            track_status = track_eng.get_status()
            tft.invalidate()
            tft.show_logging_live(
                log_file,
                sats=fix.get('satellites', 0),
                gps_ok=fix.get('valid', False),
                track_name=track_status.get("track_name"),
                elapsed_minutes=0,
                track_data=track_eng.track,
            )
            validation_live_shown = True
        if loop_count % 1000 == 0:
            ram_used_mb_storage, ram_total_mb_storage = get_ram_usage_mb()
            try:
                s_info = sm.get_active_storage_info()
                if s_info and s_info['total_kb'] > 0:
                    usage = s_info['used_kb'] / s_info['total_kb']
                    if usage > 0.90:
                        storage_critical = True
                        base_state = "STORAGE_CRITICAL"
                        led.play_storage_critical()
                        print(f"[System] STORAGE CRITICAL: {s_info['used_kb']}/{s_info['total_kb']} KB")
                    if usage > 0.98 and not stop_logging:
                        stop_logging = True
                        hard_stop_reason = "storage_hard_limit"
                        print("[System] STORAGE HARD LIMIT REACHED. Stopping log growth to protect filesystem.")
                        diag.record_phase("LOGGING_STORAGE_HARD_LIMIT")
                        append_marker("LOG_STOP", hard_stop_reason)
                        schedule_flush(force=True)
                        flush_write_buf()
                        close_log_file()
            except:
                pass
        
        # ── 6. PERIODIC MAINTENANCE ──
        if loop_count % 100 == 0:
            try:
                if f and not storage_fault:
                    os.sync()
            except:
                storage_fault = True
                stop_logging = True
                hard_stop_reason = "storage_sync_failure"
                diag.record_phase("LOGGING_STORAGE_SYNC_FAULT")
                append_marker("LOG_STOP", hard_stop_reason)
                schedule_flush(force=True)
                close_log_file()

        if not stop_logging and loop_count % 5000 == 0:
            append_marker("CHECKPOINT", str(loop_count))
            schedule_flush()
        
        if loop_count % 1000 == 0:
            gc.collect()
            sample_heap()
            mem_info = get_memory_profile()
            diag.update_runtime_stats(
                loop_count=loop_count,
                loop_state=base_state,
                min_heap=min_heap,
                max_loop_ms=max_loop_ms,
                overrun_count=overrun_count,
                stop_logging=stop_logging,
                stop_reason=hard_stop_reason,
                storage_critical=storage_critical,
                gps_health=gps.get_health(),
                led_health=led.get_health(),
                vbat=vbat,
                queue_depth=len(write_buf) + len(flush_buf),
                dropped_rows=dropped_rows,
                max_queue_depth=max_queue_depth,
                psram_present=mem_info.get("psram_present"),
                gc_free_kb=mem_info.get("gc_free", 0) // 1024,
                idf_free_kb=mem_info.get("idf_free", 0) // 1024,
                idf_largest_kb=mem_info.get("idf_largest", 0) // 1024,
            )
            print(f"[Loop] State: {base_state} | Fix: {fix.get('valid')} | Loops: {loop_count} | Queue: {len(write_buf)+len(flush_buf)} | Dropped: {dropped_rows} | MinHeap: {min_heap} | GCFreeKB: {mem_info.get('gc_free', 0) // 1024} | MaxLoop: {max_loop_ms}")


        # ── 7. TIMING — Target 10ms per tick (100 Hz) ──
        elapsed_ms = time.ticks_diff(time.ticks_ms(), tick_start)
        if elapsed_ms > max_loop_ms:
            max_loop_ms = elapsed_ms
        remaining = 10 - elapsed_ms
        if remaining > 0:
            time.sleep_ms(remaining)
        else:
            overrun_count += 1
            
if __name__ == "__main__":
    try:
        main()
    except Exception as e: 
        import sys
        print(f"CRITICAL SYSTEM ERROR: {e}")
        diag.mark_exception(e)
        try:
            with open('/crash.log', 'w') as f:
                sys.print_exception(e, f)
        except:
            pass
        time.sleep(5)
        diag.mark_expected_reset("critical_exception")
        machine.reset()
