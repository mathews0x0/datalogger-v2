import time
import framebuf
import machine
import ujson
import os

from drivers.ili9341 import ILI9341
from drivers.xpt2046 import XPT2046


TOUCH_CAL_PATH = "/data/metadata/touch.json"
DEFAULT_TOUCH_CAL = {
    "xmin": 303,
    "xmax": 1842,
    "ymin": 278,
    "ymax": 1832,
    "width": 320,
    "height": 240,
    "swap_xy": True,
    "invert_x": True,
    "invert_y": True,
}


class TFTBootUI:
    def __init__(
        self,
        spi_bus=1,
        pin_sck=15,
        pin_mosi=16,
        pin_miso=9,
        pin_tft_cs=5,
        pin_tft_dc=6,
        pin_touch_cs=7,
    ):
        self.width = 320
        self.height = 240
        self._spi = machine.SPI(
            spi_bus,
            baudrate=40_000_000,
            polarity=0,
            phase=0,
            sck=machine.Pin(pin_sck),
            mosi=machine.Pin(pin_mosi),
            miso=machine.Pin(pin_miso),
        )
        self._display = ILI9341(
            spi=self._spi,
            cs=machine.Pin(pin_tft_cs, machine.Pin.OUT),
            dc=machine.Pin(pin_tft_dc, machine.Pin.OUT),
            rst=None,
            rotation=1,
            baudrate=40_000_000,
        )
        self._touch = XPT2046(
            spi=self._spi,
            cs=machine.Pin(pin_touch_cs, machine.Pin.OUT),
            irq=None,
            baudrate=1_000_000,
            calibration=self._load_touch_calibration(),
        )
        self._buf = bytearray(self.width * self.height * 2)
        self._fb = framebuf.FrameBuffer(self._buf, self.width, self.height, framebuf.RGB565)
        self._mono_buf = bytearray(self.width)
        self._mono_fb = framebuf.FrameBuffer(self._mono_buf, self.width, 8, framebuf.MONO_VLSB)
        self._tx_buf = bytearray(512)
        self._last_touch_ms = 0
        self._battery_pct = None
        self._sd_pct = None
        self._sd_ok = None
        self._ram_used_mb = None
        self._ram_total_mb = None
        self._touch_mode = None
        self._sync_started_ms = None
        self._sync_last_bytes = 0
        self._sync_last_ms = 0
        self._sync_rate_bps = 0.0
        self._sync_eta_s = None
        self._last_render_key = None
        self._last_render_ms = 0
        self._touch_debounce_ms = 180
        self._sync_upload_screen_key = None
        self._sync_upload_values = None
        self._c_bg = 0x0000
        self._c_panel = 0x18C3
        self._c_panel_alt = 0x2945
        self._c_accent = 0xE283
        self._c_accent_soft = 0xFB46
        self._c_text = 0xFFFF
        self._c_text_dim = 0xA514
        self._c_text_muted = 0x632C
        self._c_good = 0x068D
        self._c_warn = 0xFD00
        self._c_bad = 0xF9CC
        self.clear()

    def _load_touch_calibration(self):
        try:
            with open(TOUCH_CAL_PATH, "r") as f:
                data = ujson.load(f)
            cal = DEFAULT_TOUCH_CAL.copy()
            for key in ("xmin", "xmax", "ymin", "ymax", "width", "height"):
                if key in data:
                    cal[key] = int(data[key])
            for key in ("swap_xy", "invert_x", "invert_y"):
                if key in data:
                    cal[key] = bool(data[key])
            return cal
        except Exception:
            return DEFAULT_TOUCH_CAL.copy()

    def has_touch_calibration(self):
        try:
            os.stat(TOUCH_CAL_PATH)
            return True
        except OSError:
            return False

    def _save_touch_calibration(self, cal):
        try:
            try:
                os.mkdir("/data")
            except OSError:
                pass
            try:
                os.mkdir("/data/metadata")
            except OSError:
                pass
            with open(TOUCH_CAL_PATH, "w") as f:
                ujson.dump(cal, f)
            self._touch.calibration = cal
            return True
        except Exception as e:
            print("[TFT] Touch calibration save failed:", e)
            return False

    def set_context(self, battery_pct=None, sd_ok=None, sd_pct=None, ram_used_mb=None, ram_total_mb=None):
        if battery_pct is not None:
            try:
                self._battery_pct = max(0, min(100, int(battery_pct)))
            except Exception:
                self._battery_pct = None
        if sd_ok is not None:
            self._sd_ok = bool(sd_ok)
        if sd_pct is not None:
            try:
                self._sd_pct = max(0, min(100, int(sd_pct)))
            except Exception:
                self._sd_pct = None
        if ram_used_mb is not None:
            try:
                self._ram_used_mb = max(0.0, float(ram_used_mb))
            except Exception:
                self._ram_used_mb = None
        if ram_total_mb is not None:
            try:
                self._ram_total_mb = max(0.0, float(ram_total_mb))
            except Exception:
                self._ram_total_mb = None

    def clear(self, color=0x0000):
        self._fb.fill(color)
        self._last_render_key = None
        self.show()

    def _skip_render(self, key, min_interval_ms=250):
        now = time.ticks_ms()
        if key == self._last_render_key and time.ticks_diff(now, self._last_render_ms) < min_interval_ms:
            return True
        self._last_render_key = key
        self._last_render_ms = now
        return False

    def show(self):
        self._display.set_window(0, 0, self.width - 1, self.height - 1)
        self._display._activate_spi()
        self._display.cs.value(0)
        self._display.dc.value(1)
        # MicroPython's framebuf.RGB565 byte order can differ from what the
        # ILI9341 expects over SPI on this board. Swap each 16-bit pixel before
        # transfer so orange/amber UI colors land correctly on-panel.
        src = self._buf
        tx = self._tx_buf
        src_len = len(src)
        tx_len = len(tx)
        for start in range(0, src_len, tx_len):
            chunk_len = tx_len
            if start + chunk_len > src_len:
                chunk_len = src_len - start
            if chunk_len & 1:
                chunk_len -= 1
            i = 0
            while i < chunk_len:
                tx[i] = src[start + i + 1]
                tx[i + 1] = src[start + i]
                i += 2
            self._spi.write(memoryview(tx)[:chunk_len])
        self._display.cs.value(1)

    def _show_region(self, x, y, w, h):
        if w <= 0 or h <= 0:
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
        self._display.set_window(x, y, x + w - 1, y + h - 1)
        self._display._activate_spi()
        self._display.cs.value(0)
        self._display.dc.value(1)
        tx = self._tx_buf
        tx_len = len(tx)
        for row in range(y, y + h):
            src_start = ((row * self.width) + x) * 2
            src_end = src_start + (w * 2)
            pos = src_start
            while pos < src_end:
                chunk_len = min(tx_len, src_end - pos)
                if chunk_len & 1:
                    chunk_len -= 1
                i = 0
                while i < chunk_len:
                    tx[i] = self._buf[pos + i + 1]
                    tx[i + 1] = self._buf[pos + i]
                    i += 2
                self._spi.write(memoryview(tx)[:chunk_len])
                pos += chunk_len
        self._display.cs.value(1)

    def _text(self, x, y, text, color=0xFFFF):
        self._fb.text(str(text), int(x), int(y), color)

    def _text_scaled(self, x, y, text, scale=2, color=0xFFFF):
        # Keep the built-in bitmap font at native size only. Enlarging the
        # 8x8 source font is what made the UI look pixelated.
        self._text(x, y, text, color)

    def _centered_scaled(self, y, text, scale=2, color=0xFFFF):
        width = len(str(text)) * 8
        x = max(0, (self.width - width) // 2)
        self._text(x, y, text, color)

    def _big_value_width(self, text, scale=4):
        w = 0
        for ch in str(text):
            if ch.isdigit():
                w += 5 * scale
            elif ch in (":", "."):
                w += 2 * scale
            elif ch in ("/", "%"):
                w += 4 * scale
            elif ch == "-":
                w += 4 * scale
            else:
                w += 5 * scale
        return max(0, w - scale)

    def _big_value(self, x, y, text, scale=4, color=None, shadow=True):
        color = self._c_accent if color is None else color
        text = str(text)
        if shadow:
            self._big_value(x + 1, y + 1, text, scale=scale, color=self._c_bg, shadow=False)
        cx = int(x)
        for ch in text:
            cx += self._big_char(cx, int(y), ch, int(scale), color)
            cx += int(scale)

    def _centered_big_value(self, y, text, scale=4, color=None):
        x = max(0, (self.width - self._big_value_width(text, scale)) // 2)
        self._big_value(x, y, text, scale=scale, color=color)

    def _big_char(self, x, y, ch, s, color):
        segs = {
            "0": "abcdef",
            "1": "bc",
            "2": "abged",
            "3": "abgcd",
            "4": "fgbc",
            "5": "afgcd",
            "6": "afgecd",
            "7": "abc",
            "8": "abcdefg",
            "9": "abfgcd",
        }
        t = max(2, s)
        w = 4 * s
        h = 7 * s
        if ch in segs:
            active = segs[ch]
            if "a" in active:
                self._fb.fill_rect(x + t, y, w - (2 * t), t, color)
            if "b" in active:
                self._fb.fill_rect(x + w - t, y + t, t, (h // 2) - t, color)
            if "c" in active:
                self._fb.fill_rect(x + w - t, y + (h // 2), t, (h // 2) - t, color)
            if "d" in active:
                self._fb.fill_rect(x + t, y + h - t, w - (2 * t), t, color)
            if "e" in active:
                self._fb.fill_rect(x, y + (h // 2), t, (h // 2) - t, color)
            if "f" in active:
                self._fb.fill_rect(x, y + t, t, (h // 2) - t, color)
            if "g" in active:
                self._fb.fill_rect(x + t, y + (h // 2) - (t // 2), w - (2 * t), t, color)
            return 5 * s
        if ch == ":":
            self._fb.fill_rect(x, y + (2 * s), t, t, color)
            self._fb.fill_rect(x, y + (5 * s), t, t, color)
            return 2 * s
        if ch == ".":
            self._fb.fill_rect(x, y + (6 * s), t, t, color)
            return 2 * s
        if ch == "-":
            self._fb.fill_rect(x, y + (3 * s), 3 * s, t, color)
            return 4 * s
        if ch == "/":
            for i in range(0, 7 * s, max(1, s // 2)):
                self._fb.fill_rect(x + (3 * s) - ((i * 3) // 7), y + i, t, max(1, s // 2), color)
            return 4 * s
        if ch == "%":
            self._fb.fill_rect(x, y, t, t, color)
            self._fb.fill_rect(x + (3 * s), y + (6 * s), t, t, color)
            for i in range(0, 7 * s, max(1, s // 2)):
                self._fb.fill_rect(x + (3 * s) - ((i * 3) // 7), y + i, t, max(1, s // 2), color)
            return 4 * s
        glyphs = {
            "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
            "m": ("00000", "00000", "11010", "10101", "10101", "10101", "10101"),
            "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
            "k": ("10000", "10000", "10010", "10100", "11000", "10100", "10010"),
            "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
            "s": ("00000", "00000", "01110", "10000", "01110", "00001", "11110"),
        }
        glyph = glyphs.get(ch)
        if glyph:
            dot = max(1, s - 1)
            for gy, row in enumerate(glyph):
                for gx, bit in enumerate(row):
                    if bit == "1":
                        self._fb.fill_rect(x + (gx * s), y + (gy * s), dot, dot, color)
            return 5 * s
        self._text(x, y + s, ch, color)
        return 8

    def _truncate_text(self, text, max_chars):
        text = str(text)
        if len(text) <= max_chars:
            return text
        if max_chars <= 3:
            return text[:max_chars]
        return text[: max_chars - 3] + "..."

    def _draw_panel(self, x, y, w, h, border=None, fill=None):
        border = self._c_accent if border is None else border
        fill = self._c_panel if fill is None else fill
        self._fb.fill_rect(x, y, w, h, fill)
        self._fb.rect(x, y, w, h, border)

    def _draw_mask(self, x, y, w, h, mask, mask_w, mask_h, color, glow=None):
        if not mask or mask_w <= 0 or mask_h <= 0 or w <= 0 or h <= 0:
            return
        mask_len = len(mask)
        if glow is not None:
            for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                self._draw_mask(x + ox, y + oy, w, h, mask, mask_w, mask_h, glow, glow=None)
        for dy in range(h):
            sy = (dy * mask_h) // h
            row_base = sy * mask_w
            for dx in range(w):
                sx = (dx * mask_w) // w
                bit_index = row_base + sx
                byte_index = bit_index >> 3
                if byte_index >= mask_len:
                    continue
                if mask[byte_index] & (0x80 >> (bit_index & 7)):
                    self._fb.pixel(x + dx, y + dy, color)

    def _brand_wordmark(self, y):
        # Approximate the web wordmark: clean white title with a restrained
        # RaceSense orange glow, centered in the boot panel.
        word = "RaceSense"
        x = (self.width - (len(word) * 8)) // 2
        self._text(x + 1, y + 1, word, self._c_accent)
        self._text(x, y, word, self._c_text)
        self._fb.fill_rect(78, y + 14, 164, 2, self._c_accent)
        self._text(116, y + 24, "ride faster. ride smarter.", self._c_text_muted)

    def _title_block(self, eyebrow, title, subtitle="", panel_y=48, panel_h=168):
        self._fb.fill(self._c_bg)
        self._header(eyebrow)
        self._draw_panel(12, panel_y, 296, panel_h, border=self._c_panel_alt, fill=self._c_bg)
        title_scale = 3 if len(str(title)) <= 16 else 2
        self._centered_scaled(panel_y + 18, title, scale=title_scale, color=self._c_text)
        if subtitle:
            self._centered_scaled(panel_y + 18 + (title_scale * 12), subtitle, scale=1, color=self._c_text_muted)

    def _status_pill(self, x, y, w, label, value, accent=None):
        self._fb.fill_rect(x, y, w, 28, self._c_panel)
        self._fb.rect(x, y, w, 28, self._c_panel_alt)
        self._text(x + 8, y + 5, self._truncate_text(label, 8), self._c_text_muted)
        value_color = self._c_text if accent is None else accent
        self._text(x + 8, y + 16, self._truncate_text(value, max(4, (w - 16) // 8)), value_color)

    def _label_value(self, x, y, label, value, w=0):
        label = self._truncate_text(label, 10)
        value = self._truncate_text(value, 18 if w <= 0 else max(6, w // 8))
        self._text(x, y, label, self._c_text_muted)
        if w > 0:
            value_x = x + w - (len(value) * 8)
            if value_x < x + 40:
                value_x = x + 40
        else:
            value_x = x + 44
        self._text(value_x, y, value, self._c_text)

    def _progress_bar(self, x, y, w, h, pct, fill=None, border=None, bg=None):
        pct = max(0, min(100, int(pct or 0)))
        border = self._c_accent_soft if border is None else border
        fill = self._c_accent if fill is None else fill
        bg = self._c_panel_alt if bg is None else bg
        self._fb.rect(x, y, w, h, border)
        self._fb.fill_rect(x + 1, y + 1, max(0, w - 2), max(0, h - 2), bg)
        inner_w = max(0, w - 2)
        fill_w = (inner_w * pct) // 100
        if fill_w > 0:
            self._fb.fill_rect(x + 1, y + 1, fill_w, max(0, h - 2), fill)

    def _format_bytes_compact(self, value):
        try:
            value = int(value)
        except Exception:
            return "0B"
        if value >= 1024 * 1024:
            return "%.1fM" % (value / (1024.0 * 1024.0))
        if value >= 1024:
            return "%.0fK" % (value / 1024.0)
        return "%dB" % value

    def _format_bytes_pair(self, current, total):
        return "%s/%s" % (self._format_bytes_compact(current), self._format_bytes_compact(total))

    def _format_eta(self, seconds):
        if seconds is None:
            return "--:--"
        seconds = max(0, int(seconds))
        minutes = seconds // 60
        secs = seconds % 60
        if minutes >= 100:
            return "%dm" % minutes
        return "%02d:%02d" % (minutes, secs)

    def _reset_sync_metrics(self):
        self._sync_started_ms = None
        self._sync_last_bytes = 0
        self._sync_last_ms = 0
        self._sync_rate_bps = 0.0
        self._sync_eta_s = None

    def _reset_sync_upload_screen(self):
        self._sync_upload_screen_key = None
        self._sync_upload_values = None

    def _sync_stats(self, global_current, global_total):
        try:
            global_current = int(global_current or 0)
            global_total = int(global_total or 0)
        except Exception:
            return 0, "--:--", "--/s"

        now = time.ticks_ms()
        if global_current <= 0 or global_total <= 0:
            self._reset_sync_metrics()
            return 0, "--:--", "--/s"
        if self._sync_started_ms is None or global_current < self._sync_last_bytes:
            self._sync_started_ms = now
            self._sync_last_bytes = global_current
            self._sync_last_ms = now
            self._sync_rate_bps = 0.0
            self._sync_eta_s = None

        delta_bytes = global_current - self._sync_last_bytes
        delta_ms = time.ticks_diff(now, self._sync_last_ms)
        if delta_bytes > 0 and delta_ms > 250:
            inst_rate = (delta_bytes * 1000.0) / float(delta_ms)
            if self._sync_rate_bps <= 0:
                self._sync_rate_bps = inst_rate
            else:
                self._sync_rate_bps = (self._sync_rate_bps * 0.72) + (inst_rate * 0.28)
            remaining = max(0, global_total - global_current)
            if self._sync_rate_bps > 1.0:
                self._sync_eta_s = remaining / self._sync_rate_bps
            self._sync_last_bytes = global_current
            self._sync_last_ms = now

        pct = int((global_current * 100) / global_total) if global_total > 0 else 0
        if pct >= 100:
            self._sync_eta_s = 0
        eta_text = self._format_eta(self._sync_eta_s)
        rate_text = "--/s"
        if self._sync_rate_bps > 1.0:
            rate_text = self._format_bytes_compact(int(self._sync_rate_bps)) + "/s"
        return pct, eta_text, rate_text

    def _button(self, x, y, w, h, label, fill, fg=0xFFFF):
        self._fb.fill_rect(x, y, w, h, fill)
        self._fb.rect(x, y, w, h, self._c_text_dim)
        tx = x + max(4, (w - (len(label) * 8)) // 2)
        ty = y + max(4, (h - 8) // 2)
        self._text(tx, ty, label, fg)

    def _draw_heart(self, cx, cy, color, scale=8):
        # Blocky but readable at TFT resolution; about 1 inch on this panel.
        rows = (
            "01100110",
            "11111111",
            "11111111",
            "11111111",
            "01111110",
            "00111100",
            "00011000",
        )
        s = scale
        x0 = cx - ((8 * s) // 2)
        y0 = cy - ((7 * s) // 2)
        for yy, row in enumerate(rows):
            for xx, bit in enumerate(row):
                if bit == "1":
                    self._fb.fill_rect(x0 + xx * s, y0 + yy * s, s - 1, s - 1, color)

    def _draw_heartbeat_frame(self, color, scale=8):
        self._fb.fill_rect(88, 76, 144, 72, self._c_panel)
        self._draw_heart(160, 112, color, scale=scale)
        self._show_region(88, 76, 144, 72)

    def _draw_target(self, x, y, label, index, total):
        self._fb.fill(self._c_bg)
        self._header("CALIBRATE")
        self._centered_scaled(50, "Touch target", scale=2, color=self._c_text)
        self._centered_scaled(76, "%d/%d" % (index, total), scale=2, color=self._c_text_muted)
        self._fb.fill_rect(x - 16, y - 1, 33, 3, self._c_accent)
        self._fb.fill_rect(x - 1, y - 16, 3, 33, self._c_accent)
        self._fb.rect(x - 10, y - 10, 21, 21, self._c_text_dim)
        self._centered_scaled(206, label, scale=1, color=self._c_text_muted)
        self.show()

    def _wait_touch_release(self, timeout_ms=1800):
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
            if not self._touch.touched():
                return
            time.sleep_ms(25)

    def _collect_calibration_sample(self, timeout_ms=12000):
        start = time.ticks_ms()
        values_x = []
        values_y = []
        values_z = []
        while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
            raw = self._touch.read_raw(samples=2, _skip_touch_check=True)
            if self._touch._looks_pressed(raw):
                values_x.append(raw["x"])
                values_y.append(raw["y"])
                values_z.append(raw["z"])
                if len(values_x) >= 10:
                    break
            elif values_x:
                break
            time.sleep_ms(18)
        self._wait_touch_release()
        if len(values_x) < 3:
            return None
        values_x.sort()
        values_y.sort()
        values_z.sort()
        mid = len(values_x) // 2
        return {"x": values_x[mid], "y": values_y[mid], "z": values_z[mid]}

    def _score_calibration(self, samples, swap_xy, invert_x, invert_y):
        src_x = []
        src_y = []
        dst_x = []
        dst_y = []
        for sample, tx, ty in samples:
            rx = sample["x"]
            ry = sample["y"]
            if swap_xy:
                rx, ry = ry, rx
            src_x.append(rx)
            src_y.append(ry)
            dst_x.append(tx)
            dst_y.append(ty)
        xmin = min(src_x)
        xmax = max(src_x)
        ymin = min(src_y)
        ymax = max(src_y)
        if xmax <= xmin or ymax <= ymin:
            return None
        err = 0
        for i in range(len(samples)):
            mx = int((src_x[i] - xmin) * (self.width - 1) / (xmax - xmin))
            my = int((src_y[i] - ymin) * (self.height - 1) / (ymax - ymin))
            if invert_x:
                mx = (self.width - 1) - mx
            if invert_y:
                my = (self.height - 1) - my
            dx = mx - dst_x[i]
            dy = my - dst_y[i]
            err += (dx * dx) + (dy * dy)
        return err, {
            "xmin": xmin,
            "xmax": xmax,
            "ymin": ymin,
            "ymax": ymax,
            "width": self.width,
            "height": self.height,
            "swap_xy": swap_xy,
            "invert_x": invert_x,
            "invert_y": invert_y,
        }

    def _build_calibration(self, samples):
        best = None
        for swap_xy in (False, True):
            for invert_x in (False, True):
                for invert_y in (False, True):
                    scored = self._score_calibration(samples, swap_xy, invert_x, invert_y)
                    if scored is None:
                        continue
                    if best is None or scored[0] < best[0]:
                        best = scored
        return best[1] if best else None

    def calibrate_touch(self):
        self._touch_mode = None
        points = (
            ("top left", 24, 24),
            ("top right", 295, 24),
            ("bottom right", 295, 215),
            ("bottom left", 24, 215),
            ("center", 160, 120),
        )
        samples = []
        for idx, item in enumerate(points):
            label, x, y = item
            self._draw_target(x, y, label, idx + 1, len(points))
            sample = self._collect_calibration_sample()
            if sample is None:
                self.show_message("CALIBRATE", "Touch missed\nTry again", "Calibration not saved")
                time.sleep_ms(900)
                return False
            print("[TFT] cal sample", label, sample)
            samples.append((sample, x, y))
            time.sleep_ms(250)
        cal = self._build_calibration(samples)
        if not cal or not self._save_touch_calibration(cal):
            self.show_message("CALIBRATE", "Failed", "Calibration not saved")
            time.sleep_ms(900)
            return False
        print("[TFT] touch calibration saved:", cal)
        self.show_message("CALIBRATE", "Saved", "Touch setup complete")
        time.sleep_ms(900)
        return True

    def _header(self, title, color=None):
        color = self._c_accent if color is None else color
        self._fb.fill_rect(0, 0, self.width, 34, color)
        self._centered_scaled(7, title, scale=2, color=self._c_bg)
        if self._battery_pct is not None:
            self._text(8, 24, "BAT %d%%" % self._battery_pct, self._c_bg)
        if self._ram_used_mb is not None and self._ram_total_mb is not None:
            ram = "RAM %.1f/%.1f" % (self._ram_used_mb, self._ram_total_mb)
            x = max(88, (self.width - (len(ram) * 8)) // 2)
            self._text(x, 24, ram, self._c_bg)
        if self._sd_ok is not None:
            sd_label = "SD --"
            if self._sd_ok:
                sd_label = "SD %d%%" % (self._sd_pct if self._sd_pct is not None else 0)
            self._text(self.width - 56, 24, sd_label, self._c_bg if self._sd_ok else self._c_bg)

    def _status_card(self, x, y, label, ok):
        color = 0x07E0 if ok else 0xF800
        self._fb.rect(x, y, 94, 66, color)
        self._text_scaled(x + 10, y + 10, label, scale=2, color=0xFFFF)
        self._text_scaled(x + 20, y + 38, "OK" if ok else "ERR", scale=2, color=color)

    def show_startup_logo(self):
        self._fb.fill(self._c_bg)
        self._header("RS-CORE")
        self._draw_panel(12, 48, 296, 122, border=self._c_panel_alt, fill=self._c_bg)
        self._text(28, 62, "MOTORCYCLE TELEMETRY", self._c_text_muted)
        self._brand_wordmark(86)
        self._draw_panel(22, 182, 276, 38, border=self._c_panel_alt, fill=self._c_panel)
        self._text(34, 191, "RS-CORE V2", self._c_text_muted)
        self._text(34, 203, "Booting telemetry stack", self._c_text)
        self._progress_bar(34, 214, 252, 6, 38, fill=self._c_accent, border=self._c_panel_alt, bg=self._c_panel_alt)
        self.show()
        return True

    def show_message(self, title, body="", footer=""):
        self._touch_mode = None
        key = ("msg", str(title), str(body), str(footer))
        if self._skip_render(key, 700):
            return True
        self._fb.fill(self._c_bg)
        self._header(title)
        lines = [line for line in str(body).split("\n") if line]
        y = 52
        for line in lines[:6]:
            self._centered_scaled(y, self._truncate_text(line, 20), scale=2, color=self._c_text)
            y += 22
        if footer:
            self._centered_scaled(self.height - 24, self._truncate_text(footer, 34), scale=1, color=self._c_text_muted)
        self.show()
        return True

    def show_boot(self, stage, sd_ok=None, imu_ok=None, gps_ok=None, gps_baud=None, gps_rate_hz=None, storage_info=None, force=False):
        self._fb.fill(self._c_bg)
        self._header("BOOT")
        self._text(28, 54, "DEVICE STATUS", self._c_text_muted)
        self._centered_scaled(72, stage, scale=3 if len(str(stage)) <= 16 else 2, color=self._c_text)
        self._status_pill(22, 118, 86, "SD", "Mounted" if sd_ok else "Check", self._c_accent if sd_ok else self._c_bad)
        self._status_pill(117, 118, 86, "IMU", "Ready" if imu_ok else "Check", self._c_accent if imu_ok else self._c_bad)
        self._status_pill(212, 118, 86, "GPS", "10Hz lock" if gps_ok else "Waiting", self._c_accent if gps_ok else self._c_bad)
        self._draw_panel(22, 170, 276, 46, border=self._c_panel_alt, fill=self._c_panel)
        detail = "Bringing up display and storage"
        if gps_baud is not None and gps_rate_hz is not None:
            detail = "GPS %s / %sHz" % (gps_baud, gps_rate_hz)
        self._text(34, 184, self._truncate_text(detail, 30), self._c_text_muted)
        progress = 34
        if sd_ok is not None:
            progress += 22
        if imu_ok is not None:
            progress += 22
        if gps_ok is not None and gps_ok:
            progress += 22
        self._progress_bar(34, 200, 252, 8, progress, fill=self._c_accent, border=self._c_panel_alt, bg=self._c_panel_alt)
        self.show()
        return True

    def show_decision(self, sd_ok, imu_ok, gps_ok, gps_sentences=0, countdown_ms=None, paused=False):
        self._touch_mode = "decision"
        countdown_s = -1
        if countdown_ms is not None:
            countdown_s = max(0, int(countdown_ms) // 1000)
        key = ("decision", bool(sd_ok), bool(imu_ok), bool(gps_ok), int(gps_sentences or 0), countdown_s, bool(paused))
        if self._skip_render(key, 250):
            return True
        self._fb.fill(self._c_bg)
        self._header("READY")
        self._text(22, 54, "SYNC NOW?", self._c_text_muted)
        headline = "Timer paused" if paused else ("Auto log in %02ds" % countdown_s if countdown_ms is not None and gps_ok else ("Waiting for GPS %d/5" % gps_sentences if not gps_ok else "Sync or start logging"))
        self._centered_scaled(72, headline, scale=3 if len(headline) <= 16 else 2, color=self._c_text if gps_ok or paused else self._c_bad)
        self._status_pill(22, 118, 64, "SD", "OK" if sd_ok else "ERR", self._c_accent if sd_ok else self._c_bad)
        self._status_pill(94, 118, 64, "IMU", "OK" if imu_ok else "ERR", self._c_accent if imu_ok else self._c_bad)
        self._status_pill(166, 118, 76, "GPS", "LOCKED" if gps_ok else "WAIT", self._c_accent if gps_ok else self._c_bad)
        self._status_pill(250, 118, 48, "TRK", "RDY", self._c_accent)
        self._draw_panel(22, 154, 276, 44, border=self._c_panel_alt, fill=self._c_panel)
        self._text(32, 162, "Choose mode", self._c_text_muted)
        self._text(192, 162, "Touch center", self._c_text_dim)
        self._button(34, 170, 76, 28, "SYNC", self._c_accent, self._c_bg)
        self._button(118, 170, 86, 28, "SET", self._c_panel_alt, self._c_text)
        self._button(212, 170, 76, 28, "LOG", self._c_panel_alt, self._c_text)
        self._draw_panel(22, 206, 276, 24, border=self._c_panel_alt, fill=self._c_panel)
        hint = "Sync cloud data, settings, or start logging"
        if not gps_ok:
            hint = "GPS lock required before auto logging"
        self._text(28, 214, self._truncate_text(hint, 33), self._c_text_muted)
        self.show()
        return True

    def show_settings(self, ssid=""):
        self._touch_mode = "settings"
        key = ("settings", str(ssid))
        if self._skip_render(key, 250):
            return True
        self._fb.fill(self._c_bg)
        self._header("SETTINGS")
        self._button(12, 42, 74, 28, "BACK", self._c_panel_alt, self._c_text)
        self._centered_scaled(56, "Device setup", scale=2, color=self._c_text)
        self._draw_panel(22, 88, 276, 106, border=self._c_panel_alt, fill=self._c_panel)
        self._text(34, 102, "SAVED WIFI", self._c_text_muted)
        wifi_label = self._truncate_text(ssid or "Not configured", 28)
        self._text(34, 116, wifi_label, self._c_text if ssid else self._c_bad)
        self._button(34, 146, 116, 34, "WIFI", self._c_accent, self._c_bg)
        self._button(170, 146, 116, 34, "CALIB", self._c_panel_alt, self._c_text)
        self._centered_scaled(214, "WiFi opens setup portal", scale=1, color=self._c_text_muted)
        self.show()
        return True

    def show_first_time_setup(self, ap_name="RS-Core AP"):
        return self.show_message("SETUP", "No WiFi configured\nJoin " + str(ap_name), "Open portal")

    def show_pairing(self, ssid_hint="RS-Core AP"):
        return self.show_message("PAIRING", "Setup hotspot\n" + str(ssid_hint), "Open portal")

    def show_sync_searching(self, ssid):
        self._touch_mode = None
        self._reset_sync_upload_screen()
        key = ("sync_searching", str(ssid))
        if self._skip_render(key, 500):
            return True
        self._fb.fill(self._c_bg)
        self._header("SYNC")
        self._draw_panel(18, 54, 284, 132, border=self._c_panel_alt, fill=self._c_panel)
        self._text(34, 72, "CONNECTING TO", self._c_text_muted)
        self._centered_scaled(98, self._truncate_text(str(ssid or "Saved WiFi"), 18), scale=2, color=self._c_text)
        self._progress_bar(44, 148, 232, 8, 42, fill=self._c_accent, border=self._c_panel_alt, bg=self._c_bg)
        self._centered_scaled(210, "Keep hotspot nearby", scale=1, color=self._c_text_muted)
        self.show()
        return True

    def show_sync_connected(self, ssid, ip):
        self._touch_mode = None
        self._reset_sync_upload_screen()
        key = ("sync_connected", str(ssid), str(ip))
        if self._skip_render(key, 700):
            return True
        self._fb.fill(self._c_bg)
        self._header("WIFI READY")
        self._draw_panel(18, 54, 284, 132, border=self._c_accent, fill=self._c_panel)
        self._centered_scaled(74, "Connected", scale=3, color=self._c_text)
        self._centered_scaled(120, self._truncate_text(str(ssid or "WiFi"), 18), scale=2, color=self._c_accent_soft)
        self._centered_scaled(154, self._truncate_text(str(ip or ""), 20), scale=1, color=self._c_text_muted)
        self._centered_scaled(210, "Starting cloud sync", scale=1, color=self._c_text_muted)
        self.show()
        return True

    def show_heartbeat(self, state, host="", detail=""):
        self._touch_mode = None
        self._reset_sync_upload_screen()
        ok = "ACK" in str(state).upper() or "OK" in str(state).upper()
        key = ("heartbeat", ok, str(state))
        if self._skip_render(key, 180):
            return True
        self._fb.fill(self._c_bg)
        self._header("CLOUD")
        self._draw_panel(64, 54, 192, 132, border=self._c_panel_alt, fill=self._c_panel)
        self._draw_heart(160, 112, self._c_good if ok else self._c_bad)
        self._centered_scaled(198, "ACK RECEIVED" if ok else "CONTACTING CLOUD", scale=1, color=self._c_text_muted)
        self.show()
        if not ok:
            for scale in (7, 8, 7):
                self._draw_heartbeat_frame(self._c_bad, scale=scale)
                time.sleep_ms(90)
        return True

    def show_track_sync(self, track_name):
        return self.show_message("TRACK", "Active track\n" + str(track_name or "None"), "Track metadata")

    def show_sync_queue(self, files, allow_reboot=False, total_bytes=0):
        self._touch_mode = "sync_done" if allow_reboot else "sync_repair"
        self._reset_sync_metrics()
        self._reset_sync_upload_screen()
        key = ("sync_queue", tuple([str(f) for f in files[:3]]), len(files), int(total_bytes or 0), bool(allow_reboot))
        if self._skip_render(key, 500):
            return True
        self._fb.fill(self._c_bg)
        self._header("SYNC QUEUE")
        self._status_pill(22, 58, 88, "FILES", str(len(files)))
        self._status_pill(118, 58, 88, "QUEUE", self._format_bytes_compact(total_bytes))
        self._status_pill(214, 58, 84, "STATE", "READY" if files else "IDLE")
        self._draw_panel(22, 98, 276, 84, border=self._c_panel_alt, fill=self._c_panel)
        if not files:
            self._centered_scaled(126, "No pending files", scale=2, color=self._c_text)
        else:
            self._text(34, 112, "Pending files", self._c_text_muted)
            y = 128
            for name in files[:3]:
                self._text(34, y, self._truncate_text(str(name).split("/")[-1], 26), self._c_text)
                y += 14
        self._button(16, 194, 136, 30, "PAIR", self._c_panel_alt, self._c_text)
        if allow_reboot:
            self._button(168, 194, 136, 30, "REBOOT", self._c_accent, self._c_bg)
        else:
            self._centered_scaled(204, "Awaiting upload", scale=1, color=self._c_text_muted)
        self.show()
        return True

    def show_sync_upload(self, filename, file_index, total_files, sent_bytes, total_bytes, global_current=0, global_total=0, phase="UPLOADING", detail="", batch_count=0, total_batches=0):
        self._touch_mode = None
        global_pct, eta_text, rate_text = self._sync_stats(global_current, global_total)
        short_name = self._truncate_text(str(filename).split("/")[-1], 28)
        chunks = "--"
        if total_batches:
            chunks = "%d/%d" % (int(batch_count or 0), int(total_batches or 0))
        elif total_bytes:
            chunks = "%s/%s" % (self._format_bytes_compact(sent_bytes), self._format_bytes_compact(total_bytes))
        values = (short_name, int(file_index or 0), int(total_files or 0), global_pct, eta_text, chunks)
        screen_key = ("sync_upload_screen",)
        if self._sync_upload_screen_key != screen_key:
            self._sync_upload_screen_key = screen_key
            self._sync_upload_values = None
            self._fb.fill(self._c_bg)
            self._header("SYNC")
            self._draw_panel(12, 46, 296, 178, border=self._c_panel_alt, fill=self._c_panel)
            self._text(24, 62, "OVERALL PROGRESS", self._c_text_muted)
            self._text(24, 148, "CURRENT FILE", self._c_text_muted)
            self._text(24, 188, "ETA", self._c_text_muted)
            self._text(176, 188, "CHUNKS", self._c_text_muted)
            self.show()
        if self._sync_upload_values == values and self._skip_render(("sync_upload_hold", values), 220):
            return True
        self._sync_upload_values = values

        self._fb.fill_rect(22, 78, 276, 54, self._c_panel)
        self._big_value(24, 82, "%d%%" % global_pct, scale=5, color=self._c_accent)
        self._progress_bar(24, 124, 262, 10, global_pct, fill=self._c_accent, border=self._c_panel_alt, bg=self._c_bg)
        self._show_region(22, 78, 276, 58)

        self._fb.fill_rect(22, 160, 276, 18, self._c_panel)
        self._text(24, 160, short_name, self._c_text)
        self._text(236, 160, "%d/%d" % (int(file_index or 0) + 1, int(total_files or 1)), self._c_text_dim)
        self._show_region(22, 158, 276, 24)

        self._fb.fill_rect(22, 202, 124, 26, self._c_panel)
        self._big_value(24, 202, eta_text, scale=3, color=self._c_text, shadow=False)
        self._show_region(22, 200, 124, 30)

        self._fb.fill_rect(174, 202, 116, 26, self._c_panel)
        self._big_value(176, 202, chunks, scale=3, color=self._c_text, shadow=False)
        self._show_region(174, 200, 116, 30)
        return True

    def show_sync_result(self, ok, filename="", detail="", allow_reboot=False):
        self._touch_mode = "sync_done" if allow_reboot else "sync_repair"
        self._reset_sync_metrics()
        self._reset_sync_upload_screen()
        key = ("sync_result", bool(ok), str(filename), str(detail), bool(allow_reboot))
        if self._skip_render(key, 700):
            return True
        title = "SYNC OK" if ok else "SYNC FAIL"
        self._fb.fill(self._c_bg)
        self._header(title, color=self._c_accent if ok else self._c_bad)
        y = 54
        if filename:
            self._centered_scaled(y, self._truncate_text(str(filename).split("/")[-1], 20), scale=2, color=self._c_text)
            y += 28
        if detail:
            for line in str(detail).split("\n")[:3]:
                if line:
                    self._centered_scaled(y, self._truncate_text(line, 22), scale=2, color=self._c_text_dim)
                    y += 22
        self._button(16, 186, 136, 38, "RE-PAIR", self._c_panel, self._c_text)
        if allow_reboot:
            self._button(168, 186, 136, 38, "REBOOT", self._c_accent, self._c_bg)
        else:
            self._centered_scaled(204, "Retry later", scale=1, color=self._c_text_muted)
        self.show()
        return True

    def show_sync_idle(self, hb_ok, pending_count=0, pending_bytes=0, low_power=False, allow_reboot=False, phase_label="", last_result="", track_name=""):
        self._touch_mode = "sync_done" if allow_reboot else "sync_repair"
        self._reset_sync_metrics()
        self._reset_sync_upload_screen()
        key = (
            "sync_idle",
            bool(hb_ok),
            int(pending_count or 0),
            int(pending_bytes or 0),
            bool(low_power),
            bool(allow_reboot),
            str(phase_label),
            str(last_result),
            str(track_name),
        )
        if self._skip_render(key, 500):
            return True
        self._fb.fill(self._c_bg)
        self._header("SYNC READY")
        self._draw_panel(12, 48, 296, 138, border=self._c_panel_alt, fill=self._c_panel)
        self._status_pill(22, 58, 86, "CLOUD", "OK" if hb_ok else "WAIT", self._c_accent if hb_ok else self._c_bad)
        self._status_pill(116, 58, 86, "PHASE", self._truncate_text(phase_label or "IDLE", 8))
        self._status_pill(210, 58, 88, "FILES", str(max(0, int(pending_count or 0))))
        self._status_pill(22, 92, 86, "QUEUE", self._format_bytes_compact(pending_bytes))
        self._status_pill(116, 92, 86, "POWER", "LOW" if low_power else "NORM", self._c_bad if low_power else self._c_accent)
        self._status_pill(210, 92, 88, "TRACK", self._truncate_text(track_name or "NONE", 8))
        result_text = last_result or ("Ready to upload" if pending_count else "Nothing pending")
        self._text(24, 136, "LAST RESULT", self._c_text_muted)
        self._text(24, 150, self._truncate_text(result_text, 32), self._c_text)
        self._button(16, 194, 136, 30, "PAIR", self._c_panel_alt, self._c_text)
        if allow_reboot:
            self._button(168, 194, 136, 30, "REBOOT", self._c_accent, self._c_bg)
        else:
            self._centered_scaled(204, "Hold button or tap", scale=1, color=self._c_text_muted)
        self.show()
        return True

    def show_sync_wifi_failed(self, ssid="", allow_retry=True):
        self._touch_mode = "sync_retry" if allow_retry else "sync_repair"
        self._reset_sync_metrics()
        self._reset_sync_upload_screen()
        key = ("sync_wifi_failed", str(ssid), bool(allow_retry))
        if self._skip_render(key, 700):
            return True
        self._fb.fill(self._c_bg)
        self._header("SYNC FAIL", color=self._c_bad)
        self._centered_scaled(62, "WiFi failed", scale=3, color=self._c_text)
        if ssid:
            self._centered_scaled(106, self._truncate_text(str(ssid), 20), scale=2, color=self._c_text_dim)
        if allow_retry:
            self._button(16, 186, 136, 38, "SCAN WIFI", self._c_accent, self._c_bg)
            self._button(168, 186, 136, 38, "RE-PAIR", self._c_panel, self._c_text)
        else:
            self._button(16, 186, 136, 38, "RE-PAIR", self._c_panel, self._c_text)
        self.show()
        return True

    def show_logging_started(self, filename, track_name=None, elapsed_minutes=0, force=False):
        self._touch_mode = None
        body = str(filename).split("/")[-1]
        if track_name:
            body += "\n" + str(track_name)
        return self.show_message("LOGGING", body, "T+%dm" % max(0, int(elapsed_minutes)))

    def show_logging_live(self, filename, sats=0, gps_ok=False, track_name=None, elapsed_minutes=0):
        self._touch_mode = None
        self._fb.fill(0x0000)
        self._header("LOGGING", color=0x07E0 if gps_ok else 0xF800)
        self._centered_scaled(54, str(filename).split("/")[-1], scale=2, color=0xFFFF)
        self._centered_scaled(94, "SATS %d" % max(0, int(sats or 0)), scale=3, color=0xFFE0 if sats < 4 else 0x07E0)
        self._centered_scaled(150, "GPS OK" if gps_ok else "GPS SEARCH", scale=2, color=0x07E0 if gps_ok else 0xF800)
        if track_name:
            self._centered_scaled(194, str(track_name)[:16], scale=2, color=0xFFFF)
        self._centered_scaled(216, "T+%dm" % max(0, int(elapsed_minutes)), scale=2, color=0xFFFF)
        self.show()
        return True

    def show_track_event(self, event, track_name=None, sector=None):
        self._touch_mode = None
        footer = track_name or ""
        if sector is not None:
            footer = "Sector %s" % sector
        return self.show_message(event, event.replace("_", " "), footer)

    def show_storage_critical(self, used_kb, total_kb, reason="Storage critical"):
        self._touch_mode = None
        pct = 0 if total_kb <= 0 else int((used_kb * 100) / total_kb)
        return self.show_message("STORAGE", "%s\n%d%% full" % (reason, pct), "%d/%d KB" % (used_kb, total_kb))

    def sync_touch(self):
        point = self._touch.read()
        if not point:
            return None
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_touch_ms) < self._touch_debounce_ms:
            return None
        x = point["sx"]
        y = point["sy"]
        print("[TFT] touch:", x, y, self._touch_mode)
        if self._touch_mode in ("sync_repair", "sync_done"):
            if 8 <= x <= 160 and 180 <= y <= 236:
                self._last_touch_ms = now
                return "repair"
            if self._touch_mode == "sync_done" and 160 <= x <= 312 and 180 <= y <= 236:
                self._last_touch_ms = now
                return "reboot"
        if self._touch_mode == "sync_retry":
            if 8 <= x <= 160 and 180 <= y <= 236:
                self._last_touch_ms = now
                return "retry_wifi"
            if 160 <= x <= 312 and 180 <= y <= 236:
                self._last_touch_ms = now
                return "repair"
        return None

    def decision_touch(self):
        point = self._touch.read()
        if not point:
            return None
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_touch_ms) < self._touch_debounce_ms:
            return None
        x = point["sx"]
        y = point["sy"]
        print("[TFT] touch:", x, y)
        # Keep the active area centered, but generous enough for calibration
        # drift and imperfect finger taps on the resistive panel.
        if y < 142 or y > 220:
            return None
        if 16 <= x <= 108:
            self._last_touch_ms = now
            return "yes"
        if 109 <= x <= 220:
            self._last_touch_ms = now
            return "settings"
        if 221 <= x <= 306:
            self._last_touch_ms = now
            return "no"
        return None

    def settings_touch(self):
        point = self._touch.read()
        if not point:
            return None
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_touch_ms) < self._touch_debounce_ms:
            return None
        x = point["sx"]
        y = point["sy"]
        print("[TFT] touch:", x, y, self._touch_mode)
        if 8 <= x <= 92 and 36 <= y <= 78:
            self._last_touch_ms = now
            return "back"
        if 28 <= x <= 158 and 136 <= y <= 190:
            self._last_touch_ms = now
            return "wifi"
        if 162 <= x <= 292 and 136 <= y <= 190:
            self._last_touch_ms = now
            return "calibrate"
        return None
