import framebuf


FONT_W = 8
FONT_H = 8


class _BaseOLED(framebuf.FrameBuffer):
    def __init__(self, width, height, i2c, addr=0x3C, external_vcc=False):
        self.width = width
        self.height = height
        self.i2c = i2c
        self.addr = addr
        self.external_vcc = external_vcc
        self.pages = self.height // 8
        self.buffer = bytearray(self.width * self.pages)
        super().__init__(self.buffer, self.width, self.height, framebuf.MONO_VLSB)
        self._cmd_buf = bytearray(2)

    def write_cmd(self, cmd):
        self._cmd_buf[0] = 0x80
        self._cmd_buf[1] = cmd
        self.i2c.writeto(self.addr, self._cmd_buf)

    def poweron(self):
        self.write_cmd(0xAF)

    def poweroff(self):
        self.write_cmd(0xAE)

    def contrast(self, contrast):
        self.write_cmd(0x81)
        self.write_cmd(contrast)

    def invert(self, enabled):
        self.write_cmd(0xA7 if enabled else 0xA6)

    def clear(self):
        self.fill(0)
        self.show()


class SSD1306_I2C(_BaseOLED):
    def __init__(self, width, height, i2c, addr=0x3C, external_vcc=False):
        self._frame = bytearray((width * (height // 8)) + 1)
        self._frame[0] = 0x40
        super().__init__(width, height, i2c, addr=addr, external_vcc=external_vcc)
        self.init_display()

    def init_display(self):
        for cmd in (
            0xAE,
            0x20,
            0x00,
            0x40,
            0xA1,
            0xC8,
            0x81,
            0xCF,
            0xA6,
            0xA8,
            self.height - 1,
            0xD3,
            0x00,
            0xD5,
            0x80,
            0xD9,
            0xF1 if not self.external_vcc else 0x22,
            0xDA,
            0x12 if self.height == 64 else 0x02,
            0xDB,
            0x40,
            0x8D,
            0x14 if not self.external_vcc else 0x10,
            0xAF,
        ):
            self.write_cmd(cmd)
        self.fill(0)
        self.show()

    def show(self):
        self.write_cmd(0x21)
        self.write_cmd(0x00)
        self.write_cmd(self.width - 1)
        self.write_cmd(0x22)
        self.write_cmd(0x00)
        self.write_cmd(self.pages - 1)
        self._frame[1:] = self.buffer
        self.i2c.writeto(self.addr, self._frame)


class SH1106_I2C(_BaseOLED):
    def __init__(self, width, height, i2c, addr=0x3C, external_vcc=False):
        self.column_offset = 2
        self._page_buf = bytearray(width + 1)
        self._page_buf[0] = 0x40
        super().__init__(width, height, i2c, addr=addr, external_vcc=external_vcc)
        self.init_display()

    def init_display(self):
        for cmd in (
            0xAE,
            0xD5,
            0x80,
            0xA8,
            self.height - 1,
            0xD3,
            0x00,
            0x40,
            0xAD,
            0x8B if not self.external_vcc else 0x8A,
            0xA1,
            0xC8,
            0xDA,
            0x12 if self.height == 64 else 0x02,
            0x81,
            0x80,
            0xD9,
            0x22 if self.external_vcc else 0xF1,
            0xDB,
            0x40,
            0xA4,
            0xA6,
            0xAF,
        ):
            self.write_cmd(cmd)
        self.fill(0)
        self.show()

    def show(self):
        for page in range(self.pages):
            self.write_cmd(0xB0 | page)
            self.write_cmd(0x00 | (self.column_offset & 0x0F))
            self.write_cmd(0x10 | ((self.column_offset >> 4) & 0x0F))
            start = page * self.width
            end = start + self.width
            self._page_buf[1:] = self.buffer[start:end]
            self.i2c.writeto(self.addr, self._page_buf)


def make_display(i2c, width=128, height=64, addr=0x3C, controller="sh1106"):
    # SH1106 is the validated RS-Core OLED controller.
    controller = (controller or "sh1106").lower()
    if controller == "ssd1306":
        return SSD1306_I2C(width, height, i2c, addr=addr)
    return SH1106_I2C(width, height, i2c, addr=addr)


class OLED:
    def __init__(
        self,
        i2c,
        width=128,
        height=64,
        addr=0x3C,
        controller="sh1106",
        contrast=255,
    ):
        self.display = make_display(i2c, width=width, height=height, addr=addr, controller=controller)
        self.width = width
        self.height = height
        self.controller = controller
        self.line_height = FONT_H
        self.char_width = FONT_W
        self._scratch = bytearray(8)
        self._scratch_fb = framebuf.FrameBuffer(self._scratch, 8, 8, framebuf.MONO_VLSB)
        self._last_bytes = bytearray(len(self.display.buffer))
        self._dirty = True
        self.display.contrast(contrast)
        self.clear()

    def clear(self, show=True):
        self.display.fill(0)
        self._dirty = True
        if show:
            self.show(force=True)
        return self

    def show(self, force=False):
        if force or self._dirty or self.display.buffer != self._last_bytes:
            self.display.show()
            self._last_bytes[:] = self.display.buffer
            self._dirty = False
        return self

    def invert(self, enabled=True, show=True):
        self.display.invert(enabled)
        if show:
            self.show(force=True)
        return self

    def fill(self, color=0):
        self.display.fill(color)
        self._dirty = True
        return self

    def pixel(self, x, y, color=1):
        self.display.pixel(int(x), int(y), color)
        self._dirty = True
        return self

    def hline(self, x, y, w, color=1):
        self.display.hline(int(x), int(y), int(w), color)
        self._dirty = True
        return self

    def vline(self, x, y, h, color=1):
        self.display.vline(int(x), int(y), int(h), color)
        self._dirty = True
        return self

    def rect(self, x, y, w, h, color=1, fill=False):
        if fill:
            self.display.fill_rect(int(x), int(y), int(w), int(h), color)
        else:
            self.display.rect(int(x), int(y), int(w), int(h), color)
        self._dirty = True
        return self

    def line(self, x0, y0, x1, y1, color=1):
        self.display.line(int(x0), int(y0), int(x1), int(y1), color)
        self._dirty = True
        return self

    def text_width(self, text, scale=1, spacing=0):
        if not text:
            return 0
        return (len(text) * FONT_W * scale) + (max(0, len(text) - 1) * spacing)

    def _wrap_words(self, text, max_chars):
        if not text:
            return [""]
        lines = []
        for raw_line in str(text).split("\n"):
            words = raw_line.split(" ")
            current = ""
            for word in words:
                if not word:
                    continue
                candidate = word if not current else current + " " + word
                if len(candidate) <= max_chars:
                    current = candidate
                    continue
                if current:
                    lines.append(current)
                while len(word) > max_chars:
                    lines.append(word[:max_chars])
                    word = word[max_chars:]
                current = word
            lines.append(current)
        return lines or [""]

    def _text_x(self, text, align, scale, x, width, spacing=0):
        text_w = self.text_width(text, scale=scale, spacing=spacing)
        if align == "center":
            return x + max(0, (width - text_w) // 2)
        if align == "right":
            return x + max(0, width - text_w)
        return x

    def _draw_scaled_char(self, char, x, y, scale=1, color=1):
        self._scratch_fb.fill(0)
        self._scratch_fb.text(char, 0, 0, 1)
        for sy in range(FONT_H):
            for sx in range(FONT_W):
                if self._scratch_fb.pixel(sx, sy):
                    dx = x + (sx * scale)
                    dy = y + (sy * scale)
                    self.display.fill_rect(dx, dy, scale, scale, color)
        self._dirty = True

    def text(self, text, x=0, y=0, scale=1, color=1, spacing=0):
        if scale <= 1:
            cursor_x = int(x)
            for char in str(text):
                self.display.text(char, cursor_x, int(y), color)
                cursor_x += FONT_W + spacing
            self._dirty = True
            return self

        cursor_x = int(x)
        for char in str(text):
            self._draw_scaled_char(char, cursor_x, int(y), scale=scale, color=color)
            cursor_x += (FONT_W * scale) + spacing
        return self

    def text_line(self, text, y, align="left", scale=1, color=1, x=0, width=None, spacing=0):
        width = self.width - x if width is None else width
        draw_x = self._text_x(str(text), align, scale, x, width, spacing=spacing)
        return self.text(str(text), draw_x, y, scale=scale, color=color, spacing=spacing)

    def multiline_text(
        self,
        text,
        x=0,
        y=0,
        width=None,
        align="left",
        scale=1,
        color=1,
        spacing=0,
        line_gap=0,
        wrap=True,
        max_lines=None,
    ):
        width = self.width - x if width is None else width
        max_chars = max(1, width // max(1, FONT_W * scale))
        lines = self._wrap_words(str(text), max_chars) if wrap else str(text).split("\n")
        if max_lines is not None:
            lines = lines[:max_lines]
        line_step = (FONT_H * scale) + line_gap
        for index, line_text in enumerate(lines):
            self.text_line(
                line_text,
                y + (index * line_step),
                align=align,
                scale=scale,
                color=color,
                x=x,
                width=width,
                spacing=spacing,
            )
        return self

    def label(
        self,
        text,
        x=0,
        y=0,
        width=None,
        height=None,
        align="center",
        scale=1,
        padding=2,
        invert=False,
        border=True,
    ):
        width = self.width - x if width is None else width
        text_h = FONT_H * scale
        height = (text_h + (padding * 2)) if height is None else height
        bg = 1 if invert else 0
        fg = 0 if invert else 1
        self.rect(x, y, width, height, bg, fill=True)
        if border:
            self.rect(x, y, width, height, fg, fill=False)
        text_y = y + max(0, (height - text_h) // 2)
        self.text_line(text, text_y, align=align, scale=scale, color=fg, x=x + padding, width=max(0, width - (padding * 2)))
        return self

    def progress_bar(self, x, y, width, height, value, maximum=100, border=True, show_percent=False):
        maximum = max(1, maximum)
        value = min(max(0, value), maximum)
        fill_w = int(((width - 2) * value) / maximum) if width > 2 else 0
        if border:
            self.rect(x, y, width, height, 1, fill=False)
            inner_x = x + 1
            inner_y = y + 1
            inner_w = max(0, width - 2)
            inner_h = max(0, height - 2)
        else:
            inner_x = x
            inner_y = y
            inner_w = width
            inner_h = height
        self.rect(inner_x, inner_y, inner_w, inner_h, 0, fill=True)
        if fill_w > 0:
            self.rect(inner_x, inner_y, min(fill_w, inner_w), inner_h, 1, fill=True)
        if show_percent:
            pct = str(int((value * 100) / maximum)) + "%"
            self.text_line(pct, y + max(0, (height - FONT_H) // 2), align="center", x=x, width=width)
        return self

    def header(self, title, subtitle=None):
        self.clear(show=False)
        self.label(title, x=0, y=0, width=self.width, height=14, invert=True, border=False)
        if subtitle:
            self.text_line(subtitle, 18, align="center")
        return self

    def message(self, title, body=None, footer=None, title_scale=2, show=True):
        self.clear(show=False)
        self.text_line(title, 0, align="center", scale=title_scale)
        body_y = (FONT_H * title_scale) + 6
        if body:
            self.multiline_text(body, x=4, y=body_y, width=self.width - 8, align="center", line_gap=1)
        if footer:
            self.text_line(footer, self.height - FONT_H, align="center")
        if show:
            self.show()
        return self

    def status_screen(self, state, lines=None, footer=None, progress=None, invert_header=True, show=True):
        self.clear(show=False)
        self.label(state, x=0, y=0, width=self.width, height=14, invert=invert_header, border=False)
        y = 18
        if lines:
            for line_text in lines:
                self.text_line(str(line_text), y, align="left", x=2, width=self.width - 4)
                y += FONT_H + 2
        if progress is not None:
            value, maximum = progress
            self.progress_bar(4, self.height - 14, self.width - 8, 10, value, maximum, show_percent=True)
        elif footer:
            self.text_line(str(footer), self.height - FONT_H, align="center")
        if show:
            self.show()
        return self

    def metrics_screen(self, title, metrics, footer=None, show=True):
        self.clear(show=False)
        self.label(title, x=0, y=0, width=self.width, height=14, invert=True, border=False)
        y = 18
        for key, value in metrics:
            left = str(key)
            right = str(value)
            self.text(left, 2, y)
            self.text_line(right, y, align="right", x=2, width=self.width - 4)
            y += FONT_H + 2
            if y > self.height - (FONT_H * 2):
                break
        if footer:
            self.text_line(str(footer), self.height - FONT_H, align="center")
        if show:
            self.show()
        return self


def hello_demo(i2c, width=128, height=64, addr=0x3C, controller="sh1106", text="HELLO"):
    display = make_display(i2c, width=width, height=height, addr=addr, controller=controller)
    display.fill(0)
    x = 0
    try:
        x = max(0, (width - (len(text) * FONT_W)) // 2)
    except:
        pass
    display.text(str(text), x, 16, 1)
    display.text(str(controller).upper(), 0, 32, 1)
    display.show()
    return display
