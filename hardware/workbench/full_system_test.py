import machine, os, sys, time
import gc

# Add driver path
sys.path.append('/firmware/drivers')
from bmi323 import BMI323
from gps import GPS

import math

# --- CONFIGURATION ---
# GPS: UART1, IO17 (TX), IO18 (RX)
# IMU: I2C0, IO21 (SDA), IO39 (SCL)
# SD:  Slot 2 (SCK=12, MOSI=11, MISO=13, CS=10)
# LED: IO2 (Smart PWM Feedback)

PIN_LED = 2
PIN_CS = 10
PIN_SCK = 12
PIN_MOSI = 11
PIN_MISO = 13

print("="*50)
print(" NATIVE FULL SYSTEM INTEGRATION TEST")
print("="*50)

# 1. Initialize LED (PWM for brightness control)
led_pin = machine.Pin(PIN_LED, machine.Pin.OUT)
led = machine.PWM(led_pin, freq=1000, duty=0)

# 2. Initialize SD Card (Native)
print("[1] Initializing Native SDCard...")
sd = None
try:
    sd = machine.SDCard(slot=2, width=1,
                        sck=machine.Pin(PIN_SCK),
                        mosi=machine.Pin(PIN_MOSI),
                        miso=machine.Pin(PIN_MISO),
                        cs=machine.Pin(PIN_CS))
    os.mount(sd, '/sd')
    print("    SD Card mounted at /sd")
except Exception as e:
    print(f"    CRITICAL: SD Native mount failed: {e}")
    sys.exit(1)

# 3. Initialize IMU (BMI323)
imu = None
print("[2] Initializing BMI323 IMU (I2C0)...")
for i in range(5):
    try:
        # Use 100kHz for stability on workbench jumpers
        i2c0 = machine.I2C(0, sda=machine.Pin(21), scl=machine.Pin(39), freq=100000)
        imu = BMI323(i2c0, address=0x69)
        print("    IMU Ready.")
        break
    except Exception as e:
        print(f"    IMU Init Attempt {i+1} failed: {e}")
        time.sleep(0.2)
else:
    print("    CRITICAL: IMU could not be initialized after 5 attempts.")
    try:
        print("    Final Scan results:", [hex(a) for a in i2c0.scan()])
    except:
        pass
    print("    Check hardware wiring/power!")

# 4. Initialize GPS (UART1)
print("[3] Initializing GPS (UART1)...")
gps = None
try:
    # 1. Start at default 9600 to send config commands
    uart1 = machine.UART(1, baudrate=9600, tx=17, rx=18)
    gps = GPS(uart1)
    
    # 2. Shift to 115200 baud for 10Hz bandwidth
    print("    Shifting GPS to 115200 baud...")
    gps.set_baudrate(115200)
    time.sleep(0.1)
    uart1.init(baudrate=115200)
    
    # 3. Set update rate to 10Hz
    print("    Setting GPS rate to 10Hz...")
    gps.set_rate(10)
    
    print("    GPS Ready (115200 baud, 10Hz).")
except Exception as e:
    print(f"    GPS Error: {e}")

# 5. Setup CSV File
log_file = "/sd/full_log.csv"
header = "timestamp,lat,lon,sats,speed_kmh,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z\n"

print(f"[4] Preparing Log: {log_file}")
try:
    with open(log_file, "a") as f:
        # If file is empty, write header
        if os.stat(log_file)[6] == 0:
            f.write(header)
except:
    with open(log_file, "w") as f:
        f.write(header)

# 6. Main Loop
print("\n[LOGGING STARTED] Waiting for GPS Fix. Ctrl+C to stop.\n")

# State variables for feedback
led_breathe_step = 0
prev_acc = {"x": 0, "y": 0, "z": 0}
blink_state = False

# Sync state
last_sync_ms = time.ticks_ms()
SYNC_INTERVAL_MS = 5000

try:
    # Open file once to avoid filesystem overhead on every loop
    f = open(log_file, "a")
    
    while True:
        start_ms = time.ticks_ms()
        
        # A. Update GPS
        fix = gps.update() if gps else {}
        has_fix = fix.get('valid', False)
        
        # B. Read IMU
        try:
            imu_vals = imu.get_values() if imu else None
        except Exception as e:
            imu_vals = None

        if imu_vals:
            acc = imu_vals["acc"]
            gyr = imu_vals["gyro"]
        else:
            acc = {"x":0,"y":0,"z":0}
            gyr = {"x":0,"y":0,"z":0}
            
        # C. LED Feedback Logic
        if not has_fix:
            # Mode: No Fix -> Slow Breathing (Sine Wave)
            led_breathe_step = (led_breathe_step + 0.15) % (2 * math.pi)
            brightness = int((math.sin(led_breathe_step) + 1) / 2 * 1023)
            led.duty(brightness)
        else:
            # Mode: Fixed -> Fast Blink, Reactive to IMU
            delta_x = abs(acc["x"] - prev_acc["x"])
            delta_y = abs(acc["y"] - prev_acc["y"])
            delta_z = abs(acc["z"] - prev_acc["z"])
            total_delta = delta_x + delta_y + delta_z
            
            prev_acc = acc.copy()
            blink_state = not blink_state
            
            if blink_state:
                reactive_brightness = min(1023, 20 + int(total_delta / 10))
                led.duty(reactive_brightness)
            else:
                led.duty(0)

        # D. SD Logging Logic (Only if Fix is valid)
        if has_fix:
            row = "{},{},{},{},{:.2f},{},{},{},{},{},{}\n".format(
                fix.get('timestamp', '0'),
                fix.get('lat', '0'),
                fix.get('lon', '0'),
                fix.get('satellites', '0'),
                fix.get('speed_kmh', 0.0),
                acc["x"], acc["y"], acc["z"],
                gyr["x"], gyr["y"], gyr["z"]
            )
            try:
                f.write(row)
                
                # Periodic Flush/Sync to protect against sudden power loss
                if time.ticks_diff(time.ticks_ms(), last_sync_ms) > SYNC_INTERVAL_MS:
                    f.flush()
                    os.sync()
                    last_sync_ms = time.ticks_ms()
            except Exception as e:
                pass
        
        # E. Screen Update
        status_msg = "LOGGING" if has_fix else "WAITING FOR FIX"
        print(f"[{status_msg}] TS: {fix.get('timestamp','-')} | Sats: {fix.get('satellites',0)} | AccZ: {acc.get('z', 0)}   ", end="\r")
        
        # F. Loop Timing (~10Hz)
        elapsed = time.ticks_diff(time.ticks_ms(), start_ms)
        sleep_time = max(0, 100 - elapsed)
        time.sleep_ms(sleep_time)

except KeyboardInterrupt:
    print("\n[STOPPING] Cleaning up...")
finally:
    led.duty(0)
    try: f.close()
    except: pass
    try: os.umount('/sd')
    except: pass
    if sd:
        try: sd.deinit()
        except: pass
    print("Done.")
