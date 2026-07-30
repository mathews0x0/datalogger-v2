import machine
import time

class BMI323:
    # Registers (Word addresses for BMI323)
    REG_CHIP_ID = 0x00
    REG_ERR = 0x01
    REG_STATUS = 0x02
    REG_ACC_DATA_X = 0x03
    REG_ACC_DATA_Y = 0x04
    REG_ACC_DATA_Z = 0x05
    REG_GYR_DATA_X = 0x06
    REG_GYR_DATA_Y = 0x07
    REG_GYR_DATA_Z = 0x08
    REG_TEMP_DATA = 0x09
    REG_FIFO_FILL_LEVEL = 0x15
    REG_FIFO_DATA = 0x16
    
    REG_ACC_CONF = 0x20
    REG_GYR_CONF = 0x21
    REG_FIFO_CONF = 0x36
    REG_FIFO_CTRL = 0x37
    REG_CMD = 0x7E
    STATUS_DRDY_MASK = 0x00C0
    FIFO_ACC_EN = 0x0200
    FIFO_GYR_EN = 0x0400
    FIFO_TIME_EN = 0x0100
    FIFO_FRAME_WORDS = 7
    SENSOR_TIME_LSB_US = 39.0625
    
    CHIP_ID = 0x43
    
    # Configuration values used below. Keep these paired with the sensitivity constants.
    # BMI323 CONF fields: mode[14:12], avg[10:8], bw[7], range[6:4], odr[3:0].
    ACC_CONF_100HZ_4G = 0x7298
    GYR_CONF_100HZ_2000DPS = 0x71C8

    # Sensitivity constants for +/- 4g and +/- 2000dps.
    ACC_SENSITIVITY = 8192.0   # LSB/g (2^15 / 4)
    GYR_SENSITIVITY = 16.4     # LSB/dps (2^15 / 2000)
    
    def __init__(self, i2c, address=0x69):
        self.i2c = i2c
        self.address = address
        self._last_sample = None
        self._fifo_sensor_ticks = None
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

    def _read_u16_words(self, reg, count):
        raw = self.i2c.readfrom_mem(self.address, reg, count * 2 + 2)
        words = []
        for i in range(count):
            lsb = raw[2 + 2 * i]
            msb = raw[3 + 2 * i]
            words.append((msb << 8) | lsb)
        return words

    def _u16_to_i16(self, value):
        return value if value < 32768 else value - 65536

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

        # FIFO must be configured before enabling sensors. Store accel + gyro + sensor time.
        self._write_word(self.REG_FIFO_CONF, self.FIFO_TIME_EN | self.FIFO_ACC_EN | self.FIFO_GYR_EN)
            
        # 5. Configure Accel (High Performance, 100Hz, +/- 4g, ODR/4 BW, 4x Avg)
        # Bits 14:12 (mode): 111 = HP (7)
        # Bits 10:8  (avg):  010 = 4-sample avg (2)
        # Bit  7     (bw):   1   = ODR/4 (1)
        # Bits 6:4   (range): 001 = ±4g (1)
        # Bits 3:0   (odr):   1000 = 100Hz (8)
        # Binary: 0111 0010 1001 1000 = 0x7298
        self._write_word(self.REG_ACC_CONF, self.ACC_CONF_100HZ_4G)
        
        # 6. Configure Gyro (High Performance, 100Hz, +/- 2000dps, ODR/4 BW, 2x Avg)
        # Bits 14:12 (mode): 111 = HP (7)
        # Bits 10:8  (avg):  001 = 2-sample avg (1)
        # Bit  7     (bw):   1   = ODR/4 (1)
        # Bits 6:4   (range): 100 = ±2000dps (4)
        # Bits 3:0   (odr):   1000 = 100Hz (8)
        # Binary: 0111 0001 1100 1000 = 0x71C8
        self._write_word(self.REG_GYR_CONF, self.GYR_CONF_100HZ_2000DPS)
        time.sleep(0.1)

        # 7. Final Error Check (Post-Config)
        err = self._read_words(self.REG_ERR, 1)[0]
        if err != 0:
            print(f"IMU: Sensor Error Register: {hex(err)}")
            if err & 1:
                print("IMU: Fatal Error - Chip may require power cycle")
        self.flush_fifo()

    def get_accel(self):
        return self._read_words(self.REG_ACC_DATA_X, 3)

    def get_gyro(self):
        return self._read_words(self.REG_GYR_DATA_X, 3)

    def get_status(self):
        """Return the raw 16-bit status register."""
        return self._read_words(self.REG_STATUS, 1)[0] & 0xFFFF

    def data_ready(self):
        """
        Conservative fresh-data check.
        BMI323 should expose accel/gyro data-ready bits in STATUS; require both.
        """
        return (self.get_status() & self.STATUS_DRDY_MASK) == self.STATUS_DRDY_MASK

    def get_fifo_fill_level_words(self):
        return self._read_u16_words(self.REG_FIFO_FILL_LEVEL, 1)[0] & 0x07FF

    def flush_fifo(self):
        self._write_word(self.REG_FIFO_CTRL, 0x0001)
        self._fifo_sensor_ticks = None

    def read_fifo_frames(self, max_frames=32):
        fill_words = self.get_fifo_fill_level_words()
        frame_count = fill_words // self.FIFO_FRAME_WORDS
        if frame_count <= 0:
            return []
        if max_frames is not None and frame_count > max_frames:
            frame_count = max_frames

        raw = self.i2c.readfrom_mem(self.address, self.REG_FIFO_DATA, frame_count * self.FIFO_FRAME_WORDS * 2 + 2)
        frames = []
        pos = 2
        for _ in range(frame_count):
            words = []
            for __ in range(self.FIFO_FRAME_WORDS):
                lsb = raw[pos]
                msb = raw[pos + 1]
                words.append((msb << 8) | lsb)
                pos += 2
            # Skip dummy frames emitted during internal settling after config changes.
            if words[0] == 0x7F01 or words[3] == 0x7F02:
                continue

            sensor_time_16 = words[6]
            if self._fifo_sensor_ticks is None:
                self._fifo_sensor_ticks = sensor_time_16
            else:
                prev16 = self._fifo_sensor_ticks & 0xFFFF
                delta = (sensor_time_16 - prev16) & 0xFFFF
                self._fifo_sensor_ticks += delta

            sample = (
                self._u16_to_i16(words[0]),
                self._u16_to_i16(words[1]),
                self._u16_to_i16(words[2]),
                self._u16_to_i16(words[3]),
                self._u16_to_i16(words[4]),
                self._u16_to_i16(words[5]),
            )
            if sample == self._last_sample:
                continue
            self._last_sample = sample
            frames.append({
                "sample": sample,
                "sensor_ticks": self._fifo_sensor_ticks,
                "sensor_us": int(round(self._fifo_sensor_ticks * self.SENSOR_TIME_LSB_US)),
            })
        return frames

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

    def get_values_into_if_fresh(self, out):
        """
        Fill `out` only when the sensor reports fresh data and the raw sample changed.
        Returns True when a new sample was captured, else False.
        """
        if not self.data_ready():
            return False
        self.get_values_into(out)
        sample = (out[0], out[1], out[2], out[3], out[4], out[5])
        if sample == self._last_sample:
            return False
        self._last_sample = sample
        return True

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
