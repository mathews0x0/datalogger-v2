# main.py - Datalogger Firmware (Onboard Flash Storage)
import machine
import time
import os
import sys
import gc
import _thread

# Drivers
from drivers.gps import GPS
from lib.session_manager import SessionManager
from lib.led_manager import LEDManager
from lib.track_engine import TrackEngine

# --- CONFIG ---
PIN_LED_STATUS = 2   # Blue LED
PIN_GPS_RX = 26
PIN_GPS_TX = 27
BAUD_GPS = 9600

# Globals
led = machine.Pin(PIN_LED_STATUS, machine.Pin.OUT)

def blink(n, speed=0.1):
    for _ in range(n):
        led.value(1)
        time.sleep(speed)
        led.value(0)
        time.sleep(speed)

def setup():
    print("--- ESP32 DATALOGGER BOOT ---")
    print("Storage: ONBOARD FLASH (No SD Card)")
    
    # 1. Session Manager (Manages onboard flash storage)
    sm = SessionManager()
    print(f"Session storage ready: {sm.internal_dir}")
    blink(3, 0.05)  # Fast blink success

    # 2. Track Engine (Load saved track if exists)
    track_eng = TrackEngine()
    if track_eng.load_track():
        print(f"Track Loaded: {track_eng.track.get('name', 'Unknown')}")
    else:
        print("No track loaded (use app to push track data)")

    # 3. WiFi Connection (Multi-network support)
    from lib import wifi_manager, miniserver
    mode, ip = wifi_manager.connect_or_ap()
    
    # 4. Start Web Server (with track engine)
    server = miniserver.MiniServer(sm, led, gps_state=gps_state, track_engine=track_eng)
    try:
        server.start(80)
        print(f"Web server running on http://{ip}")
    except Exception as e:
        print(f"Server Start Failed: {e}")
        time.sleep(5)
        machine.reset()

    # 4. GPS Setup & Configuration (10Hz Performance Mode)
    print("Configuring GPS (Neo-M8N)...")
    
    # 5. LED Manager (NeoPixel)
    led_np = LEDManager(pin=4, count=8)
    led_np.animation_boot()
    
    # Switch to 115200 Handshake
    uart = machine.UART(2, baudrate=9600, rx=PIN_GPS_RX, tx=PIN_GPS_TX, timeout=50)
    gps = GPS(uart)
    
    print("  -> Setting Baud: 115200")
    gps.set_baudrate(115200)
    time.sleep(0.5)
    # rxbuf=2048 allows the ESP32 to buffer GPS data during slow Flash writes
    # timeout=0 ensures non-blocking operation
    uart.init(baudrate=115200, rxbuf=2048, timeout=0)
    
    # Request 10Hz
    print("  -> Setting Rate: 10Hz")
    gps.set_rate(10)
    time.sleep(0.2)
    
    print("GPS Performance Mode Active.")
    
    return gps, sm, server, led_np, track_eng

# Shared State
gps_state = {
    'valid': False,
    'timestamp': None,
    'satellites': 0,
    'speed_kmh': 0.0,
    'lat': None,
    'lon': None,
    'logging_active': True,
    'storage_pct': 0,
    'track_event': None  # Pending track/sector event for LED
}

def logging_thread(gps, sm, track_eng):
    """
    DEDICATED LOGGING THREAD (Runs on Core 1)
    Handles GPS ingestion, Flash writing, and Track Engine updates.
    """
    print("[Core 1] Logging Thread Started")
    
    file_open = False
    f = None
    last_flush = time.ticks_ms()
    last_timestamp = None
    last_storage_check = 0
    
    while gps_state['logging_active']:
        now = time.ticks_ms()
        
        # Periodic Storage Check (Every 5 seconds)
        if time.ticks_diff(now, last_storage_check) > 5000:
            try:
                stat = os.statvfs('/')
                free = stat[0] * stat[3]
                total = stat[0] * stat[2]
                gps_state['storage_pct'] = int(((total - free) * 100) / total)
                last_storage_check = now
                
                # Safety Stop
                if gps_state['storage_pct'] >= 95:
                    print(f"[Core 1] STORAGE FULL ({gps_state['storage_pct']}%). Halting.")
                    gps_state['logging_active'] = False
                    break
            except:
                pass

        # Update GPS
        fix = gps.update()
        
        # Update shared state for Core 0
        gps_state['valid'] = fix['valid']
        gps_state['timestamp'] = fix['timestamp']
        gps_state['satellites'] = fix['satellites']
        gps_state['speed_kmh'] = fix['speed_kmh']
        gps_state['lat'] = fix['lat']
        gps_state['lon'] = fix['lon']

        # Track Engine Update (if we have valid GPS)
        if fix['valid'] and fix['lat'] and fix['lon']:
            # Use monotonic time for sector timing
            mono_ts = now / 1000.0
            event = track_eng.update(fix['lat'], fix['lon'], mono_ts)
            if event:
                gps_state['track_event'] = event  # Signal to Core 0 for LED

        # 1. Wait for Satellite Lock before creating/opening file
        if not file_open and fix['valid'] and gps_state['logging_active']:
            fpath = sm.get_log_file()
            print(f"[Core 1] GPS Fixed. Opening log: {fpath}")
            try:
                f = open(fpath, 'w')
                f.write("timestamp,lat,lon,speed_kmh,sats,alt,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z\n")
                f.flush()
                file_open = True
            except Exception as e:
                print(f"[Core 1] File Create Error: {e}")
                gps_state['logging_active'] = False # Kill logging on error
                break

        # Log Data (Only if we have a NEW timestamp and file is open)
        current_ts = fix.get('timestamp')
        if file_open and current_ts and current_ts != last_timestamp:
            last_timestamp = current_ts
            try:
                # Dummy IMU Data (Prep for physical sensor)
                # acc in m/s^2, gyro in deg/s
                ax, ay, az = 1.234567, -0.456789, 9.806650
                gx, gy, gz = 0.123456, -0.789012, 0.456789
                
                # Format CSV line
                lat = f"{fix['lat']:.6f}" if fix['lat'] else ""
                lon = f"{fix['lon']:.6f}" if fix['lon'] else ""
                
                # Full Schema: ts,lat,lon,speed,sats,alt,ax,ay,az,gx,gy,gz
                line = f"{current_ts},{lat},{lon},{fix['speed_kmh']:.2f},{fix['satellites']},0,"
                line += f"{ax:.6f},{ay:.6f},{az:.6f},{gx:.6f},{gy:.6f},{gz:.6f}\n"
                
                f.write(line)
                
                # Flush every 2 seconds
                now = time.ticks_ms()
                if time.ticks_diff(now, last_flush) > 2000:
                    f.flush()
                    last_flush = now
            except Exception as e:
                print(f"[Core 1] Log Error: {e}")
        
        # Core 1 yields slightly
        time.sleep(0.002)

    # Cleanup
    if f:
        print("[Core 1] Closing log file")
        f.close()
    print("[Core 1] Logging Thread Stopped")

def main_loop(server, led_np):
    """
    MAIN SYSTEM LOOP (Runs on Core 0)
    Handles Web Server, Animations, and WiFi.
    """
    print("[Core 0] System Loop Active")
    
    while True:
        # 1. Poll Web Server (Handle cloud sync requests)
        server.poll()
        
        # 2. Check for Track/Sector Events from Core 1
        track_event = gps_state.get('track_event')
        if track_event:
            gps_state['track_event'] = None  # Consume event
            
            # Determine duration based on event type
            if track_event == "TRACK_FOUND":
                led_np.trigger_event(track_event, duration_ms=3000)  # 3 seconds
            else:
                led_np.trigger_event(track_event, duration_ms=600)   # 600ms for sector
        
        # 3. Determine Base State for LED (priority-aware)
        # Priority: Storage Critical > Events > Logging > Searching > Idle
        base_state = "IDLE"
        if gps_state['storage_pct'] >= 90:
            base_state = "STORAGE_CRITICAL"  # New: 90% threshold for solid red
        elif gps_state['storage_pct'] >= 85:
            base_state = "STORAGE_WARN"
        elif gps_state['valid'] and gps_state['logging_active']:
            base_state = "LOGGING"
        elif gps_state['timestamp']:
            base_state = "SEARCHING"
        
        # Use event-aware update (handles priority internally)
        led_np.update_with_events(base_state)
        
        # 4. Status LED management (Onboard Blue LED)
        now = time.ticks_ms()
        if base_state == "STORAGE_CRITICAL":
             # Fast blink blue if critical
             led.value(1 if (now % 200 < 100) else 0)
        elif gps_state['valid'] and gps_state['logging_active']:
            # Slow heart-beat pulse when locked
            led.value(1 if (now % 1000 < 100) else 0)
        else:
            # Fast toggle when searching
            led.value(1 if (now % 500 < 250) else 0)
        
        # 5. Memory management
        if now % 5000 < 20: # Every 5 seconds roughly
            gc.collect()

        # Core 0 yields for WiFi tasks
        time.sleep(0.01)

if __name__ == '__main__':
    try:
        gps_sensor, session_mgr, web_server, led_np, track_eng = setup()
        
        # Start Logging Thread on Core 1
        _thread.start_new_thread(logging_thread, (gps_sensor, session_mgr, track_eng))
        
        # Start System Loop on Core 0
        main_loop(web_server, led_np)
        
    except Exception as e:
        print(f"CRASH: {e}")
        time.sleep(5)
        machine.reset()

