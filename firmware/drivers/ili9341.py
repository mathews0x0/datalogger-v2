import time


class ILI9341:
    def __init__(
        self,
        spi,
        cs,
        dc,
        rst=None,
        width=240,
        height=320,
        rotation=0,
        baudrate=40_000_000,
        madctl=None,
        clear_on_init=True,
        reset_on_init=True,
        init_on_init=True,
    ):
        self.spi = spi
        self.cs = cs
        self.dc = dc
        self.rst = rst
        self.width = width
        self.height = height
        self.rotation = rotation % 4
        self.baudrate = baudrate
        self.madctl = madctl
        self.clear_on_init = clear_on_init
        self.reset_on_init = reset_on_init
        self.init_on_init = init_on_init
        self._xbuf = bytearray(4)
        self._ybuf = bytearray(4)
        self._color_chunk = bytearray(4096)

        self.cs.init(self.cs.OUT, value=1)
        self.dc.init(self.dc.OUT, value=1)
        if self.rst is not None:
            self.rst.init(self.rst.OUT, value=1)

        if self.reset_on_init:
            self._hardware_reset()
        if self.init_on_init:
            self._init_display()
        self.set_rotation(self.rotation)
        if self.clear_on_init:
            self.fill(0x0000)

    def _activate_spi(self):
        self.spi.init(baudrate=self.baudrate, polarity=0, phase=0)

    def _hardware_reset(self):
        if self.rst is None:
            self.write_cmd(0x01)
            time.sleep_ms(150)
            return
        self.rst.value(1)
        time.sleep_ms(5)
        self.rst.value(0)
        time.sleep_ms(20)
        self.rst.value(1)
        time.sleep_ms(150)

    def write_cmd(self, cmd, data=None):
        self._activate_spi()
        self.cs.value(0)
        self.dc.value(0)
        self.spi.write(bytearray([cmd]))
        if data:
            self.dc.value(1)
            self.spi.write(data)
        self.cs.value(1)

    def _init_display(self):
        init_seq = (
            (0xCF, b"\x00\xC1\x30"),
            (0xED, b"\x64\x03\x12\x81"),
            (0xE8, b"\x85\x00\x78"),
            (0xCB, b"\x39\x2C\x00\x34\x02"),
            (0xF7, b"\x20"),
            (0xEA, b"\x00\x00"),
            (0xC0, b"\x23"),
            (0xC1, b"\x10"),
            (0xC5, b"\x3E\x28"),
            (0xC7, b"\x86"),
            (0x36, b"\x48"),
            (0x3A, b"\x55"),
            (0xB1, b"\x00\x18"),
            (0xB6, b"\x08\x82\x27"),
            (0xF2, b"\x00"),
            (0x26, b"\x01"),
            (0xE0, b"\x0F\x31\x2B\x0C\x0E\x08\x4E\xF1\x37\x07\x10\x03\x0E\x09\x00"),
            (0xE1, b"\x00\x0E\x14\x03\x11\x07\x31\xC1\x48\x08\x0F\x0C\x31\x36\x0F"),
        )

        for cmd, data in init_seq:
            self.write_cmd(cmd, data)

        self.write_cmd(0x11)
        time.sleep_ms(120)
        self.write_cmd(0x29)
        time.sleep_ms(20)

    def set_rotation(self, rotation):
        rotation = rotation % 4
        self.rotation = rotation
        # This panel wants BGR color order together with the framebuffer
        # byte-swap performed in tft_ui.show().
        madctl = self.madctl if self.madctl is not None else (0x48, 0x28, 0x88, 0xE8)[rotation]
        self.write_cmd(0x36, bytearray([madctl]))
        if rotation % 2:
            self.width = 320
            self.height = 240
        else:
            self.width = 240
            self.height = 320

    def set_window(self, x0, y0, x1, y1):
        self._xbuf[0] = (x0 >> 8) & 0xFF
        self._xbuf[1] = x0 & 0xFF
        self._xbuf[2] = (x1 >> 8) & 0xFF
        self._xbuf[3] = x1 & 0xFF
        self._ybuf[0] = (y0 >> 8) & 0xFF
        self._ybuf[1] = y0 & 0xFF
        self._ybuf[2] = (y1 >> 8) & 0xFF
        self._ybuf[3] = y1 & 0xFF
        self.write_cmd(0x2A, self._xbuf)
        self.write_cmd(0x2B, self._ybuf)
        self.write_cmd(0x2C)

    def fill(self, color):
        self.fill_rect(0, 0, self.width, self.height, color)

    def fill_rect(self, x, y, w, h, color):
        if w <= 0 or h <= 0:
            return
        if x >= self.width or y >= self.height:
            return
        if x < 0:
            w += x
            x = 0
        if y < 0:
            h += y
            y = 0
        if x + w > self.width:
            w = self.width - x
        if y + h > self.height:
            h = self.height - y
        if w <= 0 or h <= 0:
            return

        hi = (color >> 8) & 0xFF
        lo = color & 0xFF
        for i in range(0, len(self._color_chunk), 2):
            self._color_chunk[i] = hi
            self._color_chunk[i + 1] = lo

        total_pixels = w * h
        self.set_window(x, y, x + w - 1, y + h - 1)
        self._activate_spi()
        self.cs.value(0)
        self.dc.value(1)
        while total_pixels > 0:
            chunk_pixels = min(total_pixels, len(self._color_chunk) // 2)
            self.spi.write(memoryview(self._color_chunk)[:chunk_pixels * 2])
            total_pixels -= chunk_pixels
        self.cs.value(1)

    def pixel(self, x, y, color):
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return
        self.set_window(x, y, x, y)
        self._activate_spi()
        self.cs.value(0)
        self.dc.value(1)
        self.spi.write(bytearray([(color >> 8) & 0xFF, color & 0xFF]))
        self.cs.value(1)
