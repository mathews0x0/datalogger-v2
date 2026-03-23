import machine
import time

class BMI323:
    # Registers (Word addresses for BMI323)
    REG_CHIP_ID = 0x00
    REG_STATUS = 0x01
    REG_ERR = 0x02
    REG_ACC_DATA_X = 0x03
    REG_ACC_DATA_Y = 0x04
    REG_ACC_DATA_Z = 0x05
    REG_GYR_DATA_X = 0x06
    REG_GYR_DATA_Y = 0x07
    REG_GYR_DATA_Z = 0x08
    REG_TEMP_DATA = 0x09
    
    REG_ACC_CONF = 0x20
    REG_GYR_CONF = 0x21
    REG_CMD = 0x7E
    
    CHIP_ID = 0x43
    
    # Sensitivity constants for +/- 4g and +/- 2000dps
    ACC_SENSITIVITY = 8192.0   # LSB/g (2^15 / 4)
    GYR_SENSITIVITY = 16.4     # LSB/dps (2^15 / 2000)
    
    def __init__(self, i2c, address=0x69):
        self.i2c = i2c
        self.address = address
        self._init_sensor()

    def _read_words(self, reg, count):
        # BMI323 I2C: 2 dummy bytes + (2 * count) bytes
        raw = self.i2c.readfrom_mem(self.address, reg, count * 2 + 2)
        words = []
        for i in range(count):
            lsb = raw[2 + 2 * i]
            msb = raw[3 + 2 * i]
            val = (msb << 8) | lsb
            words.append(val if val < 32768 else val - 65536)
        return words

    def _write_word(self, reg, val):
        # BMI323 registers are 16-bit (words). 
        # I2C Write Format: [Register Address] [LSB] [MSB]
        # Validated: Direct writeto is more stable than writeto_mem for this sequence
        data = bytearray([reg, val & 0xFF, (val >> 8) & 0xFF])
        self.i2c.writeto(self.address, data)

    def _init_sensor(self):
        # 1. Soft Reset
        try:
            self._write_word(self.REG_CMD, 0xDEAF)
            time.sleep(0.1)
        except:
            pass
            
        # 2. Dummy read to wake serial interface
        self._read_words(self.REG_CHIP_ID, 1)
        
        # 3. Check Chip ID
        cid = self._read_words(self.REG_CHIP_ID, 1)[0]
        if (cid & 0xFF) != self.CHIP_ID:
            print(f"Warning: Unexpected Chip ID {hex(cid)}")
            
        # 4. Check for Initial Errors (Pre-Config)
        err_init = self._read_words(self.REG_ERR, 1)[0]
        if err_init != 0:
            print(f"IMU: Initial Error Register: {hex(err_init)}")
            
        # 5. Configure Accel (High Performance, 100Hz, +/- 4g, ODR/4 BW, 4x Avg)
        # Bits 14:12 (mode): 111 = HP (7)
        # Bits 10:8  (avg):  010 = 4-sample avg (2)
        # Bit  7     (bw):   1   = ODR/4 (1)
        # Bits 6:4   (range): 001 = ±4g (1)
        # Bits 3:0   (odr):   0111 = 100Hz (7)
        # Binary: 0111 0010 1001 0111 = 0x7297
        self._write_word(self.REG_ACC_CONF, 0x7297)
        
        # 6. Configure Gyro (High Performance, 100Hz, +/- 2000dps, ODR/4 BW, 2x Avg)
        # Bits 14:12 (mode): 111 = HP (7)
        # Bits 10:8  (avg):  001 = 2-sample avg (1)
        # Bit  7     (bw):   1   = ODR/4 (1)
        # Bits 6:4   (range): 000 = ±2000dps (0)
        # Bits 3:0   (odr):   0111 = 100Hz (7)
        # Binary: 0111 0001 1000 0111 = 0x7187
        self._write_word(self.REG_GYR_CONF, 0x7187)
        time.sleep(0.1)

        # 7. Final Error Check (Post-Config)
        err = self._read_words(self.REG_ERR, 1)[0]
        if err != 0:
            print(f"IMU: Sensor Error Register: {hex(err)}")
            if err & 1:
                print("IMU: Fatal Error - Chip may require power cycle")

    def get_accel(self):
        return self._read_words(self.REG_ACC_DATA_X, 3)

    def get_gyro(self):
        return self._read_words(self.REG_GYR_DATA_X, 3)

    def get_values_into(self, out):
        """Fill a caller-provided list with ax, ay, az, gx, gy, gz raw values."""
        raw = self.i2c.readfrom_mem(self.address, self.REG_ACC_DATA_X, 14)
        idx = 0
        for i in range(6):
            lsb = raw[2 + 2 * i]
            msb = raw[3 + 2 * i]
            val = (msb << 8) | lsb
            out[idx] = val if val < 32768 else val - 65536
            idx += 1

    def get_values(self):
        acc = self.get_accel()
        gyr = self.get_gyro()
        return {
            "acc": {"x": acc[0], "y": acc[1], "z": acc[2]},
            "gyro": {"x": gyr[0], "y": gyr[1], "z": gyr[2]},
            "temp": 0 
        }

if __name__ == "__main__":
    import machine
    print("--- Testing bmi323_validated.py ---")
    i2c = machine.I2C(0, sda=machine.Pin(21), scl=machine.Pin(39), freq=400000)
    print("I2C Devices:", [hex(a) for a in i2c.scan()])
    
    try:
        imu = BMI323(i2c, address=0x69)
        print("BMI323 Initialized Successfully!")
        for _ in range(5):
            vals = imu.get_values()
            print(f"Acc: {vals['acc']} | Gyro: {vals['gyro']}")
            time.sleep(0.5)
    except Exception as e:
        print("Error during test:", e)
