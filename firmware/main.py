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
from drivers.oled import SSD1306_I2C, SH1106_I2C
from lib.session_manager import SessionManager
from lib.led_manager import LEDManager
from lib.track_engine import TrackEngine
from lib.oled_status import OLEDStatus
from lib.memory_profile import get_memory_profile, format_memory_profile
from lib import boot_diagnostics as diag

TRACK_RESPONSE_LIMIT = 16 * 1024
TRACK_RESPONSE_READ_SIZE = 1024

# --- MASTER PINOUT CONFIG (ESP32-S3 RS-CORE V2) ---
PIN_LED_FEEDBACK = 4    # Feedback NeoPixel (16-LED matrix)
PIN_BUTTON_SYNC = 5     # Sync Button (GND-btn-IO5, active LOW)
PIN_LED_ONBOARD = 6     # Onboard NeoPixel (1 LED, mirrors feedback)
PIN_GPS_RX = 18
PIN_GPS_TX = 17
PIN_I2C_SDA = 21
PIN_I2C_SCL = 39
PIN_SD_SCK = 12
PIN_SD_MOSI = 11
PIN_SD_MISO = 13
PIN_SD_CS = 10
PIN_SD_CD = 3           # Card Detect
PIN_BATTERY_ADC = 7      # VBAT-SENSE (100k/100k divider)
PIN_DEBUG_LED = 2       # Blue Debug LED

# Sensitivity constants now handled by IMU driver class


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
        return (vbat_adc.read_uv() / 1000000.0) * 2.0
    except Exception:
        return 0.0


def get_storage_used_percent(sm):
    try:
        info = sm.get_active_storage_info()
        if not info or info.get('total_kb', 0) <= 0:
            return None
        return int(round((info['used_kb'] * 100.0) / info['total_kb']))
    except Exception:
        return None


def raw_oled_wake(i2c, label="wake"):
    for cls, name in ((SSD1306_I2C, "ssd1306"), (SH1106_I2C, "sh1106")):
        probe = cls(128, 64, i2c, addr=0x3C)
        probe.fill(1)
        probe.show()
        time.sleep_ms(120)
        probe.fill(0)
        probe.show()
        time.sleep_ms(80)
        print("[OLED] Raw wake via", name)
    probe = SH1106_I2C(128, 64, i2c, addr=0x3C)
    probe.fill(0)
    probe.show()


def revive_oled(i2c, sd_mounted, sm, battery_pct=None, imu_ok=None, gps_ok=None, gps_baud=None, gps_rate_hz=None, label="wake"):
    raw_oled_wake(i2c, label=label)
    oled = OLEDStatus(i2c, addr=0x3C, controller="sh1106")
    oled.set_context(battery_pct=battery_pct, sd_ok=sd_mounted, sd_pct=get_storage_used_percent(sm))
    oled.show_startup_logo()
    time.sleep_ms(3000)
    oled.show_boot(
        "Device status",
        sd_ok=sd_mounted,
        imu_ok=imu_ok,
        gps_ok=gps_ok,
        gps_baud=gps_baud,
        gps_rate_hz=gps_rate_hz,
        storage_info=sm.get_active_storage_info(),
        force=True,
    )
    time.sleep_ms(2000)
    print("[OLED] Wake complete:", label)
    return oled

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
    
    # 3. Battery Monitor
    diag.record_phase("BOOT_BATTERY_INIT")
    vbat_adc = machine.ADC(machine.Pin(PIN_BATTERY_ADC))
    vbat_adc.atten(machine.ADC.ATTN_11DB)

    # 4. Mount SD Card (Native ESP32 SD driver — proven working in full_system_test.py)
    sd_mounted = False
    diag.record_phase("BOOT_SD_INIT")
    try:
        sd = machine.SDCard(slot=2, width=1, sck=machine.Pin(PIN_SD_SCK), mosi=machine.Pin(PIN_SD_MOSI), miso=machine.Pin(PIN_SD_MISO), cs=machine.Pin(PIN_SD_CS))
        os.mount(sd, '/sd')
        print("Storage: SD CARD MOUNTED SUCCESS")
        sd_mounted = True
    except Exception as e:
        print(f"Storage: SD Mount Failed ({e}). Using Onboard Flash.")

    # 5. Session Manager
    sm = SessionManager(sd_mounted=sd_mounted)
    oled = None
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
            try:
                auto_i2c = machine.I2C(0, sda=machine.Pin(PIN_I2C_SDA), scl=machine.Pin(PIN_I2C_SCL), freq=100000)
                oled = revive_oled(auto_i2c, sd_mounted, sm, battery_pct=calculate_battery_percentage(read_vbatt(vbat_adc)), label="copy")
                if oled:
                    oled.show_flash_transfer()
            except Exception as e:
                print(f"[OLED] Auto-copy display unavailable ({e})")
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
        if oled:
            oled.show_boot("IMU failed", sd_ok=sd_mounted, imu_ok=False, storage_info=sm.get_active_storage_info(), force=True)

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
    if oled:
        oled.show_boot("GPS configured", sd_ok=sd_mounted, imu_ok=imu is not None, gps_baud=115200, gps_rate_hz=10)

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
    
    end_ms = time.ticks_ms()
    duration = time.ticks_diff(end_ms, start_ms)
    if sentences_received >= 5:
        freq = 5 / (duration / 1000.0)
        print(f"GPS: Received 5 sentences in {duration}ms ({freq:.2f}Hz)")
    else:
        print(f"GPS: Diagnostic timeout. Received only {sentences_received} sentences in {duration}ms.")
    if oled:
        oled.show_boot(
            "Sensors ready",
            sd_ok=sd_mounted,
            imu_ok=imu is not None,
            gps_ok=sentences_received >= 5,
            gps_baud=115200,
            gps_rate_hz=10,
            storage_info=sm.get_active_storage_info(),
            force=True,
        )
        oled.tick(force=True)

    # 8. Track Engine
    diag.record_phase("BOOT_TRACK_INIT")
    track_eng = TrackEngine()
    track_eng.load_track()

    # 9. OLED late init. The panel reliably wakes only after the rest of boot has settled.
    try:
        time.sleep_ms(600)
        oled = revive_oled(
            i2c,
            sd_mounted,
            sm,
            battery_pct=calculate_battery_percentage(read_vbatt(vbat_adc)),
            imu_ok=imu is not None,
            gps_ok=sentences_received >= 5,
            gps_baud=115200,
            gps_rate_hz=10,
            label="boot1",
        )
        print("[OLED] Initialized during late boot")
    except Exception as e:
        print(f"OLED: Failed to initialize ({e})")

    # 10. Watchdog Timer (Increase to 20s for network operations)
    diag.record_phase("BOOT_WDT_INIT")
    wdt = machine.WDT(timeout=20000)

    imu_ok = imu is not None
    gps_ok = sentences_received >= 5

    return led, gps, imu, sm, track_eng, oled, i2c, vbat_adc, wdt, sd_mounted, imu_ok, gps_ok, gps_uart, sentences_received

def main():
    prev_state, current_state = diag.boot_start()
    print("[Diag] Reset cause:", current_state.get("reset_cause"))
    if prev_state:
        print("[Diag] Previous phase:", prev_state.get("last_phase", "n/a"))
        if prev_state.get("exception"):
            print("[Diag] Previous exception:", prev_state.get("exception"))

    led, gps, imu, sm, track_eng, oled, i2c, vbat_adc, wdt, sd_mounted, imu_ok, gps_ok, gps_uart, sentences_received = setup()
    
    # --- Sync Button (IO5) ---
    sync_btn = machine.Pin(PIN_BUTTON_SYNC, machine.Pin.IN, machine.Pin.PULL_UP)
    
    # --- FIRST-TIME SETUP CHECK ---
    # If no WiFi credentials exist, skip button check and go straight to pairing
    from lib.wifi_manager import load_device_config
    config = load_device_config()
    if not config.get('ssid'):
        print("\n[System] No WiFi configured — First-time setup! Entering Pairing Mode.")
        diag.record_phase("SYNC_SETUP_NEEDED")
        if oled:
            oled.show_first_time_setup()
        run_sync_mode(led, sm, oled, sync_btn, wdt, vbat_adc)
        return  # Never reaches here (sync mode loops forever)
    
    # --- 10-SECOND DECISION WINDOW ---
    print("\n[System] 10s Decision Window — Press SYNC button to enter Sync Mode")
    diag.record_phase("BOOT_DECISION_WINDOW")
    if not gps_ok:
        print("[System] GPS ERROR: No NMEA data detected. Holding in Decision Window.")
    
    sync_requested = False
    start = time.ticks_ms()
    oled_retry_count = 0
    next_oled_retry_ms = time.ticks_add(start, 2000)
    
    while True:
        elapsed = time.ticks_diff(time.ticks_ms(), start)
        wdt.feed()
        
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
        
        if oled is None and i2c and oled_retry_count < 4 and time.ticks_diff(time.ticks_ms(), next_oled_retry_ms) >= 0:
            try:
                oled_retry_count += 1
                label = "retry%d" % oled_retry_count
                print("[OLED] Decision-window wake attempt:", label)
                oled = revive_oled(
                    i2c,
                    sd_mounted,
                    sm,
                    imu_ok=imu_ok,
                    gps_ok=gps_ok,
                    gps_baud=115200,
                    gps_rate_hz=10,
                    label=label,
                )
            except Exception as e:
                print("[OLED] Decision-window wake failed:", e)
            next_oled_retry_ms = time.ticks_add(time.ticks_ms(), 2000)

        # Update LED with current health status
        led.play_decision(sd_mounted, imu_ok, gps_ok)
        if oled:
            oled.set_context(
                battery_pct=calculate_battery_percentage(read_vbatt(vbat_adc)),
                sd_ok=sd_mounted,
                sd_pct=get_storage_used_percent(sm),
            )
            remaining_ms = 10000 - elapsed
            oled.show_decision(sd_mounted, imu_ok, gps_ok, gps_sentences=sentences_received, countdown_ms=remaining_ms)
            oled.tick(force=True)
        
        # Check button (active LOW — pressed when value() == 0)
        if sync_btn.value() == 0:
            sync_requested = True
            print("[System] SYNC button pressed! Entering Sync Mode.")
            break
        
        # Exit condition: 10s passed AND GPS is okay
        # If GPS is NOT okay, we stay here forever (or until SYNC is pressed)
        if gps_ok and elapsed > 10000:
            break
            
        # Optional: Re-check GPS if it was previously failed? 
        # For now, we stick to the initial check as per requirement ("stays in decision window if problem with gps")
        
        time.sleep_ms(50)

    wdt.feed()
    
    # --- MODE SELECTION ---
    if sync_requested:
        print("\n[System] ==> SYNC MODE")
        diag.record_phase("MODE_SYNC")
        run_sync_mode(led, sm, oled, sync_btn, wdt, vbat_adc)
    else:
        print("\n[System] ==> LOGGING MODE")
        diag.record_phase("MODE_LOGGING")
        # Kill all radios immediately
        from lib.wifi_manager import stop_wifi
        stop_wifi()
        logging_loop(led, gps, imu, sm, track_eng, oled, vbat_adc, wdt)


# ==================================================================
# SYNC MODE — WiFi upload / Pairing. No logging.
# ==================================================================

def run_sync_mode(led, sm, oled, sync_btn, wdt, vbat_adc):
    """
    Exclusive sync mode. No telemetry logging occurs.
    
    Flow:
    1. Search for known WiFi (purple fade).
    2. If found: upload pending files (green blink → green fade on success).
    3. Stay in sync mode after completion.
    4. Long press (>3s) on sync button → enter Pairing mode (blue breathing).
    """
    from lib.wifi_manager import load_device_config, stop_wifi
    
    config = load_device_config()
    wifi_connected = False
    needs_setup = not config.get('ssid')

    def update_oled_context():
        if oled:
            oled.set_context(
                battery_pct=calculate_battery_percentage(read_vbatt(vbat_adc)),
                sd_ok=sm.sd_mounted,
                sd_pct=get_storage_used_percent(sm),
            )
    
    if needs_setup:
        # No saved network — auto-enter pairing mode with rainbow animation
        print("[Sync] No WiFi credentials. Starting Pairing Mode automatically...")
        diag.record_phase("SYNC_PORTAL_START", "no_saved_wifi")
        from lib.captive_portal import start_background_portal
        gc.collect()
        _thread.stack_size(16384) # 16KB for portal
        _thread.start_new_thread(start_background_portal, (led,))
        diag.mark_boot_completed("pairing_portal_running")
        
        # Stay in rainbow loop — portal runs in background
        while True:
            wdt.feed()
            led.play_setup_needed()
            if oled:
                update_oled_context()
                oled.show_first_time_setup()
                oled.tick()
            time.sleep_ms(50)
    
    elif config.get('ssid'):
        # --- Phase 1: Try connecting to known WiFi ---
        print(f"[Sync] Searching for WiFi: {config['ssid']}")
        diag.record_phase("SYNC_WIFI_PREP", config.get('ssid', ''))
        led.set_state("SYNC_SEARCHING")
        if oled:
            update_oled_context()
            oled.show_sync_searching(config.get('ssid', ''))
            oled.tick(force=True)
        
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
            sta.config(txpower=8.5) # Prevent ESP32 brownout spikes
        except:
            pass
        # Inline initial power policy (nested helpers not yet defined)
        try:
            _vbatt_init = (vbat_adc.read_uv() / 1000000.0) * 2.0
            if _vbatt_init > 0 and _vbatt_init < 3.55:
                led.set_brightness(0.10)
                sta.config(txpower=2.0)
            elif _vbatt_init > 0 and _vbatt_init < 3.70:
                led.set_brightness(0.18)
                sta.config(txpower=5.0)
        except:
            pass
        diag.record_phase("SYNC_WIFI_CONNECT", config.get('ssid', ''))
        sta.connect(config['ssid'], config.get('password', ''))
        
        # Wait up to 30s for connection
        for i in range(300):
            wdt.feed()
            
            if sta.isconnected():
                wifi_connected = True
                print(f"[Sync] WiFi Connected! IP: {sta.ifconfig()[0]}")
                diag.record_phase("SYNC_WIFI_CONNECTED", sta.ifconfig()[0])
                led.play_sync_found()
                if oled:
                    update_oled_context()
                    oled.show_sync_connected(config.get('ssid', ''), sta.ifconfig()[0])
                    oled.tick(force=True)
                wdt.feed()
                time.sleep(1)  # Brief visual confirmation
                wdt.feed()
                break
            
            time.sleep_ms(100)
        
        if not wifi_connected:
            print("[Sync] WiFi connection failed.")
            diag.record_phase("SYNC_WIFI_FAILED")
            if oled:
                update_oled_context()
                oled.show_message("SYNC FAIL", "WiFi connect failed", config.get('ssid', ''))
            sta.active(False)
            gc.collect()
    
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
        "hb_ok": False,
        "wifi_connected": wifi_connected,
        "pairing_active": False,
        "portal_requested": False,
        "low_power_mode": False,
        "last_track_name": "",
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
        gc.collect()
        _thread.stack_size(32768) # 32KB for SSL uploader
        _thread.start_new_thread(uploader_thread_func, (sm, led))
        set_state(uploader_started=True)
        return True
    
    # Helper function to get battery voltage
    def get_vbatt():
        """Returns battery voltage in volts using calibrated ADC."""
        try:
            # read_uv() returns microvolts, divide by 1,000,000 for Volts
            # Multiplier is 2.0 for 100k/100k divider
            return (vbat_adc.read_uv() / 1000000.0) * 2.0
        except:
            return 0.0

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
            if oled:
                update_oled_context()
                oled.show_heartbeat("URL error", detail=str(e))
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
            if oled:
                update_oled_context()
                oled.show_heartbeat("Sending", host=host, detail="POST /ping")
            
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
                if oled:
                    update_oled_context()
                    oled.show_heartbeat("ACK OK", host=host, detail="Heartbeat accepted")
                time.sleep(1) # Visual confirmation
                success = True
            else:
                print(f"[Heartbeat] Server Rejected: {resp_line.strip()}")
                if oled:
                    update_oled_context()
                    oled.show_heartbeat("Rejected", host=host, detail=resp_line.strip())
            
            # 5. Active Track Pull (Separate connection for safety)
            if success:
                s_tr = None
                ss_tr = None
                try:
                    gc.collect()
                    diag.record_phase("SYNC_SSL_TRACK_PULL", host)
                    s_tr = socket.socket(ai[0], ai[1], ai[2])
                    s_tr.settimeout(5)
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
                                track_info = t_data["active_track"]
                                if track_info:
                                    with open('/data/metadata/track.json', 'w') as f:
                                        ujson.dump(track_info, f)
                                    print(f"[Sync] Active track saved: {track_info.get('track_name', 'Unknown')}")
                                    set_state(last_track_name=track_info.get('track_name') or track_info.get('name', 'Unknown'))
                                    if oled:
                                        update_oled_context()
                                        oled.show_track_sync(track_info.get('track_name') or track_info.get('name', 'Unknown'))
                                else:
                                    print("[Sync] Active track is null on server.")
                            else:
                                print("[Sync] No 'active_track' key in response.")
                        except Exception as json_e:
                            print(f"[Sync] JSON Parse Error: {json_e}")
                    else:
                        print(f"[Sync] Invalid response (No 200 OK or body separator)")
                except Exception as tr_e:
                    print(f"[Sync] Track Pull Error: {tr_e}")
                finally:
                    if ss_tr: ss_tr.close()
                    if s_tr: s_tr.close()

        except Exception as e:
            print(f"[Heartbeat] Network Error: {e}")
            if oled:
                update_oled_context()
                oled.show_heartbeat("Network error", host=host if 'host' in locals() else "", detail=str(e))
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
            pending = sm_ref.list_sessions()
            if oled:
                update_oled_context()
                oled.show_sync_queue(pending)

            def upload_status(event, **info):
                if not oled:
                    return
                update_oled_context()
                if event == "queue":
                    oled.show_sync_queue(info.get("files", []))
                elif event in ("upload_start", "upload_progress", "upload_done"):
                    oled.show_sync_upload(
                        info.get("filename", ""),
                        info.get("file_index", 0),
                        info.get("total_files", 1),
                        info.get("sent_bytes", 0),
                        info.get("total_bytes", 0),
                        info.get("global_current", 0),
                        info.get("global_total", 0),
                    )
                    if event == "upload_done":
                        oled.show_sync_result(True, info.get("filename", ""), "Archived")
                elif event == "upload_failed":
                    oled.show_sync_result(False, info.get("filename", ""), "Request failed")

            if pending:
                print(f"[Sync] Starting upload of {len(pending)} file(s)...")
                from lib.uploader import sync_all
                # sync_all now handles its own per-request locking via network_lock
                success = sync_all(sm_ref, led_ref, wdt, network_lock, status_cb=upload_status)
                if success:
                    print("[Sync] All files uploaded successfully!")
                    led_ref.play_idle() # Back to idle/ready
                    if oled:
                        update_oled_context()
                        oled.show_sync_result(True, detail="All files uploaded")
                else:
                    print("[Sync] One or more uploads failed.")
                    led_ref.play_heartbeat_error()
                    if oled:
                        update_oled_context()
                        oled.show_sync_result(False, detail="One or more uploads failed")
            else:
                print("[Sync] No pending files.")
                led_ref.play_idle()
                if oled:
                    update_oled_context()
                    oled.show_sync_queue([])
        except Exception as e:
            print(f"[Sync] Uploader Thread Fatal: {e}")
            led_ref.play_heartbeat_error()
            if oled:
                update_oled_context()
                oled.show_sync_result(False, detail=str(e))
        finally:
            set_state(uploader_busy=False, uploader_started=False)

    # --- PHASE 1: INITIAL HANDSHAKE ---
    hb_ok = False
    
    if wifi_connected:
        print("[Sync] Performing initial handshake...")
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
            spawn_uploader()
        else:
            print("[Sync] Handshake failed. Will retry in background.")
            diag.record_phase("SYNC_HANDSHAKE_FAILED")

    # --- PHASE 2: MAIN SYNC LOOP (Core 0) ---
    print("[Sync] Sync Engine Ready.")
    diag.record_phase("SYNC_READY")
    diag.mark_boot_completed("sync_loop_running")
    press_start = 0
    last_ping = time.ticks_ms()
    pending_count = -1
    last_pending_refresh = time.ticks_ms()
    wdt.feed()
    
    while True:
        wdt.feed()
        current_time = time.ticks_ms()
        vbatt_now = get_vbatt()
        low_power, critical_power = apply_power_policy(vbatt_now, network.WLAN(network.STA_IF) if wifi_connected else None)
        
        if get_state("pairing_active"):
            led.play_pairing()
            if oled:
                update_oled_context()
                oled.show_pairing()
                oled.tick()
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
                    if oled:
                        update_oled_context()
                        oled.show_pairing()
                        oled.tick(force=True)
                finally:
                    network_lock.release()
                time.sleep_ms(50)
                continue
            
        # Periodic Heartbeat (Every 15s)
        if wifi_connected and not get_state("uploader_busy") and not get_state("portal_requested") and time.ticks_diff(current_time, last_ping) > 15000:
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
        
        # Visual Status
        if not get_state("uploader_busy"):
            if pending_count < 0 or time.ticks_diff(current_time, last_pending_refresh) > 2000:
                try:
                    pending_count = len(sm.list_sessions())
                except:
                    pending_count = 0
                last_pending_refresh = current_time
            if needs_setup:
                led.play_setup_needed()
            elif critical_power:
                led.play_storage_critical()
            elif get_state("hb_ok"):
                led.play_sync_ok()
            elif wifi_connected:
                led.play_heartbeat_error()
            else:
                led.play_sync_fail()
            if oled:
                update_oled_context()
                oled.show_sync_idle(get_state("hb_ok"), pending_count=pending_count, low_power=get_state("low_power_mode"))
        
        if sync_btn.value() == 0:
            if press_start == 0:
                press_start = time.ticks_ms()
            elif time.ticks_diff(time.ticks_ms(), press_start) > 3000:
                print("[Sync] Pairing requested. Waiting for network activity to quiesce.")
                set_state(portal_requested=True)
                press_start = 0
        else:
            press_start = 0

        if oled:
            oled.tick()
        
        time.sleep_ms(50)


# ==================================================================
# LOGGING MODE — Pure telemetry capture. No radio.
# ==================================================================

def logging_loop(led, gps, imu, sm, track_eng, oled, vbat_adc, wdt):
    """
    Dual-rate logging loop:
      - IMU sampled at 100 Hz (every tick)
      - GPS sampled at  10 Hz (every 10th tick)
      - Buffered writes flushed every 20 rows (~200ms)
    """
    
    loop_count = 0
    FLUSH_INTERVAL = 20  # rows before flushing to SD
    
    print("\n[System] Logging Active — 100Hz IMU / 10Hz GPS — All radios OFF")
    diag.record_phase("LOGGING_START")
    diag.mark_boot_completed("logging_loop_running")
    log_file = sm.get_log_file()
    print(f"[System] Session file: {log_file}")
    if oled:
        track_status = track_eng.get_status()
        oled.set_context(
            battery_pct=calculate_battery_percentage(read_vbatt(vbat_adc)),
            sd_ok=sm.sd_mounted,
            sd_pct=get_storage_used_percent(sm),
        )
        oled.show_logging_started(log_file, track_name=track_status.get("track_name"), force=True)
        oled.tick(force=True)
    
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
    
    # Cached values
    vbat = 0.0
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
        if pending >= 200:
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
        queue_row(','.join(row) + '\n')

    append_marker("LOG_OPEN", log_file.split('/')[-1])
    
    while True:
        tick_start = time.ticks_ms()
        tick_ms = tick_start
        loop_count += 1
        
        # Feed watchdog every tick
        wdt.feed()
        
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
                
                # Track Engine (only on GPS rows)
                try:
                    event = track_eng.update(fix['lat'], fix['lon'], float(tick_ms))
                    if event:
                        led.trigger_event(event)
                        if event == "TRACK_FOUND":
                            led.set_track_mode(True)
                        if oled:
                            track_status = track_eng.get_status()
                            oled.set_context(
                                battery_pct=calculate_battery_percentage(read_vbatt(vbat_adc)),
                                sd_ok=sm.sd_mounted,
                                sd_pct=get_storage_used_percent(sm),
                            )
                            oled.show_track_event(event, track_name=track_status.get("track_name"), sector=(track_status.get("current_sector", 0) + 1))
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
                # Use calibrated microvolt reading for better accuracy
                vbat = read_vbatt(vbat_adc)
                if vbat > 0 and vbat < 3.55:
                    led.set_brightness(0.08)
                elif vbat > 0 and vbat < 3.70:
                    led.set_brightness(0.15)
                else:
                    led.set_brightness(0.35)
            except:
                vbat = 0.0
        
        # ── 5. STORAGE CHECK (every 1000th tick = ~10s) ──
        if loop_count % 1000 == 0:
            try:
                s_info = sm.get_active_storage_info()
                if s_info and s_info['total_kb'] > 0:
                    usage = s_info['used_kb'] / s_info['total_kb']
                    if usage > 0.90:
                        storage_critical = True
                        base_state = "STORAGE_CRITICAL"
                        led.play_storage_critical()
                        print(f"[System] STORAGE CRITICAL: {s_info['used_kb']}/{s_info['total_kb']} KB")
                        if oled:
                            oled.set_context(
                                battery_pct=calculate_battery_percentage(vbat),
                                sd_ok=sm.sd_mounted,
                                sd_pct=get_storage_used_percent(sm),
                            )
                            oled.show_storage_critical(s_info['used_kb'], s_info['total_kb'])
                    if usage > 0.98 and not stop_logging:
                        stop_logging = True
                        hard_stop_reason = "storage_hard_limit"
                        print("[System] STORAGE HARD LIMIT REACHED. Stopping log growth to protect filesystem.")
                        diag.record_phase("LOGGING_STORAGE_HARD_LIMIT")
                        append_marker("LOG_STOP", hard_stop_reason)
                        schedule_flush(force=True)
                        flush_write_buf()
                        close_log_file()
                        if oled:
                            oled.set_context(
                                battery_pct=calculate_battery_percentage(vbat),
                                sd_ok=sm.sd_mounted,
                                sd_pct=get_storage_used_percent(sm),
                            )
                            oled.show_message("LOG STOP", "Storage hard limit", log_file.split('/')[-1])
                            oled.tick(force=True)
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
