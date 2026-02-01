import machine
import time

class BMI323:
    # Registers (Word addresses)
    REG_CHIP_ID = 0x00
    REG_STATUS = 0x01
    REG_ACC_DATA_X = 0x03
    REG_ACC_DATA_Y = 0x04
    REG_ACC_DATA_Z = 0x05
    REG_GYR_DATA_X = 0x0C
    REG_ACC_CONF = 0x20
    REG_GYR_CONF = 0x21
    REG_PWR_CTRL = 0x22
    REG_CMD = 0x7E
    
    CHIP_ID = 0x43
    
    def __init__(self, i2c, address=0x69):
        self.i2c = i2c
        self.address = address
        self._init_sensor()

    def _read_words(self, reg, count):
        # BMI323 I2C: 2 dummy bytes + (2 * count) bytes
        raw = self.i2c.readfrom_mem(self.address, reg, count * 2 + 2)
        words = []
        for i in range(count):
            # Based on probe: Index 2/3 = Word 0, Index 4/5 = Word 1
            lsb = raw[2 + 2 * i]
            msb = raw[3 + 2 * i]
            val = (msb << 8) | lsb
            words.append(val if val < 32768 else val - 65536)
        return words

    def _write_word(self, reg, val):
        # Raw I2C write: [Register, LSB, MSB]
        data = bytearray([reg, val & 0xFF, (val >> 8) & 0xFF])
        self.i2c.writeto(self.address, data)

    def _init_sensor(self):
        # 1. Soft Reset
        self._write_word(self.REG_CMD, 0xDEAF)
        time.sleep(0.05)
        
        # 2. Check Chip ID
        cid = self._read_words(self.REG_CHIP_ID, 1)[0]
        if (cid & 0xFF) != self.CHIP_ID:
            print("Warning: Unexpected Chip ID " + hex(cid))
            
        # 3. Configure Accel (100Hz, +/- 4g, Normal Mode)
        # 0x01 = 4g range, 0x07 = 100Hz, 0x2000 = Normal Mode
        self._write_word(self.REG_ACC_CONF, 0x2107) 
        
        # 4. Configure Gyro (100Hz, 500dps, Normal Mode)
        # 0x01 = 500dps, 0x07 = 100Hz, 0x2000 = Normal Mode
        self._write_word(self.REG_GYR_CONF, 0x2107)
        time.sleep(0.05)

    def get_accel(self):
        # Read X, Y, Z (Registers 0x03, 0x04, 0x05)
        return self._read_words(self.REG_ACC_DATA_X, 3)

    def get_gyro(self):
        # Read X, Y, Z (Registers 0x0C, 0x0D, 0x0E)
        return self._read_words(self.REG_GYR_DATA_X, 3)

    def get_values(self):
        acc = self.get_accel()
        gyr = self.get_gyro()
        return {
            "acc": {"x": acc[0], "y": acc[1], "z": acc[2]},
            "gyro": {"x": gyr[0], "y": gyr[1], "z": gyr[2]},
            "temp": 0 
        }
