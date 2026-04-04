class XPT2046:
    CMD_X = 0xD0
    CMD_Y = 0x90
    CMD_Z1 = 0xB0
    CMD_Z2 = 0xC0

    def __init__(self, spi, cs, irq=None, calibration=None, baudrate=2_000_000):
        self.spi = spi
        self.cs = cs
        self.irq = irq
        self.baudrate = baudrate
        self.cs.init(self.cs.OUT, value=1)
        if self.irq is not None:
            self.irq.init(self.irq.IN)
        self.tx = bytearray(3)
        self.rx = bytearray(3)
        self.calibration = calibration or {
            "xmin": 200,
            "xmax": 3900,
            "ymin": 200,
            "ymax": 3900,
            "width": 320,
            "height": 240,
            "swap_xy": False,
            "invert_x": False,
            "invert_y": False,
        }

    def _read12(self, command):
        self.spi.init(baudrate=self.baudrate, polarity=0, phase=0)
        self.tx[0] = command
        self.tx[1] = 0
        self.tx[2] = 0
        self.cs.value(0)
        self.spi.write_readinto(self.tx, self.rx)
        self.cs.value(1)
        return ((self.rx[1] << 4) | (self.rx[2] >> 4)) & 0x0FFF

    def pressure(self):
        z1 = self._read12(self.CMD_Z1)
        z2 = self._read12(self.CMD_Z2)
        if z1 == 0:
            return 0
        if z1 == 0x0FFF and z2 == 0x0FFF:
            return 0
        return z1 + (4095 - z2)

    def touched(self):
        if self.irq is not None:
            return self.irq.value() == 0
        raw = self.read_raw(samples=2, _skip_touch_check=True)
        if raw is None:
            return False
        z = raw["z"]
        # This panel idles around x=0, y=2047, z≈2050 when untouched.
        if raw["x"] < 32 and 2000 <= raw["y"] <= 2095 and z < 2300:
            return False
        return z >= 2300

    def read_raw(self, samples=5, _skip_touch_check=False):
        if not _skip_touch_check and not self.touched():
            return None
        total_x = 0
        total_y = 0
        for _ in range(samples):
            total_x += self._read12(self.CMD_X)
            total_y += self._read12(self.CMD_Y)
        x = total_x // samples
        y = total_y // samples
        z = self.pressure()
        if x == 0x0FFF and y == 0x0FFF and z == 0:
            return None
        return {"x": x, "y": y, "z": z}

    def read(self):
        raw = self.read_raw()
        if raw is None:
            return None

        cfg = self.calibration
        x = raw["x"]
        y = raw["y"]
        if cfg.get("swap_xy"):
            x, y = y, x

        x = self._map_axis(x, cfg["xmin"], cfg["xmax"], cfg["width"], cfg.get("invert_x"))
        y = self._map_axis(y, cfg["ymin"], cfg["ymax"], cfg["height"], cfg.get("invert_y"))
        raw["sx"] = x
        raw["sy"] = y
        return raw

    def _map_axis(self, value, low, high, span, invert=False):
        if high <= low:
            return 0
        if value < low:
            value = low
        if value > high:
            value = high
        scaled = int((value - low) * (span - 1) / (high - low))
        if invert:
            scaled = (span - 1) - scaled
        return scaled
