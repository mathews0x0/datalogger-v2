# main.py - Unified Datalogger Firmware for ESP32-S3 (Racesense V2)
import machine
import time
import os
import gc
import _thread

# --- SAFE BOOT WINDOW ---
print("=== SAFE BOOT WINDOW ===")
print("You have 5 seconds to press Ctrl-C via mpremote to halt the logger.")
for i in range(5, 0, -1):
    print(f"Booting in {i}...")
    time.sleep(1)
print("=== BOOTING ===")

# Drivers
from drivers.gps import GPS
from drivers.bmi270 import BMI270
from lib.session_manager import SessionManager
from lib.led_manager import LEDManager
from lib.track_engine import TrackEngine

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
PIN_BATTERY_ADC = 8     # VBAT-SENSE
PIN_DEBUG_LED = 2       # Blue Debug LED

# --- IMU SENSITIVITY CONSTANTS (BMI270 at ±4g / ±2000dps) ---
ACC_SENSITIVITY = 8192.0   # LSB/g (2^15 / 4)
GYR_SENSITIVITY = 16.4     # LSB/dps (2^15 / 2000)

def setup():
    print("\n--- ESP32-S3 RACESENSE V2 DATALOGGER ---")
    
    # 1. LED Manager (Dual NeoPixel: IO4 feedback + IO6 onboard)
    led = LEDManager(pin=PIN_LED_FEEDBACK, count=16, onboard_neo_pin=PIN_LED_ONBOARD, onboard_led_pin=PIN_DEBUG_LED)
    led.animation_boot()  # 3 blue pulses
    
    # 2. Power Stability Delay
    print("Stabilizing power...")
    time.sleep_ms(1000)
    
    # 3. Battery Monitor
    vbat_adc = machine.ADC(machine.Pin(PIN_BATTERY_ADC))
    vbat_adc.atten(machine.ADC.ATTN_11DB)

    # 4. Mount SD Card (Native ESP32 SD driver — proven working in full_system_test.py)
    sd_mounted = False
    try:
        sd = machine.SDCard(slot=2, width=1, sck=machine.Pin(PIN_SD_SCK), mosi=machine.Pin(PIN_SD_MOSI), miso=machine.Pin(PIN_SD_MISO), cs=machine.Pin(PIN_SD_CS))
        os.mount(sd, '/sd')
        print("Storage: SD CARD MOUNTED SUCCESS")
        sd_mounted = True
    except Exception as e:
        print(f"Storage: SD Mount Failed ({e}). Using Onboard Flash.")

    # 5. Session Manager
    sm = SessionManager(sd_mounted=sd_mounted)
    
    # 6. I2C Sensors (IMU)
    imu = None
    try:
        i2c = machine.I2C(0, sda=machine.Pin(PIN_I2C_SDA), scl=machine.Pin(PIN_I2C_SCL), freq=400000)
        imu = BMI270(i2c, address=0x69)
        print("IMU: BMI270 Initialized Success")
    except Exception as e:
        print(f"IMU: Failed to initialize ({e})")

    # 7. GPS — Must start at 9600 (module default on power-up), then shift to 115200
    gps_uart = machine.UART(1, baudrate=9600, tx=machine.Pin(PIN_GPS_TX), rx=machine.Pin(PIN_GPS_RX), timeout=0, rxbuf=2048)
    gps = GPS(gps_uart)
    print("GPS: Neo-M8N — Shifting from 9600 → 115200 baud...")
    gps.set_baudrate(115200)
    time.sleep_ms(100)
    gps_uart.init(baudrate=115200, tx=machine.Pin(PIN_GPS_TX), rx=machine.Pin(PIN_GPS_RX), timeout=0, rxbuf=2048)
    gps.set_rate(10)
    print("GPS: Neo-M8N Ready at 115200 baud / 10Hz (2KB Buffer)")

    # 8. Track Engine
    track_eng = TrackEngine()
    track_eng.load_track()

    # 9. Watchdog Timer (8 second timeout)
    wdt = machine.WDT(timeout=8000)

    return led, gps, imu, sm, track_eng, vbat_adc, wdt, sd_mounted

def main():
    led, gps, imu, sm, track_eng, vbat_adc, wdt, sd_mounted = setup()
    
    # --- Sync Button (IO5) ---
    sync_btn = machine.Pin(PIN_BUTTON_SYNC, machine.Pin.IN, machine.Pin.PULL_UP)
    
    # --- FIRST-TIME SETUP CHECK ---
    # If no WiFi credentials exist, skip button check and go straight to pairing
    from lib.wifi_manager import load_device_config
    config = load_device_config()
    if not config.get('ssid'):
        print("\n[System] No WiFi configured — First-time setup! Entering Pairing Mode.")
        run_sync_mode(led, sm, sync_btn, wdt)
        return  # Never reaches here (sync mode loops forever)
    
    # --- 10-SECOND DECISION WINDOW ---
    print("\n[System] 10s Decision Window — Press SYNC button to enter Sync Mode")
    sync_requested = False
    start = time.ticks_ms()
    
    while time.ticks_diff(time.ticks_ms(), start) < 10000:
        wdt.feed()
        led.animation_decision_tick(sd_mounted)
        
        # Check button (active LOW — pressed when value() == 0)
        if sync_btn.value() == 0:
            sync_requested = True
            print("[System] SYNC button pressed! Entering Sync Mode.")
            break
        
        time.sleep_ms(50)

    wdt.feed()
    
    # --- MODE SELECTION ---
    if sync_requested:
        print("\n[System] ==> SYNC MODE")
        run_sync_mode(led, sm, sync_btn, wdt)
    else:
        print("\n[System] ==> LOGGING MODE")
        # Kill all radios immediately
        from lib.wifi_manager import stop_wifi
        stop_wifi()
        logging_loop(led, gps, imu, sm, track_eng, vbat_adc, wdt)


# ==================================================================
# SYNC MODE — WiFi upload / Pairing. No logging.
# ==================================================================

def run_sync_mode(led, sm, sync_btn, wdt):
    """
    Exclusive sync mode. No telemetry logging occurs.
    
    Flow:
    1. Search for known WiFi (purple fade).
    2. If found: upload pending files (green blink → green fade on success).
    3. Stay in sync mode after completion.
    4. Long press (>3s) on sync button → enter Pairing mode (blue breathing).
    """
    from lib.wifi_manager import load_device_config, stop_wifi
    import network
    
    config = load_device_config()
    wifi_connected = False
    needs_setup = not config.get('ssid')
    
    if needs_setup:
        # No saved network — auto-enter pairing mode with rainbow animation
        print("[Sync] No WiFi credentials. Starting Pairing Mode automatically...")
        from lib.captive_portal import start_background_portal
        _thread.start_new_thread(start_background_portal, (led,))
        
        # Stay in rainbow loop — portal runs in background
        while True:
            wdt.feed()
            led.update_sync("SETUP_NEEDED")
            time.sleep_ms(50)
    
    elif config.get('ssid'):
        # --- Phase 1: Try connecting to known WiFi ---
        print(f"[Sync] Searching for WiFi: {config['ssid']}")
        led.update_sync("SYNC_SEARCHING")
        
        sta = network.WLAN(network.STA_IF)
        sta.active(True)
        sta.connect(config['ssid'], config.get('password', ''))
        
        # Wait up to 30s for connection
        for i in range(300):
            wdt.feed()
            led.update_sync("SYNC_SEARCHING")
            
            if sta.isconnected():
                wifi_connected = True
                print(f"[Sync] WiFi Connected! IP: {sta.ifconfig()[0]}")
                led.update_sync("SYNC_FOUND")
                time.sleep(1)  # Brief visual confirmation
                break
            
            time.sleep_ms(100)
        
        if not wifi_connected:
            print("[Sync] WiFi connection failed.")
            sta.active(False)
    
    # --- Phase 2: Upload if connected ---
    if wifi_connected:
        pending = sm.list_sessions()
        if pending:
            print(f"[Sync] Uploading {len(pending)} file(s)...")
            led.update_sync("SYNC_UPLOADING")
            
            from lib.uploader import sync_all
            wdt.feed()
            success = sync_all(sm, led, wdt)
            
            if success:
                print("[Sync] Upload Complete!")
                # Show success for 5 seconds
                end = time.ticks_ms() + 5000
                while time.ticks_diff(time.ticks_ms(), end) < 0:
                    wdt.feed()
                    led.update_sync("SYNC_OK")
                    time.sleep_ms(50)
            else:
                print("[Sync] Upload had issues.")
                end = time.ticks_ms() + 5000
                while time.ticks_diff(time.ticks_ms(), end) < 0:
                    wdt.feed()
                    led.update_sync("SYNC_FAIL")
                    time.sleep_ms(50)
        else:
            print("[Sync] No pending files to upload.")
            # Show OK since there's nothing to do
            end = time.ticks_ms() + 3000
            while time.ticks_diff(time.ticks_ms(), end) < 0:
                wdt.feed()
                led.update_sync("SYNC_OK")
                time.sleep_ms(50)
    
    # --- Phase 3: Stay in sync idle loop ---
    # Long press (>3s) on sync button → Pairing mode
    print("[Sync] Idle. Hold SYNC button for 3s to enter Pairing mode.")
    
    press_start = 0
    pairing_active = False
    
    while True:
        wdt.feed()
        
        if pairing_active:
            led.update_sync("PAIRING")
            time.sleep_ms(50)
            continue
        
        # Show current status
        if needs_setup:
            led.update_sync("SETUP_NEEDED")
        elif wifi_connected:
            led.update_sync("SYNC_OK")
        else:
            led.update_sync("SYNC_FAIL")
        
        # Long press detection for pairing
        if sync_btn.value() == 0:  # Button pressed
            if press_start == 0:
                press_start = time.ticks_ms()
            elif time.ticks_diff(time.ticks_ms(), press_start) > 3000:
                print("[Sync] Long press detected! Entering Pairing Mode...")
                stop_wifi()
                time.sleep_ms(200)
                
                from lib.captive_portal import start_background_portal
                _thread.start_new_thread(start_background_portal, (led,))
                pairing_active = True
                press_start = 0
        else:
            press_start = 0
        
        time.sleep_ms(50)


# ==================================================================
# LOGGING MODE — Pure telemetry capture. No radio.
# ==================================================================

def logging_loop(led, gps, imu, sm, track_eng, vbat_adc, wdt):
    """
    Dual-rate logging loop:
      - IMU sampled at 100 Hz (every tick)
      - GPS sampled at  10 Hz (every 10th tick)
      - Buffered writes flushed every 20 rows (~200ms)
    """
    
    loop_count = 0
    FLUSH_INTERVAL = 20  # rows before flushing to SD
    
    print("\n[System] Logging Active — 100Hz IMU / 10Hz GPS — All radios OFF")
    log_file = sm.get_log_file()
    print(f"[System] Session file: {log_file}")
    
    # RTC sync flag
    rtc_synced = False
    
    # Write buffer for batched SD writes
    write_buf = []
    
    # Cached values
    vbat = 0.0
    fix = {'valid': False, 'lat': None, 'lon': None, 'altitude': 0.0,
           'speed_kmh': 0.0, 'satellites': 0, 'timestamp': None, 'date': None}
    base_state = "SEARCHING"
    
    try:
        f = open(log_file, 'w')
        f.write("tick_ms,row_type,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,lat,lon,alt,speed,sats,vbat\n")
        f.flush()
        print(f"[System] Log file opened: {log_file}")
    except Exception as e:
        print(f"[System] FAILED to open log file: {e}")
        f = None
    
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
                data = imu.get_values()
                acc_x = data["acc"]["x"] / ACC_SENSITIVITY
                acc_y = data["acc"]["y"] / ACC_SENSITIVITY
                acc_z = data["acc"]["z"] / ACC_SENSITIVITY
                gyr_x = data["gyro"]["x"] / GYR_SENSITIVITY
                gyr_y = data["gyro"]["y"] / GYR_SENSITIVITY
                gyr_z = data["gyro"]["z"] / GYR_SENSITIVITY
            except:
                pass
        
        # Write IMU row (row_type = I, GPS fields empty)
        if f:
            write_buf.append(f"{tick_ms},I,{acc_x:.4f},{acc_y:.4f},{acc_z:.4f},{gyr_x:.2f},{gyr_y:.2f},{gyr_z:.2f},,,,,,\n")
        
        # ── 2. GPS READ (every 10th tick = 10 Hz) ──
        if loop_count % 10 == 0:
            fix = gps.update()
            
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
                    machine.RTC().datetime((year, month, day, 0, hour, minute, second, 0))
                    rtc_synced = True
                    print(f"[System] RTC Synced to GPS: {year}-{month}-{day} {hour}:{minute}:{second}")
                except:
                    pass
            
            # Write GPS row if we have a fresh valid fix
            if f and fix['valid'] and gps.new_fix:
                write_buf.append(f"{tick_ms},G,{acc_x:.4f},{acc_y:.4f},{acc_z:.4f},{gyr_x:.2f},{gyr_y:.2f},{gyr_z:.2f}," +
                                 f"{fix['lat']:.15g},{fix['lon']:.15g},{fix['altitude']:.1f},{fix['speed_kmh']:.2f},{fix['satellites']},{vbat:.2f}\n")
                
                # Track Engine (only on GPS rows)
                try:
                    event = track_eng.update(fix['lat'], fix['lon'], float(tick_ms))
                    if event:
                        led.trigger_event(event)
                except Exception as e:
                    if loop_count % 100 == 0:
                        print(f"TrackEng Error: {e}")
            
            # LED update (on GPS ticks)
            base_state = "LOGGING" if fix['valid'] else "SEARCHING"
            led.update_with_events(base_state)
            
            # Debug output (every ~1s = every 10 GPS ticks)
            if loop_count % 100 == 0:
                print(f"[DBG] valid={fix['valid']} lat={fix['lat']} lon={fix['lon']} sats={fix['satellites']} buf={len(write_buf)}")
        
        # ── 3. FLUSH WRITE BUFFER ──
        if f and len(write_buf) >= FLUSH_INTERVAL:
            f.write(''.join(write_buf))
            f.flush()
            write_buf.clear()
        
        # ── 4. BATTERY (every 100th tick = ~1 Hz) ──
        if loop_count % 100 == 0:
            try:
                raw_v = vbat_adc.read()
                vbat = (raw_v / 4095.0) * 3.3 * 2.0
            except:
                vbat = 0.0
        
        # ── 5. STORAGE CHECK (every 1000th tick = ~10s) ──
        if loop_count % 1000 == 0:
            try:
                s_info = sm.get_active_storage_info()
                if s_info and s_info['total_kb'] > 0:
                    usage = s_info['used_kb'] / s_info['total_kb']
                    if usage > 0.95:
                        base_state = "STORAGE_CRITICAL"
                        print(f"[System] STORAGE CRITICAL: {s_info['used_kb']}/{s_info['total_kb']} KB")
            except:
                pass
        
        # ── 6. PERIODIC MAINTENANCE ──
        if loop_count % 100 == 0:
            try:
                os.sync()
            except:
                pass
        
        if loop_count % 1000 == 0:
            gc.collect()
            print(f"[Loop] State: {base_state} | Fix: {fix.get('valid')} | Loops: {loop_count}")

        # ── 7. TIMING — Target 10ms per tick (100 Hz) ──
        elapsed_ms = time.ticks_diff(time.ticks_ms(), tick_start)
        remaining = 10 - elapsed_ms
        if remaining > 0:
            time.sleep_ms(remaining)
            
if __name__ == "__main__":
    try:
        main()
    except Exception as e: 
        import sys
        print(f"CRITICAL SYSTEM ERROR: {e}")
        try:
            with open('/crash.log', 'w') as f:
                sys.print_exception(e, f)
        except:
            pass
        time.sleep(5)
        machine.reset()
