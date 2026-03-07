# main.py - Unified Datalogger Firmware for ESP32-S3 (Racesense V2)
import machine
import time
import os
import gc
import network
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
PIN_LED_STATUS = 4   # Neopixel LED_DATA
PIN_GPS_RX = 18
PIN_GPS_TX = 17
PIN_I2C_SDA = 21
PIN_I2C_SCL = 39
PIN_SD_SCK = 12
PIN_SD_MOSI = 11
PIN_SD_MISO = 13
PIN_SD_CS = 10
PIN_SD_CD = 3        # Card Detect
PIN_BATTERY_ADC = 8  # VBAT-SENSE (Updated for S3 ADC1)
PIN_DEBUG_LED = 2    # Blue Debug LED

# --- IMU SENSITIVITY CONSTANTS (BMI270 at ±4g / ±2000dps) ---
ACC_SENSITIVITY = 8192.0   # LSB/g (2^15 / 4)
GYR_SENSITIVITY = 16.4     # LSB/dps (2^15 / 2000)

def setup():
    print("\n--- ESP32-S3 RACESENSE V2 DATALOGGER ---")
    
    # 1. LED Manager (NeoPixel — stays off until logging loop)
    led = LEDManager(PIN_LED_STATUS, count=16)
    led.animation_boot(500) 
    
    # 2. Power Stability Delay
    print("Stabilizing power...")
    time.sleep_ms(1000)
    
    # 3. Battery Monitor
    vbat_adc = machine.ADC(machine.Pin(PIN_BATTERY_ADC))
    vbat_adc.atten(machine.ADC.ATTN_11DB) # 0-3.3V range (for 0-6.6V battery)

    # 4. Mount SD Card
    sd_mounted = False
    try:
        import drivers.sdcard
        miso = machine.Pin(PIN_SD_MISO, machine.Pin.IN, machine.Pin.PULL_UP)
        spi = machine.SPI(1, baudrate=10000000, polarity=0, phase=0, 
                          sck=machine.Pin(PIN_SD_SCK), 
                          mosi=machine.Pin(PIN_SD_MOSI), 
                          miso=miso)
        sd = drivers.sdcard.SDCard(spi, machine.Pin(PIN_SD_CS))
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

    # 7. GPS (2KB RX buffer to prevent overflows during flash writes)
    gps_uart = machine.UART(1, baudrate=115200, tx=machine.Pin(PIN_GPS_TX), rx=machine.Pin(PIN_GPS_RX), timeout=0, rxbuf=2048)
    gps = GPS(gps_uart)
    print("GPS: Neo-M8N Initialized at 115200 baud (2KB Buffer)")

    # 8. Track Engine
    track_eng = TrackEngine()
    track_eng.load_track()

    # 9. Watchdog Timer (8 second timeout — resets device if loop hangs)
    wdt = machine.WDT(timeout=8000)

    return led, gps, imu, sm, track_eng, vbat_adc, wdt

def main():
    led, gps, imu, sm, track_eng, vbat_adc, wdt = setup()
    
    # IO2 debug LED for pre-logging status
    debug_led = machine.Pin(PIN_DEBUG_LED, machine.Pin.OUT)
    
    # --- PHASE 1: 30s SYNC WINDOW ---
    # IO2 LED active here — NeoPixel is off
    print("\n[System] Phase 1: 30s Sync/Setup Window")
    start_boot = time.ticks_ms()
    wifi_connected = False
    
    # Load config once, connect once (L5 optimization)
    from lib.wifi_manager import load_device_config
    config = load_device_config()
    
    sta = None
    if config.get('ssid'):
        sta = network.WLAN(network.STA_IF)
        sta.active(True)
        sta.connect(config['ssid'], config.get('password', ''))
    else:
        print("[System] No WiFi credentials.")
    
    # Wait loop — only poll status, IO2 blinks
    while config.get('ssid') and time.ticks_diff(time.ticks_ms(), start_boot) < 30000:
        wdt.feed()
        elapsed = time.ticks_diff(time.ticks_ms(), start_boot) // 1000
        
        # IO2 blink: connecting pattern
        led.update_onboard_led("CONNECTING")
        
        # Movement check: if racing, skip all networking
        fix = gps.update()
        if fix['valid'] and fix['speed_kmh'] > 10.0:
            print("[System] Movement detected! Switching to LOGGER role immediately.")
            wifi_connected = False
            break

        if sta and sta.isconnected():
            print(f"[System] WiFi Connected (took {elapsed}s)")
            wifi_connected = True
            led.update_onboard_led("CONNECTED")
            break
        
        time.sleep(1)
        print(f"Waiting for WiFi... {30 - elapsed}s left")

    # --- PHASE 2: ROLE DECISION ---
    wdt.feed()
    pending_files = sm.list_sessions()
    
    # Final stationary check
    fix = gps.update()
    is_stationary = not (fix['valid'] and fix['speed_kmh'] > 10.0)
    
    if wifi_connected and pending_files and is_stationary:
        print("\n[System] ROLE: UPLOADER (Exclusive)")
        led.update_onboard_led("CONNECTED")
        from lib.uploader import sync_all
        wdt.feed()
        success = sync_all(sm, led)
        if success:
            print("[System] Sync Complete. Rebooting for Logging Mode...")
            time.sleep(2)
            machine.reset()
        else:
            print("[System] Sync issues. Proceeding to Logging Mode anyway.")

    # --- PHASE 3: LOGGING MODE (Exclusive) ---
    print("\n[System] ROLE: LOGGER (Exclusive focus)")
    
    if is_stationary and not wifi_connected:
        print("[System] Entering 1-min Pairing Window...")
        # IO2 shows pairing status during this window
        led.update_onboard_led("PAIRING")
        from lib.captive_portal import start_background_portal
        _thread.start_new_thread(start_background_portal, (led,))
    else:
        # Kill WiFi to save power and eliminate thread jitter
        from lib.wifi_manager import stop_wifi
        stop_wifi()
    
    # IO2 OFF from here — NeoPixel takes over
    debug_led.value(0)
    
    logging_loop(led, gps, imu, sm, track_eng, vbat_adc, wdt)

def logging_loop(led, gps, imu, sm, track_eng, vbat_adc, wdt):
    
    wifi_radio_active = True
    loop_count = 0
    
    print("\n[System] Logging Active (Core 0) — NeoPixel active, IO2 off")
    log_file = sm.get_log_file()
    print(f"[System] Session file: {log_file}")
    
    # State Machine Variables
    current_state = "LOGGING"
    calib_wait_start = 0
    calib_samples = []
    session_offset = {"x": 0.0, "y": 0.0, "z": 0.0}
    gravity_axis = "z" # Default
    
    # Internal high-res timing for GPS interpolation
    rtc_synced = False
    
    with open(log_file, 'w') as f:
        f.write("gps_time,lat,lon,alt,speed,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,vbat\n")
        
        while True:
            # Consistent 10Hz timing (L3)
            tick_start = time.ticks_ms()
            
            wdt.feed()
            
            # 1. Update GPS
            fix = gps.update()
            
            # --- RADIO SAFETY SHIELD ---
            if wifi_radio_active and fix['valid'] and fix['speed_kmh'] > 10.0:
                print("[System] Speed > 10km/h - Enforcing Silent Mode")
                from lib.wifi_manager import stop_wifi
                stop_wifi()
                wifi_radio_active = False

            # 2. Battery Monitoring
            try:
                raw_v = vbat_adc.read()
                vbat = (raw_v / 4095.0) * 3.3 * 2.0
            except:
                vbat = 0.0
            
            # 3. Read IMU — scale to physical units (H4)
            acc = {"x": 0.0, "y": 0.0, "z": 0.0}
            gyr = {"x": 0.0, "y": 0.0, "z": 0.0}
            if imu:
                try:
                    data = imu.get_values()
                    # Scale raw counts to g's and dps
                    acc = {
                        "x": data["acc"]["x"] / ACC_SENSITIVITY,
                        "y": data["acc"]["y"] / ACC_SENSITIVITY,
                        "z": data["acc"]["z"] / ACC_SENSITIVITY
                    }
                    gyr = {
                        "x": data["gyro"]["x"] / GYR_SENSITIVITY,
                        "y": data["gyro"]["y"] / GYR_SENSITIVITY,
                        "z": data["gyro"]["z"] / GYR_SENSITIVITY
                    }
                except:
                    pass
            
            # 4. State Machine & Logging
            in_pit = False
            if fix['valid']:
                in_pit = track_eng.is_in_pit(fix['lat'], fix['lon'])
            
            # State Transitions
            if current_state == "LOGGING":
                if in_pit:
                    current_state = "PAUSED"
                    print("[System] Entering Pit - PAUSED")
            
            elif current_state == "PAUSED":
                if not in_pit and fix['speed_kmh'] > 10:
                    current_state = "LOGGING"
                    print("[System] Exiting Pit - LOGGING")
                
                # Calibration Trigger — now uses g's (H4 fix)
                upright = abs(acc['z']) > 0.8 and abs(acc['x']) < 0.3 and abs(acc['y']) < 0.3
                if fix['valid'] and fix['speed_kmh'] < 2.0 and upright:
                    if calib_wait_start == 0:
                        calib_wait_start = time.ticks_ms()
                    elif time.ticks_diff(time.ticks_ms(), calib_wait_start) > 10000:
                        current_state = "CALIBRATING"
                        calib_samples = []
                        print("[System] Starting IMU Calibration...")
                else:
                    calib_wait_start = 0
            
            elif current_state == "CALIBRATING":
                calib_samples.append((acc['x'], acc['y'], acc['z']))
                if len(calib_samples) >= 30:  # 3s at 10Hz
                    avg_x = sum(s[0] for s in calib_samples) / 30
                    avg_y = sum(s[1] for s in calib_samples) / 30
                    avg_z = sum(s[2] for s in calib_samples) / 30
                    
                    # Auto-detect orientation (which axis is pointing at earth?)
                    m = {"x": abs(avg_x), "y": abs(avg_y), "z": abs(avg_z)}
                    gravity_axis = max(m, key=m.get)
                    
                    session_offset = {"x": avg_x, "y": avg_y, "z": avg_z}
                    # Subtract 1g (gravity) from the detected primary axis
                    if avg_z > 0.8: session_offset["z"] -= 1.0  # Flat
                    elif avg_z < -0.8: session_offset["z"] += 1.0 # Upside down
                    elif avg_x > 0.8: session_offset["x"] -= 1.0 # Sideways
                    elif avg_x < -0.8: session_offset["x"] += 1.0
                    elif avg_y > 0.8: session_offset["y"] -= 1.0 # Front/Back
                    elif avg_y < -0.8: session_offset["y"] += 1.0
                    
                    current_state = "PAUSED"
                    calib_wait_start = 0
                    led.show_calibrated()
                    print(f"[System] Calibrated ({gravity_axis}-axis gravity)! Offset: {session_offset}")

                # 1. Sync System RTC to GPS time once
            if not rtc_synced and fix.get('valid'):
                try:
                    # Simple UTC-to-Epoch conversion (MicroPython 2000-based)
                    # We use machine.RTC().datetime() for stability
                    d = fix['date'] # ddmmyy
                    t = fix['timestamp'] # hhmmss.ss
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

            # 5. Write to Log (apply calibration offset)
            if fix['valid'] and current_state == "LOGGING":
                # High-res Timestamp (Unix-style float)
                # ESP32 MicroPython epoch is 2000-01-01. Add offset for 1970 epoch.
                t_now = time.time() + 946684800
                ms = time.ticks_ms() % 1000
                gps_ts = f"{t_now}.{ms:03d}00" # 5 decimal places as requested
                
                # Apply calibration offsets
                cal_ax = acc['x'] - session_offset['x']
                cal_ay = acc['y'] - session_offset['y']
                cal_az = acc['z'] - session_offset['z']
                
                log_line = f"{gps_ts},{fix['lat']},{fix['lon']},{fix['altitude']:.1f},{fix['speed_kmh']:.2f},{cal_ax:.4f},{cal_ay:.4f},{cal_az:.4f},{gyr['x']:.2f},{gyr['y']:.2f},{gyr['z']:.2f},{vbat:.2f}\n"
                f.write(log_line)
                f.flush()
                
                # Track Engine (Uses precise float)
                try:
                    ts_float = float(gps_ts)
                    event = track_eng.update(fix['lat'], fix['lon'], ts_float)
                    if event:
                        led.trigger_event(event)
                except Exception as e:
                    print(f"TrackEng Error: {e}")

            # 6. NeoPixel LED Update (active during logging loop)
            base_state = current_state if fix['valid'] else "SEARCHING"
            
            # Storage Check
            try:
                s_info = sm.get_active_storage_info()
                if s_info and s_info['total_kb'] > 0:
                    if (s_info['used_kb'] / s_info['total_kb']) > 0.95:
                        base_state = "STORAGE_CRITICAL"
            except:
                pass

            led.update_with_events(base_state)
            
            # 7. Periodic maintenance
            loop_count += 1
            
            # os.sync() every ~1 second for data safety (H1)
            if loop_count % 10 == 0:
                try:
                    os.sync()
                except:
                    pass
            
            # GC every ~10 seconds (L1)
            if loop_count % 100 == 0:
                gc.collect()
            
            # Heartbeat log every ~10 seconds
            if loop_count % 100 == 0:
                print(f"[Loop] State: {base_state} | Fix: {fix.get('valid')} | Loops: {loop_count}")

            # Consistent 10Hz timing (L3)
            elapsed_ms = time.ticks_diff(time.ticks_ms(), tick_start)
            remaining = 100 - elapsed_ms
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
