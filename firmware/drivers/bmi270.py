import machine
import time

class BMI270:
    # Registers
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
    REG_INIT_ADDR_1 = 0x5C
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
        if isinstance(data, int):
            data = bytes([data])
        self.i2c.writeto_mem(self.address, reg, data)

    def _init_sensor(self):
        # 1. Soft Reset
        self._write_mem(self.REG_CMD, 0xB6)
        time.sleep(0.3)
        
        # 2. Check Chip ID
        cid = self._read_mem(self.REG_CHIP_ID, 1)[0]
        if cid != self.CHIP_ID:
            print("Warning: BMI270 Chip ID mismatch: " + hex(cid))
        
        # 3. Disable Advanced Power Save (mandatory before config load)
        self._write_mem(self.REG_PWR_CONF, 0x00)
        time.sleep(0.01)
        
        # 4. Load Config File (mandatory for BMI270 to produce data)
        self._load_config()
        
        # 5. Enable Accel, Gyro, Temp (PWR_CTRL: bit2=acc, bit1=gyr, bit0=aux)
        self._write_mem(self.REG_PWR_CTRL, 0x0E)
        time.sleep(0.01)
        
        # 6. Configure Accel (100Hz, Normal mode, +/- 4g)
        self._write_mem(self.REG_ACC_CONF, 0xA8)
        self._write_mem(self.REG_ACC_RANGE, 0x01)  # +/- 4g
        
        # 7. Configure Gyro (100Hz, Normal mode, +/- 2000dps)
        self._write_mem(self.REG_GYR_CONF, 0xA8)
        self._write_mem(self.REG_GYR_RANGE, 0x00)  # +/- 2000dps
        
        time.sleep(0.05)
        print("BMI270 initialized.")

    def _load_config(self):
        # Check if already initialized (survives soft reset sometimes)
        status = self._read_mem(self.REG_INTERNAL_STATUS, 1)[0] & 0x0F
        if status == 0x01:
            print("IMU: Config already loaded.")
            return
        
        # Import config blob from community library (installed via mip)
        from micropython_bmi270.config_file import bmi270_config_file as cfg
        
        # Prepare for config load
        self._write_mem(self.REG_PWR_CONF, 0x00)
        time.sleep(0.001)
        self._write_mem(self.REG_INIT_CTRL, 0x00)
        
        # Write config in 32-byte pages (256 pages × 32 bytes = 8192 bytes)
        # INIT_ADDR_0 = 0x00 (LSB, always 0), INIT_ADDR_1 = page index
        for page in range(256):
            self._write_mem(0x5B, 0x00)           # INIT_ADDR_0
            self._write_mem(0x5C, page)            # INIT_ADDR_1
            time.sleep(0.03)
            chunk = cfg[page * 32 : (page + 1) * 32]
            self.i2c.writeto_mem(self.address, 0x5E, bytes(chunk))
            time.sleep(0.00002)
        
        # Trigger initialization
        self._write_mem(self.REG_INIT_CTRL, 0x01)
        time.sleep(0.02)
        
        # Verify
        status = self._read_mem(self.REG_INTERNAL_STATUS, 1)[0] & 0x0F
        if status != 0x01:
            print(f"IMU: WARNING - Init status: {status} (expected 1)")
        else:
            print("IMU: Config loaded OK.")

    def _signed(self, val):
        return val if val < 32768 else val - 65536

    def get_accel(self):
        raw = self._read_mem(self.REG_ACC_DATA_X, 6)
        x = self._signed(raw[0] | (raw[1] << 8))
        y = self._signed(raw[2] | (raw[3] << 8))
        z = self._signed(raw[4] | (raw[5] << 8))
        return [x, y, z]

    def get_gyro(self):
        raw = self._read_mem(self.REG_GYR_DATA_X, 6)
        x = self._signed(raw[0] | (raw[1] << 8))
        y = self._signed(raw[2] | (raw[3] << 8))
        z = self._signed(raw[4] | (raw[5] << 8))
        return [x, y, z]

    def get_values(self):
        acc = self.get_accel()
        gyr = self.get_gyro()
        return {
            "acc": {"x": acc[0], "y": acc[1], "z": acc[2]},
            "gyro": {"x": gyr[0], "y": gyr[1], "z": gyr[2]},
            "temp": 0
        }

if __name__ == "__main__":
    print("--- Testing BMI270 Driver ---")
    i2c = machine.I2C(0, sda=machine.Pin(21), scl=machine.Pin(39), freq=400000)
    print("I2C Devices:", [hex(a) for a in i2c.scan()])
    
    try:
        imu = BMI270(i2c, address=0x69)
        print("BMI270 Initialized Successfully!")
        for _ in range(10):
            vals = imu.get_values()
            print(f"Acc: {vals['acc']} | Gyro: {vals['gyro']}")
            time.sleep(0.5)
    except Exception as e:
        print("Error during test:", e)
