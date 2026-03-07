import machine, os, sys, time
import gc
import neopixel
import math

# ==========================================
# STANDALONE PERIPHERAL DRIVERS
# ==========================================

class BMI270:
    REG_CHIP_ID = 0x00
    REG_ERR = 0x02
    REG_STATUS = 0x03
    REG_ACC_DATA_X = 0x0C
    REG_GYR_DATA_X = 0x12
    REG_INTERNAL_STATUS = 0x21
    REG_ACC_CONF = 0x40
    REG_ACC_RANGE = 0x41
    REG_GYR_CONF = 0x42
    REG_GYR_RANGE = 0x43
    REG_INIT_CTRL = 0x59
    REG_INIT_ADDR_0 = 0x5B
    REG_INIT_DATA = 0x5E
    REG_PWR_CONF = 0x7C
    REG_PWR_CTRL = 0x7D
    REG_CMD = 0x7E
    CHIP_ID = 0x24
    
    def __init__(self, i2c, address=0x69):
        self.i2c = i2c
        self.address = address
        self._init_sensor()

    def _read_mem(self, reg, count):
        return self.i2c.readfrom_mem(self.address, reg, count)

    def _write_mem(self, reg, data):
        if isinstance(data, int): data = bytes([data])
        self.i2c.writeto_mem(self.address, reg, data)

    def _signed(self, val):
        return val if val < 32768 else val - 65536

    def _init_sensor(self):
        self._write_mem(self.REG_CMD, 0xB6)
        time.sleep(0.3)
        cid = self._read_mem(self.REG_CHIP_ID, 1)[0]
        if cid != self.CHIP_ID:
            print(f"Warning: BMI270 Chip ID mismatch: {hex(cid)}")
        self._write_mem(self.REG_PWR_CONF, 0x00)
        time.sleep(0.01)
        # Load config file (mandatory for BMI270)
        status = self._read_mem(self.REG_INTERNAL_STATUS, 1)[0] & 0x0F
        if status != 0x01:
            from micropython_bmi270.config_file import bmi270_config_file as cfg
            self._write_mem(self.REG_INIT_CTRL, 0x00)
            for page in range(256):
                self._write_mem(0x5B, 0x00)
                self._write_mem(0x5C, page)
                time.sleep(0.03)
                self.i2c.writeto_mem(self.address, 0x5E, bytes(cfg[page*32:(page+1)*32]))
                time.sleep(0.00002)
            self._write_mem(self.REG_INIT_CTRL, 0x01)
            time.sleep(0.02)
        self._write_mem(self.REG_PWR_CTRL, 0x0E)
        time.sleep(0.01)
        self._write_mem(self.REG_ACC_CONF, 0xA8)
        self._write_mem(self.REG_ACC_RANGE, 0x01)
        self._write_mem(self.REG_GYR_CONF, 0xA8)
        self._write_mem(self.REG_GYR_RANGE, 0x00)
        time.sleep(0.05)

    def get_values(self):
        raw_a = self._read_mem(self.REG_ACC_DATA_X, 6)
        raw_g = self._read_mem(self.REG_GYR_DATA_X, 6)
        return {
            "acc": {
                "x": self._signed(raw_a[0] | (raw_a[1] << 8)),
                "y": self._signed(raw_a[2] | (raw_a[3] << 8)),
                "z": self._signed(raw_a[4] | (raw_a[5] << 8))
            },
            "gyro": {
                "x": self._signed(raw_g[0] | (raw_g[1] << 8)),
                "y": self._signed(raw_g[2] | (raw_g[3] << 8)),
                "z": self._signed(raw_g[4] | (raw_g[5] << 8))
            }
        }

class GPS:
    def __init__(self, uart):
        self.uart = uart
        self.last_fix = {
            'lat': None, 'lon': None, 'altitude': 0.0,
            'speed_kmh': 0.0, 'satellites': 0, 'timestamp': None,
            'date': None, 'gps_timestamp': '', 'valid': False
        }
        
    def send_ubx(self, msg_class, msg_id, payload):
        header = b'\xb5\x62'
        length = len(payload).to_bytes(2, 'little')
        msg = bytes([msg_class, msg_id]) + length + payload
        ck_a, ck_b = 0, 0
        for b in msg:
            ck_a = (ck_a + b) & 0xFF
            ck_b = (ck_b + ck_a) & 0xFF
        self.uart.write(header + msg + bytes([ck_a, ck_b]))

    def set_baudrate(self, baud):
        if baud == 115200:
            payload = b'\x01\x00\x00\x00\xd0\x08\x00\x00\x00\xc2\x01\x00\x07\x00\x03\x00\x00\x00\x00\x00'
        else:
            payload = b'\x01\x00\x00\x00\xd0\x08\x00\x00' + baud.to_bytes(4, 'little') + b'\x07\x00\x03\x00\x00\x00\x00\x00'
        self.send_ubx(0x06, 0x00, payload)

    def set_rate(self, hz):
        interval = int(1000 / hz)
        self.send_ubx(0x06, 0x08, interval.to_bytes(2, 'little') + b'\x01\x00\x01\x00')
        for msg in [b'\xf0\x03\x00', b'\xf0\x01\x00', b'\xf0\x05\x00', b'\xf0\x02\x00']:
            self.send_ubx(0x06, 0x01, msg)

    def update(self):
        while self.uart.any():
            try:
                line = self.uart.readline()
                if not line: break
                line_str = line.decode('utf-8').strip()
                if line_str.startswith('$'): self._parse_nmea(line_str)
            except: pass
        
        # Construct full timestamp: DDMMYY_HHMMSS.SS
        if self.last_fix.get('date') and self.last_fix.get('timestamp'):
            self.last_fix['gps_timestamp'] = f"{self.last_fix['date']}_{self.last_fix['timestamp']}"
        else:
            self.last_fix['gps_timestamp'] = self.last_fix.get('timestamp', '0')
            
        return self.last_fix

    def _chk(self, line):
        try:
            pt = line.split('*')
            if len(pt) != 2: return False
            content, checksum_received = pt[0][1:], int(pt[1], 16)
            calc = 0
            for char in content: calc ^= ord(char)
            return calc == checksum_received
        except: return False

    def _parse_nmea(self, line):
        if not self._chk(line): return 
        parts = line.split(',')
        msg_id = parts[0][3:]
        if msg_id == 'RMC':
            if len(parts) < 10: return
            if parts[1]: self.last_fix['timestamp'] = parts[1]
            valid = parts[2] == 'A'
            self.last_fix['valid'] = valid
            if valid:
                self.last_fix['lat'] = self._dm_to_dd(parts[3], parts[4])
                self.last_fix['lon'] = self._dm_to_dd(parts[5], parts[6])
                try: self.last_fix['speed_kmh'] = float(parts[7] or 0) * 1.852
                except: pass
            if len(parts) > 9 and parts[9]: self.last_fix['date'] = parts[9]
        elif msg_id == 'GGA':
            if len(parts) > 9:
                try: self.last_fix['satellites'] = int(parts[7] or 0)
                except: pass
                try: self.last_fix['altitude'] = float(parts[9] or 0)
                except: pass

    def _dm_to_dd(self, val, hemi):
        if not val or not hemi: return None
        try:
            dot = val.find('.')
            degrees, minutes = float(val[:dot-2]), float(val[dot-2:])
            calc = degrees + (minutes / 60.0)
            return -calc if hemi in ['S', 'W'] else calc
        except: return None

# ==========================================
# MAIN TEST SCRIPT
# ==========================================

# --- CONFIGURATION ---
PIN_LED = 2
PIN_CS = 10
PIN_SCK = 12
PIN_MOSI = 11
PIN_MISO = 13
PIN_NEOPIXEL = 4
NUM_PIXELS = 16

print("="*50)
print(" NATIVE FULL SYSTEM INTEGRATION TEST (STANDALONE)")
print("="*50)

# 0. Initialize NeoPixel & Boot Animation
np = neopixel.NeoPixel(machine.Pin(PIN_NEOPIXEL), NUM_PIXELS)
print("[0] Booting Animation...")
for i in range(NUM_PIXELS):
    np[i] = (0, 0, 50)
    np.write()
    time.sleep_ms(30)
for i in range(NUM_PIXELS):
    np[i] = (0, 0, 0)
    np.write()
    time.sleep_ms(30)
np.fill((0, 0, 50))
np.write()

# 1. Initialize LED
led = machine.Pin(PIN_LED, machine.Pin.OUT)

# 2. Initialize SD Card
print("[1] Initializing Native SDCard...")
sd = None
sd_ok = False
try:
    sd = machine.SDCard(slot=2, width=1, sck=machine.Pin(PIN_SCK), mosi=machine.Pin(PIN_MOSI), miso=machine.Pin(PIN_MISO), cs=machine.Pin(PIN_CS))
    os.mount(sd, '/sd')
    print("    SD Card mounted at /sd")
    sd_ok = True
except Exception as e:
    print(f"    WARNING: SD Native mount failed: {e}")

# 2.5 SD Status Animation (5 Seconds)
print("[1.5] SD Status Animation...")
sd_color = (0, 50, 0) if sd_ok else (50, 0, 0)
# Pulse both ends toward center for ~5 seconds
for loop in range(10): 
    for i in range(NUM_PIXELS // 2):
        np[i] = sd_color
        np[NUM_PIXELS - 1 - i] = sd_color
        np.write()
        time.sleep_ms(50)
    for i in range(NUM_PIXELS // 2 - 1, -1, -1):
        np[i] = (0, 0, 0)
        np[NUM_PIXELS - 1 - i] = (0, 0, 0)
        np.write()
        time.sleep_ms(50)

# 3. Initialize IMU (BMI270)
imu = None
imu_ok = False
print("[2] Initializing BMI270 IMU (I2C0)...")
for i in range(5):
    try:
        # Use 400kHz for full speed as per main.py
        i2c0 = machine.I2C(0, sda=machine.Pin(21), scl=machine.Pin(39), freq=400000)
        imu = BMI270(i2c0, address=0x69)
        print("    IMU Ready.")
        imu_ok = True
        break
    except Exception as e:
        print(f"    IMU Init Attempt {i+1} failed: {e}")
        time.sleep(0.5)

# 4. Initialize GPS
print("[3] Initializing GPS (UART1)...")
gps = None
try:
    uart1 = machine.UART(1, baudrate=9600, tx=17, rx=18)
    gps = GPS(uart1)
    print("    Shifting GPS to 115200 baud...")
    gps.set_baudrate(115200)
    time.sleep(0.1)
    uart1.init(baudrate=115200)
    print("    Setting GPS rate to 10Hz...")
    gps.set_rate(10)
    print("    GPS Ready.")
except Exception as e:
    print(f"    GPS Error: {e}")

# 5. Setup CSV File
log_file = None
if sd_ok:
    def get_next_log_file():
        idx = 1
        existing = os.listdir('/sd')
        while True:
            fn = f"log_{idx:03d}.csv"
            if fn not in existing: return f"/sd/{fn}"
            idx += 1
    log_file = get_next_log_file()
    header = "gps_unix_time,lat,lon,sats,speed_kmh,acc_x,acc_y,acc_z,gyro_x,gyro_y,gyro_z\n"
    print(f"[4] Preparing Log: {log_file}")
    try:
        with open(log_file, "a") as f:
            if os.stat(log_file)[6] == 0: f.write(header)
    except:
        with open(log_file, "w") as f: f.write(header)
else:
    print("[4] Skipping Log Preparation (No SD Card).")

# 6. Main Loop
print("\n[LOGGING STARTED] Waiting for GPS Fix. Ctrl+C to stop.\n")
anim_tick = 0
last_sync_ms = time.ticks_ms()
SYNC_INTERVAL_MS = 5000
rtc_synced = False

# --- New Animation State ---
colors = [
    (50, 0, 0),   # Red
    (0, 50, 0),   # Green
    (0, 0, 50),   # Blue
    (40, 0, 40),  # Purple
    (0, 40, 40),  # Cyan
    (50, 20, 0)   # Orange
]
color_idx = 1 # Start with Green
flash_ticks = 0
last_shake_ms = 0

try:
    f = open(log_file, "a") if sd_ok else None
    while True:
        start_ms = time.ticks_ms()
        anim_tick += 1
        fix = gps.update() if gps else {}
        has_fix = fix.get('valid', False)
        
        try: 
            imu_vals = imu.get_values() if imu else None
            if imu_vals:
                if imu_vals["gyro"]["z"] == -32768 or (imu_vals["acc"]["z"] == 0 and imu_vals["acc"]["x"] == 0):
                    imu_ok = False
                else:
                    imu_ok = True
            else: imu_ok = False
        except: 
            imu_vals = None
            imu_ok = False

        acc = imu_vals["acc"] if imu_vals else {"x":0,"y":0,"z":0}
        gyr = imu_vals["gyro"] if imu_vals else {"x":0,"y":0,"z":0}

        # Status LED Heartbeat
        led.value(1 if anim_tick % 2 == 0 else 0)

        # ------------------------------------------
        # REACTIVE 4x4 NEOPIXEL ANIMATION
        # ------------------------------------------
        # 1. Shake Detection & Color Cycling
        gyro_mag = math.sqrt(gyr["x"]**2 + gyr["y"]**2 + gyr["z"]**2)
        if gyro_mag > 8000 and time.ticks_diff(time.ticks_ms(), last_shake_ms) > 500:
            color_idx = (color_idx + 1) % len(colors)
            flash_ticks = 3 # Flash white for 3 ticks
            last_shake_ms = time.ticks_ms()
        
        # 2. Base Color & Tilt Logic
        # Normal state color from list
        current_color = colors[color_idx]
        
        # If IMU Error or Searching, override logic for awareness
        if not imu_ok: current_color = (40, 0, 0) # Force Red for error
        
        # Tilt offset (Normalized to +/- 1.5 range to keep 2-px center constrained)
        # Acc range +/- 16384. Sensible tilt is around +/- 8000
        offset_x = int(max(-1, min(1, acc["y"] / 5000))) # Tilt side-to-side
        offset_y = int(max(-1, min(1, acc["x"] / 5000))) # Tilt front-to-back
        
        # Base center LEDs for 4x4 (row-major: 0..15)
        # Center points are (1,1) and (2,1)
        # Map to indexes: y*4 + x
        p1_x, p1_y = 1 + offset_x, 1 + offset_y
        p2_x, p2_y = 2 + offset_x, 1 + offset_y
        
        idx1 = (p1_y * 4) + p1_x
        idx2 = (p2_y * 4) + p2_x

        np.fill((0, 0, 0))
        if flash_ticks > 0:
            np.fill((50, 50, 50)) # Flash White 
            flash_ticks -= 1
        else:
            # Draw the 2 center LEDs
            if 0 <= idx1 < 16: np[idx1] = current_color
            if 0 <= idx2 < 16: np[idx2] = current_color
            
            # Subtle dim tail or search pulsing if no GPS fix
            if not has_fix:
                pulse = int(10 * math.sin(anim_tick / 2) + 10)
                # Keep center visible but dim background
                bg = (pulse, pulse, 0)
                for i in range(16):
                    if i != idx1 and i != idx2: 
                        np[i] = bg
        np.write()

        if has_fix and sd_ok and f:
            # Sync RTC once for high-res timestamps
            if not rtc_synced:
                try:
                    d, t = fix['date'], fix['timestamp']
                    year, month, day = 2000+int(d[4:6]), int(d[2:4]), int(d[0:2])
                    hour, minute, sec = int(t[0:2]), int(t[2:4]), int(t[4:6])
                    machine.RTC().datetime((year, month, day, 0, hour, minute, sec, 0))
                    rtc_synced = True
                except: pass
            
            # Form accurate Unix timestamp
            t_now = time.time() + 946684800
            ms = time.ticks_ms() % 1000
            gps_ts = f"{t_now}.{ms:03d}"

            row = "{},{},{},{},{:.2f},{},{},{},{},{},{}\n".format(
                gps_ts, fix.get('lat', '0'), fix.get('lon', '0'),
                fix.get('satellites', '0'), fix.get('speed_kmh', 0.0),
                acc["x"], acc["y"], acc["z"], gyr["x"], gyr["y"], gyr["z"]
            )
            try:
                f.write(row)
                if time.ticks_diff(time.ticks_ms(), last_sync_ms) > SYNC_INTERVAL_MS:
                    f.flush()
                    os.sync()
                    last_sync_ms = time.ticks_ms()
            except: pass

        # Screen Output
        status_msg = "LOGGING" if has_fix else "WAITING FOR FIX"
        # Display simplified timestamp for screen clarity
        scr_ts = fix.get('timestamp', '-')
        print(f"[{status_msg}] GPS: {scr_ts} | AccZ: {acc.get('z', 0)} | GyroX: {gyr.get('x',0)}   ", end="\r")

        time.sleep_ms(max(0, 100 - time.ticks_diff(time.ticks_ms(), start_ms)))

except KeyboardInterrupt:
    print("\n[STOPPING] Cleaning up...")
finally:
    led.value(0)
    np.fill((0, 0, 0))
    np.write()
    try:
        if f: f.close()
    except: pass
    try: os.umount('/sd')
    except: pass
    if sd:
        try: sd.deinit()
        except: pass
    print("Done.")
