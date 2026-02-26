import machine
import time

class BMI270:
    # Registers
    REG_CHIP_ID = 0x00
    REG_ERR = 0x02
    REG_STATUS = 0x03
    REG_ACC_DATA_X = 0x0C
    REG_ACC_DATA_Y = 0x0E
    REG_ACC_DATA_Z = 0x10
    REG_GYR_DATA_X = 0x12
    REG_GYR_DATA_Y = 0x14
    REG_GYR_DATA_Z = 0x16
    
    REG_ACC_CONF = 0x40
    REG_ACC_RANGE = 0x41
    REG_GYR_CONF = 0x42
    REG_GYR_RANGE = 0x43
    
    REG_PWR_CONF = 0x7C
    REG_PWR_CTRL = 0x7D
    REG_CMD = 0x7E
    
    CHIP_ID = 0x24
    
    def __init__(self, i2c, address=0x68): # 7Semi module is usually 0x68 or 0x69
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
        time.sleep(0.1)
        
        # 2. Check Chip ID
        cid = self._read_mem(self.REG_CHIP_ID, 1)[0]
        if cid != self.CHIP_ID:
            print("Warning: BMI270 Chip ID mismatch: " + hex(cid))
        
        # 3. Disable Power Save
        self._write_mem(self.REG_PWR_CONF, 0x00)
        time.sleep(0.01)
        
        # 4. Enable Accel and Gyro (PWR_CTRL)
        # Bit 2 = Accel, Bit 1 = Gyro, Bit 0 = Auxiliary
        self._write_mem(self.REG_PWR_CTRL, 0x0E) 
        time.sleep(0.01)
        
        # 5. Configure Accel (100Hz, +/- 4g)
        # ACC_CONF: 0xA8 (Normal mode, 100Hz)
        # ACC_RANGE: 0x01 (+/- 4g)
        self._write_mem(self.REG_ACC_CONF, 0xA8)
        self._write_mem(self.REG_ACC_RANGE, 0x01)
        
        # 6. Configure Gyro (100Hz, 500dps)
        # GYR_CONF: 0xA8 (Normal mode, 100Hz)
        # GYR_RANGE: 0x02 (500dps)
        self._write_mem(self.REG_GYR_CONF, 0xA8)
        self._write_mem(self.REG_GYR_RANGE, 0x02)
        
        print("BMI270 initialized.")

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
