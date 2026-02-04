# main.py - Unified Datalogger Firmware
import machine
import time
import os
import gc
import _thread

# Drivers
from drivers.gps import GPS
from drivers.bmi323 import BMI323
from lib.session_manager import SessionManager
from lib.led_manager import LEDManager
from lib.track_engine import TrackEngine
from lib.wifi_manager import connect_or_ap
from lib.miniserver import MiniServer
from lib.ble_provisioning import BLEProvisioning

# --- MASTER PINOUT CONFIG ---
PIN_LED_STATUS = 4   # Feedback LED
PIN_GPS_RX = 27
PIN_GPS_TX = 26
PIN_I2C_SDA = 21
PIN_I2C_SCL = 22
PIN_SD_SCK = 18
PIN_SD_MOSI = 23
PIN_SD_MISO = 33
PIN_SD_CS = 5

def setup():
    print("\n--- ESP32 UNIFIED DATALOGGER ---")
    
    # 1. LED Manager
    led = LEDManager(PIN_LED_STATUS, count=16) # 16 LED Matrix
    led.animation_boot(500) 
    
    # 2. Power Stability Delay
    print("Stabilizing power...")
    time.sleep_ms(1000) # Crucial: Let level shifters and SD stabilize
    
    # 3. Mount SD Card (DO THIS BEFORE WIFI Sags the power)
    sd_mounted = False
    try:
        import drivers.sdcard
        miso = machine.Pin(PIN_SD_MISO, machine.Pin.IN, machine.Pin.PULL_UP)
        spi = machine.SPI(1, baudrate=400000, polarity=0, phase=0, 
                          sck=machine.Pin(PIN_SD_SCK), 
                          mosi=machine.Pin(PIN_SD_MOSI), 
                          miso=miso)
        sd = drivers.sdcard.SDCard(spi, machine.Pin(PIN_SD_CS))
        os.mount(sd, '/sd')
        print("Storage: SD CARD MOUNTED SUCCESS")
        sd_mounted = True
    except Exception as e:
        print(f"Storage: SD Mount Failed ({e}). Using Onboard Flash.")

    # 4. Session Manager
    sm = SessionManager(sd_mounted=sd_mounted)
    
    # 5. I2C Sensors (IMU)
    imu = None
    try:
        # Use I2C 1 and ensure pins are set
        i2c = machine.I2C(1, sda=machine.Pin(PIN_I2C_SDA), scl=machine.Pin(PIN_I2C_SCL))
        imu = BMI323(i2c, address=0x69)
        print("IMU: BMI323 Initialized Success")
    except Exception as e:
        print(f"IMU: Failed to initialize ({e})")

    # 6. GPS
    gps_uart = machine.UART(2, baudrate=9600, tx=machine.Pin(PIN_GPS_TX), rx=machine.Pin(PIN_GPS_RX), timeout=0)
    gps = GPS(gps_uart)
    print("GPS: Neo-M8N Initialized")

    # 7. Track Engine
    track_eng = TrackEngine()
    track_eng.load_track()

    # 8. BLE Provisioning (Start early)
    import lib.wifi_manager as wm
    ble = BLEProvisioning(wifi_manager=wm, session_manager=sm)
    ble.start()

    # 9. WiFi (DO THIS LAST - Power Hungry)
    print("Starting WiFi Radio...")
    mode, ip = connect_or_ap()
    print(f"WiFi Status: {mode}, IP: {ip}")
    
    # Update BLE status with initial WiFi state
    ble.notify_wifi_status(mode=="STA", "", ip, mode)

    # 10. Start MiniServer
    server = MiniServer(sm, led=led, track_engine=track_eng)
    _thread.start_new_thread(server.start, ())
    print("Server: Listening in background")

    return led, gps, imu, sm, track_eng, mode, ble

def main_loop():
    led, gps, imu, sm, track_eng, wifi_mode, ble = setup()
    
    # Onboard LED for AP Mode indication
    onboard_led = machine.Pin(2, machine.Pin.OUT)
    
    print("\n[System] Logging Active")
    log_file = sm.get_log_file()
    
    # Track time sync status
    time_synced = False
    # BLE update counter
    ble_update_tick = 0
    
    with open(log_file, 'w') as f:
        f.write("time,lat,lon,alt,speed,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z\n")
        
        while True:
            # Periodically update BLE (every 2 seconds / 20 ticks @ 10Hz)
            ble_update_tick += 1
            if ble_update_tick >= 20:
                ble_update_tick = 0
                try:
                    s_info = sm.get_storage_info()
                    usage = (s_info['used_kb'] / s_info['total_kb']) * 100 if s_info else 0
                    # We'll get fix['valid'] after gps.update()
                except:
                    usage = 0
            # 1. Update GPS (Blocking/Synchronous)
            fix = gps.update()
            
            # Update BLE with fix info (tick check above handled usage)
            if ble_update_tick == 0:
                ble.update_device_info(gps_valid=fix['valid'], storage_pct=usage)
            
            # Sync System Time from GPS (Once)
            if not time_synced and fix['timestamp']:
                try:
                    # Parse HHMMSS.SS
                    t_str = fix['timestamp']
                    h = int(t_str[0:2])
                    m = int(t_str[2:4])
                    s = int(t_str[4:6])
                    
                    # Set simple RTC (Date is unknown without RMC date field, assumes 2000-01-01)
                    machine.RTC().datetime((2024, 1, 1, 0, h, m, s, 0))
                    time_synced = True
                    print(f"[System] Time synced to GPS: {h}:{m}:{s}")
                    
                    # Rename the session file to match the correct time
                    try:
                        f.close() # Close to rename
                        
                        # New filename with valid timestamp (now synced)
                        new_log_file = sm.get_log_file() # timestamp is now correct
                        
                        import os
                        os.rename(log_file, new_log_file)
                        print(f"[System] Renamed session to: {new_log_file}")
                        
                        log_file = new_log_file
                        f = open(log_file, 'a') # Re-open in append mode
                    except Exception as e:
                        print(f"[System] Rename failed: {e}")
                        f = open(log_file, 'a') # Try to re-open old file at least
                except:
                    pass

            # 2. Read IMU (Immediately after GPS)
            # Default to 0.0 if sensor fails, but try every loop
            acc = {"x":0.0, "y":0.0, "z":0.0}
            gyr = {"x":0.0, "y":0.0, "z":0.0}
            
            if imu:
                try:
                    # Direct register read - No buffering
                    data = imu.get_values()
                    acc = data["acc"]
                    gyr = data.get("gyro", gyr)
                except Exception as e:
                    # Optional: print(f"IMU Fail: {e}")
                    pass
            
            # 3. Log Data (Synchronous Write)
            if fix['valid']:
                # CSV Format: time,lat,lon,alt,speed,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z
                log_line = f"{time.time()},{fix['lat']},{fix['lon']},0.0,{fix['speed_kmh']:.2f},{acc['x']:.0f},{acc['y']:.0f},{acc['z']:.0f},{gyr['x']:.0f},{gyr['y']:.0f},{gyr['z']:.0f}\n"
                f.write(log_line)
                f.flush() # Ensure data hits the card/flash immediately
                
                # Update Track Engine (Logic Layer)
                try:
                    event = track_eng.update(fix['lat'], fix['lon'], time.time())
                    if event:
                        # Trigger LED Event (Priority 2 & 3)
                        led.trigger_event(event)
                except Exception as e:
                    print(f"TrackEng Error: {e}")

            # 4. LED & Feedback Logic
            # Priority 0: Storage Full (>95%)
            base_state = "IDLE"
            
            # Check storage occasionally (e.g. every 10s? or just use cached if expensive?)
            # For simplicity, we assume SessionManager handles this cheaply or we do it rarely.
            # But os.statvfs is fast enough for 10Hz? Maybe. Let's do it simple first.
            # Optimization: Move out of loop or counter check if slow.
            # Using simple heuristic:
            
            if fix['valid']:
                base_state = "LOGGING"
            else:
                base_state = "SEARCHING"

            # Check Storage (Optimized: Check only every 100 frames / 10s)
            # Global or static var needed? Just do it every loop for safety if fast enough.
            # statvfs takes ~2ms. 10Hz budget is 100ms. It's fine.
            try:
                s_info = sm.get_storage_info()
                if s_info:
                    usage = (s_info['used_kb'] / s_info['total_kb']) * 100
                    if usage > 95:
                        base_state = "STORAGE_CRITICAL"
            except:
                pass

            # Update LED with Priority Logic
            try:
                led.update_with_events(base_state)
            except Exception as e:
                # LED failure should never stop logging
                pass
            
            # 5. AP Mode Blink (Rapid Blue/Onboard LED)
            if wifi_mode == "AP":
                onboard_led.value(not onboard_led.value()) # Toggle every loop (10Hz = 5Hz Blink)
            else:
                onboard_led.value(0) # Off in STA mode

            # Maintain frequency
            time.sleep(0.1) # 10Hz target
            
if __name__ == "__main__":
    try:
        main_loop()
    except Exception as e:
        print(f"CRITICAL SYSTEM ERROR: {e}")
        time.sleep(5)
        machine.reset()
