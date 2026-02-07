# main.py - Unified Datalogger Firmware for ESP32-S3 (Racesense V2)
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
PIN_BATTERY_ADC = 35 # VBAT-SENSE
PIN_DEBUG_LED = 2    # Blue Debug LED

def setup():
    print("\n--- ESP32-S3 RACESENSE V2 DATALOGGER ---")
    
    # 1. LED Manager
    led = LEDManager(PIN_LED_STATUS, count=16) # 16 LED Matrix
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
        # Use I2C 0 for S3 (SDA:21, SCL:39)
        i2c = machine.I2C(0, sda=machine.Pin(PIN_I2C_SDA), scl=machine.Pin(PIN_I2C_SCL), freq=400000)
        imu = BMI323(i2c, address=0x69)
        print("IMU: BMI323 Initialized Success")
    except Exception as e:
        print(f"IMU: Failed to initialize ({e})")

    # 7. GPS
    # S3 UART2 is flexible
    gps_uart = machine.UART(1, baudrate=9600, tx=machine.Pin(PIN_GPS_TX), rx=machine.Pin(PIN_GPS_RX), timeout=0)
    gps = GPS(gps_uart)
    print("GPS: Neo-M8N Initialized")

    # 8. Track Engine
    track_eng = TrackEngine()
    track_eng.load_track()

    # 9. BLE Provisioning
    import lib.wifi_manager as wm
    ble = BLEProvisioning(wifi_manager=wm, session_manager=sm)
    ble.start()

    # 10. WiFi
    print("Starting WiFi Radio...")
    mode, ip = connect_or_ap()
    print(f"WiFi Status: {mode}, IP: {ip}")
    
    ble.notify_wifi_status(mode=="STA", "", ip, mode)

    # 11. Start MiniServer (Second Core)
    server = MiniServer(sm, led=led, gps_state=gps, track_engine=track_eng)
    _thread.start_new_thread(server.start, ())
    print("Server: Listening in background (Core 1)")

    return led, gps, imu, sm, track_eng, mode, ble, vbat_adc

def main_loop():
    led, gps, imu, sm, track_eng, wifi_mode, ble, vbat_adc = setup()
    
    # Debug LED for AP Mode / Status
    onboard_led = machine.Pin(PIN_DEBUG_LED, machine.Pin.OUT)
    
    print("\n[System] Logging Active (Core 0)")
    log_file = sm.get_log_file()
    
    time_synced = False
    ble_update_tick = 0
    
    # State Machine Variables
    current_state = "LOGGING"
    calib_wait_start = 0
    calib_samples = []
    session_offset = {"x": 0.0, "y": 0.0, "z": 0.0}
    
    with open(log_file, 'w') as f:
        f.write("time,lat,lon,alt,speed,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z,vbat\n")
        
        while True:
            ble_update_tick += 1
            if ble_update_tick >= 20: # Every 2s
                ble_update_tick = 0
            
            # 1. Update GPS
            fix = gps.update()
            
            # 2. Battery Monitoring
            try:
                # 12-bit ADC (0-4095) -> 0-3.3V
                # Voltage divider 1:2 (100k/100k) -> Multiply by 2
                raw_v = vbat_adc.read()
                vbat = (raw_v / 4095.0) * 3.3 * 2.0
            except:
                vbat = 0.0

            # 3. BLE Status Update
            if ble_update_tick == 0:
                try:
                    s_info = sm.get_storage_info()
                    usage = (s_info['used_kb'] / s_info['total_kb']) * 100 if s_info else 0
                except:
                    usage = 0
                ble.update_device_info(gps_valid=fix['valid'], storage_pct=usage)
            
            # 4. Time Sync
            if not time_synced and fix['timestamp']:
                try:
                    t_str = fix['timestamp']
                    h, m, s = int(t_str[0:2]), int(t_str[2:4]), int(t_str[4:6])
                    machine.RTC().datetime((2026, 2, 7, 0, h, m, s, 0)) # Updated for current year
                    time_synced = True
                    print(f"[System] Time synced: {h}:{m}:{s}")
                    
                    # Rename log file
                    f.close()
                    new_log_file = sm.get_log_file()
                    os.rename(log_file, new_log_file)
                    log_file = new_log_file
                    f = open(log_file, 'a')
                except:
                    pass

            # 5. Read IMU
            acc = {"x":0.0, "y":0.0, "z":0.0}
            gyr = {"x":0.0, "y":0.0, "z":0.0}
            if imu:
                try:
                    data = imu.get_values()
                    acc, gyr = data["acc"], data["gyro"]
                except:
                    pass
            
            # 6. State Machine & Logging
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
                
                # Calibration Trigger
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
                if len(calib_samples) >= 30: # 3s at 10Hz
                    avg_x = sum(s[0] for s in calib_samples) / 30
                    avg_y = sum(s[1] for s in calib_samples) / 30
                    avg_z = sum(s[2] for s in calib_samples) / 30
                    session_offset = {"x": avg_x, "y": avg_y, "z": avg_z}
                    current_state = "PAUSED"
                    calib_wait_start = 0
                    led.show_calibrated()
                    print(f"[System] Calibrated! Offset: {session_offset}")

            # 7. Write to Log
            if fix['valid'] and current_state == "LOGGING":
                log_line = f"{time.time()},{fix['lat']},{fix['lon']},0.0,{fix['speed_kmh']:.2f},{acc['x']},{acc['y']},{acc['z']},{gyr['x']},{gyr['y']},{gyr['z']},{vbat:.2f}\n"
                f.write(log_line)
                f.flush()
                
                # Track Engine
                try:
                    event = track_eng.update(fix['lat'], fix['lon'], time.time())
                    if event:
                        led.trigger_event(event)
                except Exception as e:
                    print(f"TrackEng Error: {e}")

            # 8. LED Update
            base_state = current_state if fix['valid'] else "SEARCHING"
            
            # Storage Check (Priority)
            try:
                s_info = sm.get_storage_info()
                if s_info and (s_info['used_kb'] / s_info['total_kb']) > 0.95:
                    base_state = "STORAGE_CRITICAL"
            except:
                pass

            led.update_with_events(base_state)
            
            # 9. Status LED Blink
            if wifi_mode == "AP":
                onboard_led.value(not onboard_led.value()) 
            else:
                onboard_led.value(0)

            # 10Hz target
            time.sleep(0.1)
            
if __name__ == "__main__":
    try:
        main_loop()
    except Exception as e:
        print(f"CRITICAL SYSTEM ERROR: {e}")
        time.sleep(5)
        machine.reset()
