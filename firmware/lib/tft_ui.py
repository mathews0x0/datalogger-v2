import time
import math
import framebuf
import machine
import ujson
import os
try:
    import micropython
except ImportError:
    class _MicroPythonCompat:
        @staticmethod
        def native(func):
            return func
    micropython = _MicroPythonCompat()

from drivers.ili9341 import ILI9341
from lib.display_config import DEFAULT_DISPLAY_CONFIG, normalize_display_config, save_display_config, load_display_config
try:
    from drivers.xpt2046 import XPT2046
except ImportError:
    XPT2046 = None


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
        pin_tft_rst=42,
        pin_touch_cs=7,
        pin_touch_irq=38,
        display_config=None,
    ):
        self.width = 320
        self.height = 240
        self._display_config = normalize_display_config(display_config)
        self._swap_bytes = bool(self._display_config.get("swap_bytes", True))
        self._pin_tft_cs = pin_tft_cs
        self._pin_tft_dc = pin_tft_dc
        self._pin_tft_rst = pin_tft_rst
        self._spi = machine.SPI(
            spi_bus,
            baudrate=self._display_config["baudrate"],
            polarity=0,
            phase=0,
            sck=machine.Pin(pin_sck),
            mosi=machine.Pin(pin_mosi),
            miso=machine.Pin(pin_miso),
        )
        self._display = self._make_display(self._display_config)
        if XPT2046 is not None:
            self._touch = XPT2046(
                spi=self._spi,
                cs=machine.Pin(pin_touch_cs, machine.Pin.OUT),
                irq=machine.Pin(pin_touch_irq, machine.Pin.IN, machine.Pin.PULL_UP) if pin_touch_irq is not None else None,
                baudrate=1_000_000,
                calibration=self._load_touch_calibration(),
            )
        else:
            print("[TFT] Touch disabled: drivers.xpt2046 missing")
            self._touch = None
        self._buf = bytearray(self.width * self.height * 2)
        self._fb = framebuf.FrameBuffer(self._buf, self.width, self.height, framebuf.RGB565)
        self._mono_buf = bytearray(self.width)
        self._mono_fb = framebuf.FrameBuffer(self._mono_buf, self.width, 8, framebuf.MONO_VLSB)
        self._tx_buf = bytearray(32 * 1024)
        self._last_touch_ms = 0
        self._battery_pct = None
        self._charging = False
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
        self._touch_debounce_ms = 110
        self._sync_upload_screen_key = None
        self._sync_upload_values = None
        self._sync_search_screen_key = None
        self._boot_logo_visible = False
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
        self._topbar_title = "RaceSense"
        self._topbar_color = self._c_accent
        self._topbar_key = None
        self._topbar_ram_key = None
        self._topbar_last_full_ms = 0
        self._topbar_last_ram_ms = 0
        self._logging_track_name = ""
        self._logging_elapsed_minutes = 0
        self._logging_gps_ok = False
        self._logging_status_text = "READY"
        self._logging_status_color = self._c_warn
        self._logging_status_mode = "status"
        self._logging_last_lap_text = "--.---"
        self._logging_last_lap_color = self._c_text_dim
        self._logging_has_lap = False
        self._logging_layout_cache = None
        self._logging_layout_key = None
        self._logging_screen_active = False
        self._settings_scroll_index = 0
        self._fb.fill(self._c_bg)

    def _make_display(self, display_config):
        cfg = normalize_display_config(display_config)
        return ILI9341(
            spi=self._spi,
            cs=machine.Pin(self._pin_tft_cs, machine.Pin.OUT),
            dc=machine.Pin(self._pin_tft_dc, machine.Pin.OUT),
            rst=machine.Pin(self._pin_tft_rst, machine.Pin.OUT, value=1) if self._pin_tft_rst is not None else None,
            rotation=cfg["rotation"],
            baudrate=cfg["baudrate"],
            madctl=cfg["madctl"],
            clear_on_init=False,
            reset_on_init=True,
            init_on_init=True,
        )

    def apply_display_config(self, display_config, clear=True):
        cfg = normalize_display_config(display_config)
        self._display_config = cfg
        self._swap_bytes = bool(cfg.get("swap_bytes", True))
        self._spi.init(baudrate=cfg["baudrate"], polarity=0, phase=0)
        self._display = self._make_display(cfg)
        if clear:
            self._fb.fill(self._c_bg)
            self.show()
        return cfg

    def _font(self):
        if not hasattr(self, "_font_renderer"):
            from lib.tft_fonts import renderer
            self._font_renderer = renderer
        return self._font_renderer

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

    def has_display_selection_touch(self):
        if self._touch is None:
            return False
        try:
            return bool(self._touch.touched())
        except Exception:
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
            if self._touch is not None:
                self._touch.calibration = cal
            return True
        except Exception as e:
            print("[TFT] Touch calibration save failed:", e)
            return False

    def set_context(self, battery_pct=None, charging=None, sd_ok=None, sd_pct=None, ram_used_mb=None, ram_total_mb=None):
        if battery_pct is not None:
            try:
                self._battery_pct = max(0, min(100, int(battery_pct)))
            except Exception:
                self._battery_pct = None
        if charging is not None:
            self._charging = bool(charging)
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
        self._boot_logo_visible = False
        self.show()

    def _skip_render(self, key, min_interval_ms=250):
        now = time.ticks_ms()
        if key == self._last_render_key and time.ticks_diff(now, self._last_render_ms) < min_interval_ms:
            return True
        self._last_render_key = key
        self._last_render_ms = now
        return False

    def _skip_same_render(self, key):
        if key == self._last_render_key:
            return True
        self._last_render_key = key
        self._last_render_ms = time.ticks_ms()
        return False

    def invalidate(self):
        self._last_render_key = None
        self._topbar_key = None
        self._topbar_ram_key = None
        self._sync_search_screen_key = None
        self._sync_upload_screen_key = None
        self._sync_upload_values = None

    def _touch_point(self):
        if self._touch is None:
            return None, time.ticks_ms()
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_touch_ms) < self._touch_debounce_ms:
            return None, now
        return self._touch.read(), now

    @micropython.native
    def _write_swapped_from_buffer(self, start, length):
        src = self._buf
        tx = self._tx_buf
        tx_len = len(tx)
        end = start + length
        pos = start
        while pos < end:
            chunk_len = min(tx_len, end - pos)
            if chunk_len & 1:
                chunk_len -= 1
            i = 0
            while i < chunk_len:
                tx[i] = src[pos + i + 1]
                tx[i + 1] = src[pos + i]
                i += 2
            self._spi.write(memoryview(tx)[:chunk_len])
            pos += chunk_len

    def show(self):
        self._display.set_window(0, 0, self.width - 1, self.height - 1)
        self._display._activate_spi()
        self._display.cs.value(0)
        self._display.dc.value(1)
        if self._swap_bytes:
            self._write_swapped_from_buffer(0, len(self._buf))
        else:
            self._spi.write(self._buf)
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
        if self._swap_bytes:
            if x == 0 and w == self.width:
                self._write_swapped_from_buffer((y * self.width) * 2, w * h * 2)
            else:
                for row in range(y, y + h):
                    self._write_swapped_from_buffer(((row * self.width) + x) * 2, w * 2)
        else:
            if x == 0 and w == self.width:
                start = (y * self.width) * 2
                self._spi.write(memoryview(self._buf)[start:start + (w * h * 2)])
            else:
                for row in range(y, y + h):
                    start = ((row * self.width) + x) * 2
                    self._spi.write(memoryview(self._buf)[start:start + (w * 2)])
        self._display.cs.value(1)

    def _show_regions(self, regions):
        for region in regions:
            self._show_region(region[0], region[1], region[2], region[3])

    def _logging_palette(self, bucket):
        bucket = str(bucket or "").lower()
        if bucket == "green":
            return self._c_good
        if bucket == "red":
            return self._c_bad
        return self._c_warn

    def _logging_layout_cache_key(self, track_data):
        if not isinstance(track_data, dict):
            return None
        layout = track_data.get("device_layout") or {}
        polyline = layout.get("polyline") if isinstance(layout, dict) else None
        sectors = track_data.get("sectors") or []
        return (
            track_data.get("track_id"),
            track_data.get("track_name") or track_data.get("name"),
            len(polyline) if isinstance(polyline, list) else 0,
            len(sectors),
        )

    def _prepare_logging_layout(self, track_data):
        key = self._logging_layout_cache_key(track_data)
        if key == self._logging_layout_key:
            return self._logging_layout_cache

        self._logging_layout_key = key
        self._logging_layout_cache = None
        if not isinstance(track_data, dict):
            return None
        layout = track_data.get("device_layout")
        if not isinstance(layout, dict):
            return None

        polyline = layout.get("polyline")
        if not isinstance(polyline, list) or len(polyline) < 2:
            return None

        map_x = 18
        map_y = 54
        map_w = 284
        map_h = 108
        inner_x = map_x + 8
        inner_y = map_y + 8
        inner_w = map_w - 16
        inner_h = map_h - 16

        def scale_point(point):
            try:
                px = int(point.get("x", 0))
                py = int(point.get("y", 0))
            except Exception:
                return None
            sx = inner_x + ((max(0, min(1000, px)) * inner_w) // 1000)
            sy = inner_y + ((max(0, min(1000, py)) * inner_h) // 1000)
            return (sx, sy)

        def marker_label(point, fallback_idx):
            try:
                sector_index = int(point.get("sector_index"))
                if sector_index > 0:
                    return "S%d" % sector_index
            except Exception:
                pass
            marker_id = point.get("id")
            if marker_id:
                return str(marker_id)
            return "S%d" % (fallback_idx + 1)

        scaled_polyline = []
        for point in polyline:
            scaled = scale_point(point)
            if scaled:
                scaled_polyline.append(scaled)
        if len(scaled_polyline) < 2:
            return None

        scaled_sectors = []
        for idx, point in enumerate(layout.get("sector_markers") or []):
            scaled = scale_point(point)
            if scaled:
                scaled_sectors.append({
                    "x": scaled[0],
                    "y": scaled[1],
                    "label": marker_label(point, idx),
                })

        start_marker = None
        if isinstance(layout.get("start_marker"), dict):
            start_marker = scale_point(layout.get("start_marker"))

        self._logging_layout_cache = {
            "panel": (map_x, map_y, map_w, map_h),
            "polyline": scaled_polyline,
            "sector_markers": scaled_sectors,
            "start_marker": start_marker,
        }
        return self._logging_layout_cache

    def _draw_logging_background(self, track_data):
        self._fb.fill(self._c_bg)
        self._header("LOGGING", color=self._c_good if self._logging_gps_ok else self._c_bad)
        self._text(16, 54, "LAST LAP", self._c_text_muted, bg=self._c_bg)
        self._draw_logging_lap_time_panel()

        self._draw_panel(12, 198, 296, 30, border=self._c_panel_alt, fill=self._c_bg)
        self._text(22, 207, "TRACK", self._c_text_muted, bg=self._c_bg)
        track_label = self._fit_text_px(self._logging_track_name or "No track", 150, "ui")
        self._text(74, 207, track_label, self._c_text if self._logging_track_name else self._c_text_dim, bg=self._c_bg)
        elapsed = "T+%dm" % max(0, int(self._logging_elapsed_minutes))
        elapsed_x = 300 - self._text_width(elapsed, "ui")
        self._text(elapsed_x, 207, elapsed, self._c_text, bg=self._c_bg)
        self._logging_screen_active = True

    def _draw_thick_data_text(self, x, y, text, color, bg):
        offsets = (
            (-2, 0),
            (-1, 0),
            (0, 0),
            (1, 0),
            (2, 0),
            (0, -1),
            (0, 1),
        )
        for dx, dy in offsets:
            self._text_data(x + dx, y + dy, text, color, bg=bg)

    def _draw_logging_lap_time_panel(self):
        panel_x = 10
        panel_y = 68
        panel_w = 300
        panel_h = 118
        self._fb.fill_rect(panel_x, panel_y, panel_w, panel_h, self._c_bg)
        self._fb.rect(panel_x, panel_y, panel_w, panel_h, self._c_panel_alt)

        if self._logging_has_lap:
            lap_text = str(self._logging_last_lap_text or "--.---")
            lap_color = self._logging_last_lap_color or self._c_text
        else:
            lap_text = "--.---"
            lap_color = self._c_text

        text_w = self._text_width(lap_text, "data")
        text_x = max(panel_x + 12, (self.width - text_w) // 2)
        text_y = panel_y + 32
        self._draw_thick_data_text(text_x, text_y, lap_text, lap_color, self._c_bg)

        footer = "LED handles sector feedback" if self._logging_has_lap else "Waiting for first lap"
        self._centered_scaled(panel_y + 94, footer, scale=1, color=self._c_text_muted)

    def _draw_logging_status_band(self):
        band_x = 10
        band_y = 192
        band_w = 300
        band_h = 40
        fill = self._logging_palette(self._logging_status_color)
        self._fb.fill_rect(band_x, band_y, band_w, band_h, fill)
        text = str(self._logging_status_text or "READY")
        style = "data"
        if self._text_width(text, style) > (band_w - 12):
            style = "ui"
        text_w = self._text_width(text, style)
        text_h = self._font().height(style)
        text_x = max(band_x + 4, band_x + ((band_w - text_w) // 2))
        text_y = band_y + max(2, (band_h - text_h) // 2)
        if style == "data":
            self._text_data(text_x, text_y, text, self._c_text, bg=fill)
        else:
            self._text(text_x, text_y, text, self._c_text, bg=fill)

    def _set_logging_context(self, track_name=None, elapsed_minutes=0, gps_ok=False, track_data=None):
        self._logging_track_name = str(track_name or "")
        self._logging_elapsed_minutes = int(elapsed_minutes or 0)
        self._logging_gps_ok = bool(gps_ok)
        self._prepare_logging_layout(track_data)

    def _apply_logging_event(self, event):
        if not isinstance(event, dict):
            return
        event_type = str(event.get("type") or "")
        if event_type != "lap_complete":
            return
        self._logging_status_mode = event_type
        self._logging_status_text = str(event.get("display_text") or "READY")
        self._logging_status_color = event.get("display_color") or "orange"
        self._logging_last_lap_text = str(event.get("display_text") or "--.---")
        self._logging_last_lap_color = self._c_text
        self._logging_has_lap = True

    def _start_region_screen(self):
        self._fb.fill(self._c_bg)
        self._display.fill(self._c_bg)

    def _start_content_screen(self):
        self._fb.fill_rect(0, 40, self.width, self.height - 40, self._c_bg)
        self._display.fill_rect(0, 40, self.width, self.height - 40, self._c_bg)

    def _topbar_values(self):
        ram_used_key = int(self._ram_used_mb or 0) if self._ram_used_mb is not None else None
        ram_total_key = int(self._ram_total_mb or 0) if self._ram_total_mb is not None else None
        return (self._battery_pct, self._charging, self._sd_ok, self._sd_pct, ram_used_key, ram_total_key)

    def _draw_charge_bolt(self, x, y, color):
        self._fb.fill_rect(x + 2, y, 4, 2, color)
        self._fb.fill_rect(x + 1, y + 2, 3, 2, color)
        self._fb.fill_rect(x + 3, y + 4, 3, 2, color)
        self._fb.fill_rect(x + 2, y + 6, 2, 2, color)

    def _draw_topbar_to_fb(self, title=None, color=None, ram_only=False):
        title = self._topbar_title if title is None else str(title)
        color = self._topbar_color if color is None else color
        if not ram_only:
            self._topbar_title = title
            self._topbar_color = color
            self._fb.fill_rect(0, 0, self.width, 40, color)
            title_x = max(0, (self.width - self._text_width(title, "ui")) // 2)
            self._text(title_x, 5, title, self._c_bg, bg=color)
            if self._battery_pct is not None:
                batt_x = 8
                if self._charging:
                    self._draw_charge_bolt(batt_x, 24, self._c_bg)
                    batt_x += 11
                self._text(batt_x, 24, "BAT %d%%" % self._battery_pct, self._c_bg, bg=color)
            if self._sd_ok is not None:
                sd_label = "SD --"
                if self._sd_ok:
                    sd_label = "SD %d%%" % (self._sd_pct if self._sd_pct is not None else 0)
                sd_x = self.width - self._text_width(sd_label, "ui") - 8
                self._text(sd_x, 24, sd_label, self._c_bg, bg=color)
        self._fb.fill_rect(88, 24, 144, 14, color)
        if self._ram_used_mb is not None and self._ram_total_mb is not None:
            ram = "RAM %.1f/%.1f" % (self._ram_used_mb, self._ram_total_mb)
            x = max(88, (self.width - self._text_width(ram, "ui")) // 2)
            self._text(x, 24, ram, self._c_bg, bg=color)

    def refresh_topbar(self, title=None, color=None, force=False):
        now = time.ticks_ms()
        title = self._topbar_title if title is None else str(title)
        color = self._topbar_color if color is None else color
        full_key = (title, color, self._battery_pct, self._charging, self._sd_ok, self._sd_pct)
        ram_key = (self._ram_used_mb, self._ram_total_mb)
        if force or full_key != self._topbar_key or time.ticks_diff(now, self._topbar_last_full_ms) >= 30000:
            self._draw_topbar_to_fb(title, color, ram_only=False)
            self._show_region(0, 0, self.width, 40)
            self._topbar_key = full_key
            self._topbar_ram_key = ram_key
            self._topbar_last_full_ms = now
            self._topbar_last_ram_ms = now
            return True
        if ram_key != self._topbar_ram_key and time.ticks_diff(now, self._topbar_last_ram_ms) >= 2000:
            self._draw_topbar_to_fb(title, color, ram_only=True)
            self._show_region(88, 24, 144, 14)
            self._topbar_ram_key = ram_key
            self._topbar_last_ram_ms = now
            return True
        return False

    def _block_text_width(self, text, scale):
        narrow = (".", "i", "l")
        total = 0
        for ch in str(text):
            total += (3 if ch in narrow else 6) * scale
        return total

    def _block_glyphs(self):
        return {
            "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
            "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
            "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
            "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
            "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
            "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
            "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
            "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
            "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
            "i": ("00100", "00000", "01100", "00100", "00100", "00100", "01110"),
        }

    def _draw_block_glyph(self, rows, x, y, scale, color):
        for yy, row in enumerate(rows):
            for xx, bit in enumerate(row):
                if bit == "1":
                    self._fb.fill_rect(x + xx * scale, y + yy * scale, scale - 1, scale - 1, color)

    def _draw_block_text(self, text, x, y, scale, color, accent=None):
        glyphs = self._block_glyphs()
        cursor = int(x)
        scale = int(scale)
        accent = color if accent is None else accent
        for ch in str(text):
            if ch == ".":
                self._fb.fill_rect(cursor + scale, y + 6 * scale, scale - 1, scale - 1, accent)
                cursor += 3 * scale
                continue
            rows = glyphs.get(ch)
            if rows:
                self._draw_block_glyph(rows, cursor, y, scale, color)
            cursor += (3 if ch in ("i", "l") else 6) * scale

    def _text(self, x, y, text, color=0xFFFF, bg=None):
        return self._font().draw_text(self._fb, int(x), int(y), str(text), style="ui", color=color, bg=bg)

    def _text_data(self, x, y, text, color=0xFFFF, bg=None):
        return self._font().draw_text(self._fb, int(x), int(y), str(text), style="data", color=color, bg=bg)

    def _text_width(self, text, style="ui"):
        return self._font().text_width(str(text), style=style)

    def _fit_text_px(self, text, max_w, style="ui"):
        text = str(text)
        if self._text_width(text, style) <= max_w:
            return text
        if max_w <= self._text_width("...", style):
            return ""
        out = text
        while out and self._text_width(out + "...", style) > max_w:
            out = out[:-1]
        return out + "..." if out else ""

    def _text_scaled(self, x, y, text, scale=2, color=0xFFFF):
        self._text(x, y, text, color)

    def _centered_scaled(self, y, text, scale=2, color=0xFFFF):
        width = self._text_width(text, "ui")
        x = max(0, (self.width - width) // 2)
        self._text(x, y, text, color)

    def _big_value_width(self, text, scale=4):
        return self._text_width(text, "data")

    def _big_value(self, x, y, text, scale=4, color=None, shadow=True, bg=None):
        color = self._c_accent if color is None else color
        text = str(text)
        if shadow:
            self._big_value(x + 1, y + 1, text, scale=scale, color=self._c_bg, shadow=False)
        self._text_data(x, y, text, color, bg=bg)

    def _centered_big_value(self, y, text, scale=4, color=None):
        x = max(0, (self.width - self._big_value_width(text, scale)) // 2)
        self._big_value(x, y, text, scale=scale, color=color)

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

    def _arrow_button(self, x, y, w, h, direction, enabled=True):
        fill = self._c_accent if enabled else self._c_panel
        fg = self._c_bg if enabled else self._c_text_muted
        self._fb.fill_rect(x, y, w, h, fill)
        self._fb.rect(x, y, w, h, self._c_text_dim)
        mid_x = x + (w // 2)
        mid_y = y + (h // 2)
        if direction == "up":
            for step in range(6):
                self._fb.line(mid_x - step, mid_y - 2 + step, mid_x + step, mid_y - 2 + step, fg)
        else:
            for step in range(6):
                self._fb.line(mid_x - step, mid_y + 2 - step, mid_x + step, mid_y + 2 - step, fg)

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

    def _draw_raw_rgb565(self, x, y, w, h, path):
        if w <= 0 or h <= 0:
            return False
        try:
            f = open(path, "rb")
        except Exception as e:
            print("[TFT] Boot logo raw open failed:", e)
            return False
        try:
            self._display.set_window(x, y, x + w - 1, y + h - 1)
            self._display._activate_spi()
            self._display.cs.value(0)
            self._display.dc.value(1)
            while True:
                chunk = f.read(1024)
                if not chunk:
                    break
                self._spi.write(chunk)
            self._display.cs.value(1)
            return True
        except Exception as e:
            try:
                self._display.cs.value(1)
            except Exception:
                pass
            print("[TFT] Boot logo raw draw failed:", e)
            return False
        finally:
            try:
                f.close()
            except Exception:
                pass

    def _brand_wordmark(self, y):
        # Approximate the web wordmark: clean white title with a restrained
        # RaceSense orange glow, centered in the boot panel.
        word = "RaceSense"
        x = (self.width - self._text_width(word, "ui")) // 2
        self._text(x + 1, y + 1, word, self._c_accent)
        self._text(x, y, word, self._c_text)
        self._fb.fill_rect(78, y + 20, 164, 2, self._c_accent)
        tagline = "ride faster. ride smarter."
        self._text((self.width - self._text_width(tagline, "ui")) // 2, y + 28, tagline, self._c_text_muted)

    def _title_block(self, eyebrow, title, subtitle="", panel_y=48, panel_h=168):
        self._fb.fill(self._c_bg)
        self._header(eyebrow)
        self._draw_panel(12, panel_y, 296, panel_h, border=self._c_panel_alt, fill=self._c_bg)
        title_scale = 3 if len(str(title)) <= 16 else 2
        self._centered_scaled(panel_y + 18, title, scale=title_scale, color=self._c_text)
        if subtitle:
            self._centered_scaled(panel_y + 18 + (title_scale * 12), subtitle, scale=1, color=self._c_text_muted)

    def _status_pill(self, x, y, w, label, value, accent=None):
        self._fb.fill_rect(x, y, w, 34, self._c_panel)
        self._fb.rect(x, y, w, 34, self._c_panel_alt)
        self._text(x + 7, y + 3, self._fit_text_px(label, w - 14, "ui"), self._c_text_muted, bg=self._c_panel)
        value_color = self._c_text if accent is None else accent
        self._text(x + 7, y + 18, self._fit_text_px(value, w - 14, "ui"), value_color, bg=self._c_panel)

    def _label_value(self, x, y, label, value, w=0):
        label = self._fit_text_px(label, 76 if w <= 0 else max(40, w // 2), "ui")
        value = self._fit_text_px(value, 170 if w <= 0 else max(40, w - 44), "ui")
        self._text(x, y, label, self._c_text_muted)
        if w > 0:
            value_x = x + w - self._text_width(value, "ui")
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

    def _format_mb_label(self, value):
        try:
            value = int(value or 0)
        except Exception:
            value = 0
        mb = value / (1024.0 * 1024.0)
        return "[%.1f MB]" % mb

    def _format_eta(self, seconds):
        if seconds is None:
            return "--"
        seconds = max(0, int(seconds))
        hours = seconds // 3600
        if hours > 0:
            return "%dh %02dm" % (hours, (seconds % 3600) // 60)
        minutes = seconds // 60
        secs = seconds % 60
        if minutes > 0:
            return "%dm %02ds" % (minutes, secs)
        return "%ds" % secs

    def _reset_sync_metrics(self):
        self._sync_started_ms = None
        self._sync_last_bytes = 0
        self._sync_last_ms = 0
        self._sync_rate_bps = 0.0
        self._sync_eta_s = None

    def _reset_sync_upload_screen(self):
        self._sync_upload_screen_key = None
        self._sync_upload_values = None

    def _reset_sync_search_screen(self):
        self._sync_search_screen_key = None

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
        label = self._fit_text_px(label, w - 10, "ui")
        tx = x + max(4, (w - self._text_width(label, "ui")) // 2)
        ty = y + max(3, (h - self._font().height("ui")) // 2)
        self._text(tx, ty, label, fg, bg=fill)

    def _gear_icon(self, cx, cy, color, bg):
        for x, y, w, h in (
            (cx - 3, cy - 14, 6, 5),
            (cx - 3, cy + 9, 6, 5),
            (cx - 14, cy - 3, 5, 6),
            (cx + 9, cy - 3, 5, 6),
            (cx - 11, cy - 11, 5, 5),
            (cx + 6, cy - 11, 5, 5),
            (cx - 11, cy + 6, 5, 5),
            (cx + 6, cy + 6, 5, 5),
        ):
            self._fb.fill_rect(x, y, w, h, color)
        self._fb.fill_rect(cx - 9, cy - 9, 18, 18, color)
        self._fb.fill_rect(cx - 4, cy - 4, 8, 8, bg)

    def _icon_button(self, x, y, w, h, icon, fill, fg=0xFFFF):
        self._fb.fill_rect(x, y, w, h, fill)
        self._fb.rect(x, y, w, h, self._c_text_dim)
        if icon == "gear":
            self._gear_icon(x + (w // 2), y + (h // 2), fg, fill)

    def _toggle(self, x, y, w, h, enabled):
        fill = self._c_accent if enabled else self._c_panel_alt
        knob = self._c_bg if enabled else self._c_text_dim
        self._fb.fill_rect(x, y, w, h, fill)
        self._fb.rect(x, y, w, h, self._c_text_dim)
        k = h - 8
        kx = x + w - k - 4 if enabled else x + 4
        self._fb.fill_rect(kx, y + 4, k, k, knob)

    def _status_icon(self, cx, cy, ok):
        color = self._c_good if ok else self._c_bad
        self._fb.fill_rect(cx - 11, cy - 11, 22, 22, color)
        self._fb.rect(cx - 11, cy - 11, 22, 22, self._c_text_dim)
        if ok:
            self._fb.fill_rect(cx - 6, cy, 4, 8, self._c_bg)
            self._fb.fill_rect(cx - 2, cy + 4, 12, 4, self._c_bg)
            self._fb.fill_rect(cx + 5, cy - 5, 4, 13, self._c_bg)
        else:
            for i in range(-6, 7):
                self._fb.fill_rect(cx + i, cy + i, 3, 3, self._c_bg)
                self._fb.fill_rect(cx + i, cy - i, 3, 3, self._c_bg)

    def _status_line(self, x, y, label, ok):
        self._fb.fill_rect(x, y, 86, 34, self._c_panel)
        self._fb.rect(x, y, 86, 34, self._c_panel_alt)
        self._text(x + 8, y + 10, label, self._c_text, bg=self._c_panel)
        self._status_icon(x + 68, y + 17, ok)

    def _wifi_bars(self, cx, y, frame, color):
        frame = int(frame or 0) % 4
        widths = (84, 58, 32)
        heights = (34, 22, 10)
        for i in range(3):
            active = i <= frame
            c = color if active else self._c_panel_alt
            w = widths[i]
            h = heights[i]
            x0 = cx - (w // 2)
            yy = y + (i * 18)
            self._fb.rect(x0, yy, w, h, c)
            self._fb.fill_rect(cx - 3, yy + h - 5, 6, 6, c)

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

    def _mix565(self, c0, c1, t, span):
        if span <= 0:
            return c1 & 0xFFFF
        t = max(0, min(span, int(t)))
        r0 = (c0 >> 11) & 0x1F
        g0 = (c0 >> 5) & 0x3F
        b0 = c0 & 0x1F
        r1 = (c1 >> 11) & 0x1F
        g1 = (c1 >> 5) & 0x3F
        b1 = c1 & 0x1F
        r = r0 + (((r1 - r0) * t) // span)
        g = g0 + (((g1 - g0) * t) // span)
        b = b0 + (((b1 - b0) * t) // span)
        return (r << 11) | (g << 5) | b

    def _rainbow565(self, pos, span):
        anchors = (
            0xF800,  # red
            0xFD20,  # orange
            0xFFE0,  # yellow
            0x07E0,  # green
            0x07FF,  # cyan
            0x001F,  # blue
            0xF81F,  # magenta
            0xF800,  # red
        )
        if span <= 0:
            return anchors[0]
        pos = pos % span
        seg_count = len(anchors) - 1
        seg_span = max(1, span // seg_count)
        seg = min(seg_count - 1, pos // seg_span)
        local_t = pos - (seg * seg_span)
        return self._mix565(anchors[seg], anchors[seg + 1], local_t, seg_span)

    def _draw_color_calibration_strip(self, y, h, frame):
        width = self.width
        span = max(1, width * 3)
        for x in range(width):
            color = self._rainbow565(frame + (x * 3), span)
            self._fb.fill_rect(x, y, 1, h, color)

    def _draw_display_selection_screen(self, preset, index, total, frame=0):
        self._fb.fill(self._c_bg)
        self._header("DISPLAY", color=self._c_accent)
        self._draw_panel(16, 52, 288, 176, border=self._c_panel_alt, fill=self._c_panel)
        self._centered_scaled(64, "Preset %d/%d" % (index, total), scale=2, color=self._c_text)
        self._centered_scaled(88, str(preset.get("name", "display")), scale=2, color=self._c_text_muted)
        cards = (
            (28, "RED", 0xF800),
            (121, "GREEN", 0x07E0),
            (214, "BLUE", 0x001F),
        )
        for card_x, label, color in cards:
            self._draw_panel(card_x, 110, 78, 42, border=self._c_panel_alt, fill=self._c_bg)
            text_x = card_x + max(4, (78 - self._text_width(label, "ui")) // 2)
            self._text(text_x, 124, label, color, bg=self._c_bg)
        self._draw_color_calibration_strip(166, 20, frame)
        self._centered_scaled(196, "Touch when colors look right", scale=1, color=self._c_text)
        self._centered_scaled(212, "Spectrum should sweep cleanly", scale=1, color=self._c_text_muted)
        self.show()

    def select_display_preset(self, presets, cycle_ms=2200, frame_step_ms=140):
        if self._touch is None:
            print("[TFT] Display selection unavailable: touch missing")
            return None
        presets = [normalize_display_config(item) for item in presets if isinstance(item, dict)]
        if not presets:
            return None
        self._touch_mode = None
        accepted = None
        start = time.ticks_ms()
        index = 0
        while accepted is None:
            preset = presets[index]
            self.apply_display_config(preset, clear=False)
            self._draw_display_selection_screen(preset, index + 1, len(presets), frame=0)
            print("[TFT] display preset", index + 1, preset)
            shown_at = time.ticks_ms()
            frame = 0
            last_frame_ms = shown_at
            while time.ticks_diff(time.ticks_ms(), shown_at) < cycle_ms:
                if self.has_display_selection_touch():
                    accepted = preset
                    self._wait_touch_release()
                    break
                now = time.ticks_ms()
                if time.ticks_diff(now, last_frame_ms) >= frame_step_ms:
                    frame = (frame + 11) % (self.width * 3)
                    self._draw_display_selection_screen(preset, index + 1, len(presets), frame=frame)
                    last_frame_ms = now
                time.sleep_ms(40)
            index = (index + 1) % len(presets)
            if time.ticks_diff(time.ticks_ms(), start) > 120000:
                break
        return accepted

    def _wait_touch_release(self, timeout_ms=1800):
        if self._touch is None:
            return
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
            if not self._touch.touched():
                return
            time.sleep_ms(25)

    def _collect_calibration_sample(self, timeout_ms=12000):
        if self._touch is None:
            return None
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
        if self._touch is None:
            self.show_message("CALIBRATE", "Touch driver missing", "Sync drivers/xpt2046.py")
            time.sleep_ms(900)
            return False
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

    def _draw_color_profile_screen(self, profile, frame):
        self._fb.fill(self._c_bg)
        self._header("COLOR", color=self._c_accent)
        self._draw_panel(16, 52, 288, 176, border=self._c_panel_alt, fill=self._c_panel)
        self._centered_scaled(64, str(profile.get("name", "color-profile")), scale=2, color=self._c_text)
        stripe_y = 104
        stripe_h = 32
        stripe_colors = (
            self._rainbow565(frame + 0, max(1, self.width * 6)),
            self._rainbow565(frame + 80, max(1, self.width * 6)),
            self._rainbow565(frame + 160, max(1, self.width * 6)),
            self._rainbow565(frame + 240, max(1, self.width * 6)),
        )
        for idx, color in enumerate(stripe_colors):
            self._fb.fill_rect(34 + (idx * 63), stripe_y, 55, stripe_h, color)
        cards = (
            (34, "RED", 0xF800),
            (126, "GREEN", 0x07E0),
            (218, "BLUE", 0x001F),
            (92, "ORANGE", self._c_warn),
        )
        for card_x, label, color in cards:
            card_y = 150 if label != "ORANGE" else 188
            card_w = 70 if label != "ORANGE" else 136
            self._draw_panel(card_x, card_y, card_w, 28, border=self._c_panel_alt, fill=self._c_bg)
            text_x = card_x + max(4, (card_w - self._text_width(label, "ui")) // 2)
            self._text(text_x, card_y + 8, label, color, bg=self._c_bg)
        self._centered_scaled(224, "Each profile shows for 3 seconds", scale=1, color=self._c_text_muted)
        self._centered_scaled(210, "Touch when colors are correct", scale=1, color=self._c_text)
        self.show()

    def _build_color_profiles(self):
        base = normalize_display_config(self._display_config)
        madctl_rgb = base.get("madctl", DEFAULT_DISPLAY_CONFIG["madctl"]) & 0xF7
        madctl_bgr = madctl_rgb | 0x08
        return (
            {
                "name": "RGB + swap",
                "rotation": base["rotation"],
                "madctl": madctl_rgb,
                "baudrate": base["baudrate"],
                "swap_bytes": True,
            },
            {
                "name": "RGB + direct",
                "rotation": base["rotation"],
                "madctl": madctl_rgb,
                "baudrate": base["baudrate"],
                "swap_bytes": False,
            },
            {
                "name": "BGR + swap",
                "rotation": base["rotation"],
                "madctl": madctl_bgr,
                "baudrate": base["baudrate"],
                "swap_bytes": True,
            },
            {
                "name": "BGR + direct",
                "rotation": base["rotation"],
                "madctl": madctl_bgr,
                "baudrate": base["baudrate"],
                "swap_bytes": False,
            },
        )

    def calibrate_display_colors(self, cycle_ms=3000, frame_step_ms=110):
        if self._touch is None:
            self.show_message("COLOR", "Touch driver missing", "Display check skipped")
            time.sleep_ms(900)
            return False
        self._touch_mode = None
        accepted = None
        start = time.ticks_ms()
        frame = 0
        profiles = self._build_color_profiles()
        index = 0
        while accepted is None:
            profile = profiles[index]
            self.apply_display_config(profile, clear=False)
            shown_at = time.ticks_ms()
            last_frame_ms = shown_at
            self._draw_color_profile_screen(profile, frame)
            while time.ticks_diff(time.ticks_ms(), shown_at) < cycle_ms:
                if self.has_display_selection_touch():
                    accepted = profile
                    self._wait_touch_release()
                    break
                now = time.ticks_ms()
                if time.ticks_diff(now, last_frame_ms) >= frame_step_ms:
                    frame = (frame + 13) % (self.width * 6)
                    self._draw_color_profile_screen(profile, frame)
                    last_frame_ms = now
                time.sleep_ms(35)
            index = (index + 1) % len(profiles)
            if time.ticks_diff(time.ticks_ms(), start) > 180000:
                break
        if accepted is None:
            self.show_message("COLOR", "Timed out", "Keeping current profile")
            time.sleep_ms(900)
            return False
        if not save_display_config(accepted):
            self.show_message("COLOR", "Save failed", "Keeping current profile")
            time.sleep_ms(900)
            return False
        loaded_cfg = load_display_config(accepted)
        self.apply_display_config(loaded_cfg, clear=True)
        self.invalidate()
        self.show_message("COLOR", "Saved", str(loaded_cfg.get("name", "profile")))
        time.sleep_ms(900)
        return True

    def calibrate_touch_and_display(self):
        if not self.calibrate_touch():
            return False
        return self.calibrate_display_colors()

    def _header(self, title, color=None):
        color = self._c_accent if color is None else color
        self._draw_topbar_to_fb(title, color, ram_only=False)

    def _status_card(self, x, y, label, ok):
        color = 0x07E0 if ok else 0xF800
        self._fb.rect(x, y, 94, 66, color)
        self._text_scaled(x + 10, y + 10, label, scale=2, color=0xFFFF)
        self._text_scaled(x + 20, y + 38, "OK" if ok else "ERR", scale=2, color=color)

    def show_startup_logo(self):
        if self._draw_raw_rgb565(0, 0, self.width, self.height, "/lib/tft_wordmark.raw"):
            self._boot_logo_visible = True
            return True
        self._fb.fill(self._c_bg)
        self._fb.fill_rect(0, 0, self.width, 3, self._c_accent)
        self._fb.fill_rect(0, self.height - 3, self.width, 3, self._c_accent)
        self._fb.fill_rect(68, 83, 184, 4, self._c_accent)
        self._boot_logo_visible = True
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
        if not self._boot_logo_visible or force:
            self.show_startup_logo()
        return True

    def show_home(self, sd_ok, imu_ok, gps_ok, gps_sentences=0, countdown_ms=None, paused=False, auto_log_enabled=True, track_name="", mount_label=""):
        self._touch_mode = "home"
        key = ("home", bool(sd_ok), bool(imu_ok), bool(gps_ok), str(track_name), str(mount_label))
        if self._skip_same_render(key):
            self.refresh_topbar("RaceSense")
            return True
        self._start_content_screen()
        self.refresh_topbar("RaceSense", force=True)
        self._status_line(18, 64, "GPS", gps_ok)
        self._status_line(117, 64, "IMU", imu_ok)
        self._status_line(216, 64, "SD", sd_ok)
        self._draw_panel(18, 116, 284, 42, border=self._c_panel_alt, fill=self._c_panel)
        self._text(30, 126, "TRACK", self._c_text_muted, bg=self._c_panel)
        if mount_label:
            mount_text = "  [%s]" % str(mount_label).upper()
        else:
            mount_text = ""
        name = self._fit_text_px((track_name or "No track") + mount_text, 190, "ui")
        self._text(98, 126, name, self._c_text if track_name else self._c_text_dim, bg=self._c_panel)
        self._button(10, 176, 96, 50, "SYNC", self._c_accent, self._c_bg)
        self._icon_button(112, 176, 96, 50, "gear", self._c_panel_alt, self._c_text)
        self._button(214, 176, 96, 50, "LOG", self._c_panel_alt, self._c_text)
        self._show_regions((
            (0, 58, 320, 40),
            (18, 116, 284, 42),
            (10, 176, 300, 50),
        ))
        return True

    def show_decision(self, *args, **kwargs):
        return self.show_home(*args, **kwargs)

    def show_settings(self, ssid="", auto_log_enabled=True, pending_count=0, scroll_index=0):
        self._touch_mode = "settings"
        total_items = 6
        max_scroll = max(0, total_items - 3)
        scroll_index = max(0, min(max_scroll, int(scroll_index or 0)))
        self._settings_scroll_index = scroll_index
        key = ("settings", str(ssid), bool(auto_log_enabled), int(pending_count or 0), scroll_index)
        if self._skip_same_render(key):
            self.refresh_topbar("RaceSense")
            return True
        self._start_content_screen()
        self._button(10, 46, 96, 38, "BACK", self._c_panel_alt, self._c_text)
        self._text(128, 58, "SETTINGS", self._c_text)
        self._draw_panel(18, 88, 252, 136, border=self._c_panel_alt, fill=self._c_bg)
        items = (
            ("wifi", "wifi", self._fit_text_px(ssid or "Not configured", 170, "ui"), self._c_text if ssid else self._c_bad),
            ("track", "track", "view selected layout", self._c_text_dim),
            ("imu_profiles", "mount profile", "select or recalibrate", self._c_text_dim),
            ("calibrate", "calibration", "touch and display setup", self._c_text_dim),
            ("toggle_auto_log", "auto log", "on" if auto_log_enabled else "off", self._c_text if auto_log_enabled else self._c_bad),
            ("archive", "archive all", "%d file%s pending" % (int(pending_count or 0), "" if int(pending_count or 0) == 1 else "s"), self._c_warn if pending_count else self._c_text_dim),
        )
        visible = items[scroll_index : scroll_index + 3]
        row_y = 96
        for action, title, detail, detail_color in visible:
            self._draw_panel(22, row_y, 248, 36, border=self._c_panel_alt, fill=self._c_panel)
            self._text(38, row_y + 6, title.upper(), self._c_text, bg=self._c_panel)
            detail_text = self._fit_text_px(str(detail), 190, "ui")
            self._text(38, row_y + 20, detail_text, detail_color, bg=self._c_panel)
            if action == "toggle_auto_log":
                self._toggle(214, row_y + 6, 36, 16, auto_log_enabled)
            else:
                self._text(236, row_y + 12, ">", self._c_accent if action in ("wifi", "track", "archive") else self._c_text_dim, bg=self._c_panel)
            row_y += 42
        can_up = scroll_index > 0
        can_down = scroll_index < max_scroll
        self._arrow_button(278, 104, 28, 40, "up", enabled=can_up)
        self._arrow_button(278, 168, 28, 40, "down", enabled=can_down)
        self._show_region(0, 40, 320, 200)
        return True

    def show_imu_profiles(self, profiles, selected_id=""):
        self._touch_mode = "imu_profiles"
        key = ("imu_profiles", str(selected_id), tuple(sorted(str((p or {}).get("id") or "") for p in (profiles or []))))
        if self._skip_same_render(key):
            self.refresh_topbar("RaceSense")
            return True
        self._start_content_screen()
        self.refresh_topbar("RaceSense", force=True)
        self._button(10, 46, 96, 38, "BACK", self._c_panel_alt, self._c_text)
        self._text(114, 58, "MOUNT SETUP", self._c_text)
        labels = ("tank", "tail", "stem", "generic")
        profile_map = {}
        for profile in profiles or []:
            profile_map[str(profile.get("label") or "").lower()] = profile
        row_y = 92
        for label in labels:
            profile = profile_map.get(label)
            is_selected = bool(profile and str(profile.get("id") or "") == str(selected_id or ""))
            fill = self._c_panel_alt if is_selected else self._c_panel
            border = self._c_accent if is_selected else self._c_panel_alt
            self._draw_panel(22, row_y, 276, 30, border=border, fill=fill)
            self._text(34, row_y + 8, label.upper(), self._c_text, bg=fill)
            detail = "saved - tap to use" if profile else "not saved - tap to calibrate"
            if is_selected:
                detail = "selected - tap to recalibrate"
            self._text(112, row_y + 9, self._fit_text_px(detail, 168, "ui"), self._c_text_dim, bg=fill)
            row_y += 34
        self._centered_scaled(228, "Tap a saved profile to use it", scale=1, color=self._c_text_muted)
        self._centered_scaled(212, "Tap selected/new profile to calibrate", scale=1, color=self._c_text_muted)
        self._show_region(0, 40, 320, 200)
        return True

    def show_imu_calibration_prompt(self, title, body, footer="Tap bottom band to continue"):
        self._touch_mode = "imu_prompt"
        self._fb.fill(self._c_bg)
        self._header(title)
        lines = [line for line in str(body).split("\n") if line]
        y = 58
        for line in lines[:6]:
            self._centered_scaled(y, self._truncate_text(line, 22), scale=2 if y < 90 else 1, color=self._c_text)
            y += 26 if y < 90 else 18
        self._button(28, 182, 264, 40, "CAPTURE", self._c_accent, self._c_bg)
        if footer:
            self._centered_scaled(162, self._truncate_text(footer, 32), scale=1, color=self._c_text_muted)
        self.show()
        return True

    def _draw_heading_arrow(self, cx, cy, radius, angle_deg, color):
        angle = math.radians(angle_deg)
        tip_x = int(cx + (math.sin(angle) * radius))
        tip_y = int(cy - (math.cos(angle) * radius))
        left_angle = angle - 2.55
        right_angle = angle + 2.55
        left_x = int(tip_x + (math.sin(left_angle) * 16))
        left_y = int(tip_y - (math.cos(left_angle) * 16))
        right_x = int(tip_x + (math.sin(right_angle) * 16))
        right_y = int(tip_y - (math.cos(right_angle) * 16))
        self._fb.line(cx, cy, tip_x, tip_y, color)
        self._fb.line(tip_x, tip_y, left_x, left_y, color)
        self._fb.line(tip_x, tip_y, right_x, right_y, color)
        self._fb.rect(cx - radius - 4, cy - radius - 4, (radius * 2) + 8, (radius * 2) + 8, self._c_panel_alt)

    def _draw_tilt_indicator(self, x, y, w, h, angle_deg, label):
        cx = x + (w // 2)
        cy = y + (h // 2)
        self._draw_panel(x, y, w, h, border=self._c_panel_alt, fill=self._c_bg)
        self._text(x + 8, y + 6, label, self._c_text_muted, bg=self._c_bg)
        line_half = max(18, min(34, (w // 2) - 16))
        angle = math.radians(max(-60.0, min(60.0, angle_deg)))
        dx = int(math.sin(angle) * line_half)
        dy = int(math.cos(angle) * line_half)
        self._fb.line(cx - dx, cy + dy, cx + dx, cy - dy, self._c_accent_soft)
        self._fb.fill_rect(cx - 2, cy - 2, 5, 5, self._c_text)
        self._centered_scaled(y + h - 14, "%+d deg" % int(round(angle_deg)), scale=1, color=self._c_text)

    def show_logging_validation(self, profile_name, heading_deg, pitch_deg, roll_deg, status_text):
        self._touch_mode = None
        key = ("imu_validate", str(profile_name), int(heading_deg), int(pitch_deg), int(roll_deg), str(status_text))
        if self._skip_render(key, min_interval_ms=120):
            return True
        self._fb.fill(self._c_bg)
        self.refresh_topbar("IMU CHECK", color=self._c_accent, force=True)
        self._draw_panel(8, 38, 148, 192, border=self._c_panel_alt, fill=self._c_panel)
        self._draw_panel(164, 38, 148, 192, border=self._c_panel_alt, fill=self._c_panel)
        self._centered_scaled(28, self._fit_text_px(str(profile_name or "PROFILE").upper(), 210, "ui"), scale=1, color=self._c_text)
        self._text(30, 52, "TOP VIEW", self._c_text_muted, bg=self._c_panel)
        self._draw_heading_arrow(82, 130, 44, heading_deg, self._c_accent_soft)
        self._centered_scaled(170, self._fit_text_px("%+d deg to bike fwd" % int(round(heading_deg)), 118, "ui"), scale=1, color=self._c_text)
        self._text(186, 52, "MOUNT ANGLE", self._c_text_muted, bg=self._c_panel)
        self._draw_tilt_indicator(176, 74, 124, 62, roll_deg, "FRONT")
        self._draw_tilt_indicator(176, 146, 124, 62, pitch_deg, "SIDE")
        status_color = self._c_good if "OK" in str(status_text) else self._c_warn if "CHECK" in str(status_text) else self._c_bad
        self._centered_scaled(218, self._fit_text_px(str(status_text or "IMU CHECK"), 180, "ui"), scale=1, color=status_color)
        self._show_region(0, 20, 320, 220)
        return True

    def show_archive_confirm(self, pending_count=0):
        self._touch_mode = "archive_confirm"
        pending_count = max(0, int(pending_count or 0))
        file_label = "%d file%s" % (pending_count, "" if pending_count == 1 else "s")
        key = ("archive_confirm", pending_count)
        if self._skip_same_render(key):
            self.refresh_topbar("RaceSense")
            return True
        self._start_content_screen()
        self.refresh_topbar("RaceSense")
        self._button(10, 46, 96, 38, "BACK", self._c_panel_alt, self._c_text)
        self._text(102, 58, "ARCHIVE ALL", self._c_text)
        self._draw_panel(18, 88, 284, 82, border=self._c_panel_alt, fill=self._c_panel)
        self._centered_scaled(106, "Move pending logs", scale=2, color=self._c_text)
        self._centered_scaled(130, self._fit_text_px(file_label + " to uploaded/", 220, "ui"), scale=1, color=self._c_text_muted)
        self._centered_scaled(148, "No cloud sync", scale=1, color=self._c_bad)
        self._button(166, 188, 136, 40, "YES", self._c_warn, self._c_bg)
        self._show_region(0, 40, 320, 200)
        return True

    def show_track_view(self, track_data, page=0):
        page = 1 if int(page or 0) else 0
        self._touch_mode = "track_detail" if page else "track_layout"
        track_name = ""
        if isinstance(track_data, dict):
            track_name = track_data.get("track_name") or track_data.get("name") or ""
        key = ("track_view", page, track_name)
        if self._skip_same_render(key):
            self.refresh_topbar("RaceSense")
            return True

        self._start_content_screen()
        self.refresh_topbar("RaceSense")
        self._button(10, 46, 96, 38, "BACK", self._c_panel_alt, self._c_text)

        if not isinstance(track_data, dict):
            self._draw_panel(18, 92, 284, 94, border=self._c_panel_alt, fill=self._c_panel)
            self._centered_scaled(118, "No active track", scale=2, color=self._c_text_dim)
            self._centered_scaled(150, "Sync to load", scale=1, color=self._c_text_muted)
            self._button(196, 194, 106, 38, "DETAILS", self._c_panel, self._c_text_muted)
            self._show_region(0, 40, 320, 200)
            return True

        if page == 0:
            self._show_track_layout_page(track_data)
        else:
            self._show_track_detail_page(track_data)
        self._show_region(0, 40, 320, 200)
        return True

    def _show_track_layout_page(self, track_data):
        name = self._fit_text_px(track_data.get("track_name") or track_data.get("name") or "Active track", 190, "ui")
        self._text(112, 58, name, self._c_text)
        self._draw_panel(18, 88, 284, 106, border=self._c_panel_alt, fill=self._c_panel)
        layout = self._prepare_logging_layout(track_data)
        if layout:
            for idx in range(1, len(layout["polyline"])):
                x0, y0 = layout["polyline"][idx - 1]
                x1, y1 = layout["polyline"][idx]
                self._fb.line(x0, y0 + 34, x1, y1 + 34, self._c_accent_soft)
            for idx, marker in enumerate(layout["sector_markers"]):
                mx = marker["x"]
                my = marker["y"] + 34
                self._fb.fill_rect(mx - 2, my - 2, 5, 5, self._c_warn)
                label = marker.get("label") or ("S%d" % (idx + 1))
                self._text(mx + 4, my - 6, self._fit_text_px(label, 20, "ui"), self._c_text_muted, bg=self._c_panel)
            if layout["start_marker"]:
                marker = layout["start_marker"]
                mx = marker[0]
                my = marker[1] + 34
                self._fb.fill_rect(mx - 3, my - 3, 7, 7, self._c_good)
                self._text(mx + 6, my - 6, "SF", self._c_text, bg=self._c_panel)
        else:
            self._centered_scaled(122, "Layout unavailable", scale=2, color=self._c_text_dim)
        self._text(24, 200, "Sector map", self._c_text_muted)
        self._button(196, 194, 106, 38, "DETAILS", self._c_accent, self._c_bg)

    def _show_track_detail_page(self, track_data):
        name = self._fit_text_px(track_data.get("track_name") or track_data.get("name") or "Track", 190, "ui")
        self._text(112, 58, name, self._c_text)
        tbl = track_data.get("tbl") if isinstance(track_data.get("tbl"), dict) else {}
        sectors = tbl.get("sectors") if isinstance(tbl.get("sectors"), list) else []
        tbl_total = 0.0
        for value in sectors:
            try:
                tbl_total += float(value or 0)
            except Exception:
                pass
        self._draw_panel(18, 84, 284, 54, border=self._c_panel_alt, fill=self._c_panel)
        self._text(30, 94, "BEST LAP", self._c_text_muted, bg=self._c_panel)
        lap_text = self._format_track_time(tbl_total) if tbl_total > 0 else "--.---"
        self._big_value(30, 108, lap_text, scale=4, color=self._c_text, shadow=False, bg=self._c_panel)

        self._draw_panel(18, 144, 284, 48, border=self._c_panel_alt, fill=self._c_panel)
        y = 154
        for idx in range(min(len(sectors), 7)):
            value = sectors[idx]
            sector_label = "S%d" % (idx + 1)
            sector_time = self._format_track_time(value)
            col = 24 if idx < 4 else 164
            row_y = y + ((idx % 4) * 10)
            self._text(col, row_y, sector_label, self._c_text_muted, bg=self._c_panel)
            self._text(col + 26, row_y, self._fit_text_px(sector_time, 90, "ui"), self._c_text, bg=self._c_panel)
        if not sectors:
            self._centered_scaled(164, "No TBL sectors", scale=1, color=self._c_text_dim)
        self._button(196, 194, 106, 38, "LAYOUT", self._c_accent, self._c_bg)

    def _format_track_time(self, value):
        try:
            total_ms = int(round(float(value or 0) * 1000.0))
        except Exception:
            return "--.---"
        if total_ms <= 0:
            return "--.---"
        minutes = total_ms // 60000
        seconds = (total_ms % 60000) / 1000.0
        if minutes > 0:
            return "%d:%06.3f" % (minutes, seconds)
        return "%.3fs" % (total_ms / 1000.0)

    def show_wifi_options(self, ssid=""):
        self._touch_mode = "wifi_options"
        key = ("wifi_options", str(ssid))
        if self._skip_same_render(key):
            self.refresh_topbar("RaceSense")
            return True
        self._start_content_screen()
        self._button(10, 46, 96, 38, "BACK", self._c_panel_alt, self._c_text)
        self._text(142, 48, "WIFI", self._c_text)
        self._draw_panel(18, 72, 284, 78, border=self._c_panel_alt, fill=self._c_panel)
        self._text(30, 86, "SAVED WIFI", self._c_text_muted, bg=self._c_panel)
        label = self._fit_text_px(ssid or "Not configured", 250, "ui")
        self._text(30, 110, label, self._c_text if ssid else self._c_bad, bg=self._c_panel)
        self._button(90, 184, 140, 44, "CHANGE", self._c_accent, self._c_bg)
        self._show_regions(((0, 40, 320, 118), (90, 184, 140, 44)))
        return True

    def show_first_time_setup(self, ap_name="RS-Core AP"):
        return self.show_message("SETUP", "No WiFi configured\nJoin " + str(ap_name), "Open portal")

    def show_pairing(self, ssid_hint="RS-Core AP"):
        return self.show_message("PAIRING", "Setup hotspot\n" + str(ssid_hint), "Open portal")

    def show_sync_searching(self, ssid, frame=0):
        self._touch_mode = "sync_searching"
        self._reset_sync_upload_screen()
        screen_key = ("sync_searching", str(ssid))
        frame = int(frame or 0) % 4
        if self._sync_search_screen_key != screen_key:
            self._sync_search_screen_key = screen_key
            self._fb.fill_rect(0, 40, self.width, self.height - 40, self._c_bg)
            self._display.fill_rect(0, 40, self.width, self.height - 40, self._c_bg)
            self._text(142, 48, "WIFI", self._c_text)
            self._draw_panel(18, 70, 284, 128, border=self._c_panel_alt, fill=self._c_panel)
            self._centered_scaled(170, "Searching", scale=2, color=self._c_text)
            self._draw_panel(18, 206, 178, 26, border=self._c_panel_alt, fill=self._c_bg)
            ssid_label = self._fit_text_px(str(ssid or "Saved WiFi"), 260, "ui")
            self._text(28, 213, self._fit_text_px(ssid_label, 158, "ui"), self._c_text_muted, bg=self._c_bg)
            self._button(206, 202, 96, 34, "EXIT", self._c_panel_alt, self._c_text)
            self._wifi_bars(160, 86, frame, self._c_accent)
            self._show_region(0, 40, 320, 200)
            return True
        self.refresh_topbar("RaceSense")
        key = ("sync_searching_frame", screen_key, frame)
        if self._skip_render(key, 180):
            return True
        self._fb.fill_rect(86, 82, 148, 72, self._c_panel)
        self._wifi_bars(160, 86, frame, self._c_accent)
        self._show_region(86, 82, 148, 72)
        return True

    def show_sync_connected(self, ssid, ip):
        self._touch_mode = None
        self._reset_sync_upload_screen()
        self._reset_sync_search_screen()
        key = ("sync_connected", str(ssid), str(ip))
        if self._skip_render(key, 700):
            self.refresh_topbar("RaceSense")
            return True
        self._start_content_screen()
        self.refresh_topbar("RaceSense")
        self._draw_panel(18, 54, 284, 132, border=self._c_accent, fill=self._c_panel)
        self._centered_scaled(74, "Connected", scale=3, color=self._c_text)
        self._centered_scaled(120, self._truncate_text(str(ssid or "WiFi"), 18), scale=2, color=self._c_accent_soft)
        self._centered_scaled(154, self._truncate_text(str(ip or ""), 20), scale=1, color=self._c_text_muted)
        self._centered_scaled(210, "Starting cloud sync", scale=1, color=self._c_text_muted)
        self._show_region(0, 40, 320, 200)
        return True

    def show_heartbeat(self, state, host="", detail=""):
        self._touch_mode = None
        self._reset_sync_upload_screen()
        self._reset_sync_search_screen()
        ok = "ACK" in str(state).upper() or "OK" in str(state).upper()
        key = ("heartbeat", ok, str(state))
        if self._skip_render(key, 180):
            return True
        self._fb.fill(self._c_bg)
        self._header("CLOUD")
        self._draw_panel(64, 54, 192, 132, border=self._c_panel_alt, fill=self._c_panel)
        self._draw_heart(160, 112, self._c_good if ok else self._c_bad)
        if ok:
            self._centered_scaled(188, "racesense servers", scale=1, color=self._c_text_muted)
            self._centered_scaled(202, "says hello back", scale=1, color=self._c_text_muted)
        else:
            self._centered_scaled(188, "saying hi to", scale=1, color=self._c_text_muted)
            self._centered_scaled(202, "racesense servers", scale=1, color=self._c_text_muted)
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
        self._reset_sync_search_screen()
        key = ("sync_queue", tuple([str(f) for f in files[:3]]), len(files), int(total_bytes or 0), bool(allow_reboot))
        if self._skip_render(key, 500):
            self.refresh_topbar("RaceSense")
            return True
        self._start_content_screen()
        self.refresh_topbar("RaceSense")
        self._text(120, 46, "SYNC QUEUE", self._c_text)
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
        self._button(10, 190, 92, 40, "PAIR", self._c_panel_alt, self._c_text)
        self._button(110, 190, 92, 40, "EXIT", self._c_panel_alt, self._c_text)
        if allow_reboot:
            self._button(210, 190, 100, 40, "REBOOT", self._c_accent, self._c_bg)
        else:
            self._button(210, 190, 100, 40, "WAIT", self._c_panel, self._c_text_muted)
        self._show_region(0, 40, 320, 200)
        return True

    def show_sync_upload(self, filename, file_index, total_files, sent_bytes, total_bytes, global_current=0, global_total=0, phase="UPLOADING", detail="", batch_count=0, total_batches=0):
        self._touch_mode = None
        self.refresh_topbar("RaceSense")
        global_pct, eta_text, rate_text = self._sync_stats(global_current, global_total)
        remaining_mb = self._format_mb_label(max(0, int(global_total or 0) - int(global_current or 0)))
        file_size_label = self._format_mb_label(total_bytes)
        file_pos = "%d/%d" % (int(file_index or 0) + 1, int(total_files or 1))
        file_pos_w = self._text_width(file_pos, "ui")
        file_line_max = max(40, 262 - file_pos_w - 10)
        short_name = self._fit_text_px("%s %s" % (str(filename).split("/")[-1], file_size_label), file_line_max, "ui")
        chunks = "--"
        if total_batches:
            chunks = "%d/%d" % (int(batch_count or 0), int(total_batches or 0))
        elif total_bytes:
            chunks = "%s/%s" % (self._format_bytes_compact(sent_bytes), self._format_bytes_compact(total_bytes))
        values = (short_name, int(file_index or 0), int(total_files or 0), global_pct, remaining_mb, eta_text, chunks)
        screen_key = ("sync_upload_screen",)
        if self._sync_upload_screen_key != screen_key:
            self._reset_sync_search_screen()
            self._sync_upload_screen_key = screen_key
            self._sync_upload_values = None
            self._start_content_screen()
            self._text(142, 48, "SYNC", self._c_text)
            self._draw_panel(12, 46, 296, 178, border=self._c_panel_alt, fill=self._c_panel)
            self._text(24, 62, "OVERALL PROGRESS", self._c_text_muted)
            self._text(24, 144, "CURRENT FILE", self._c_text_muted)
            self._text(24, 184, "ETA", self._c_text_muted)
            self._text(176, 184, "CHUNKS", self._c_text_muted)
            self._show_region(0, 40, 320, 200)
        if self._sync_upload_values == values and self._skip_render(("sync_upload_hold", values), 220):
            return True
        self._sync_upload_values = values

        pct_text = "%d%%" % global_pct
        self._fb.fill_rect(22, 78, 276, 58, self._c_panel)
        self._big_value(24, 78, pct_text, scale=4, color=self._c_accent, bg=self._c_panel)
        remaining_x = 294 - self._text_width(remaining_mb, "ui")
        self._text(max(120, remaining_x), 92, remaining_mb, self._c_text_muted, bg=self._c_panel)
        self._progress_bar(24, 124, 262, 10, global_pct, fill=self._c_accent, border=self._c_panel_alt, bg=self._c_bg)
        self._show_region(22, 76, 276, 62)

        self._fb.fill_rect(22, 156, 276, 20, self._c_panel)
        self._text(24, 156, short_name, self._c_text, bg=self._c_panel)
        self._text(288 - self._text_width(file_pos, "ui"), 156, file_pos, self._c_text_dim, bg=self._c_panel)
        self._show_region(22, 154, 276, 24)

        self._fb.fill_rect(22, 198, 140, 30, self._c_panel)
        self._big_value(24, 202, eta_text, scale=3, color=self._c_text, shadow=False, bg=self._c_panel)
        self._show_region(22, 196, 140, 34)

        self._fb.fill_rect(166, 198, 128, 30, self._c_panel)
        self._big_value(168, 202, self._fit_text_px(chunks, 124, "data"), scale=3, color=self._c_text, shadow=False, bg=self._c_panel)
        self._show_region(166, 196, 128, 34)
        return True

    def show_sync_result(self, ok, filename="", detail="", allow_reboot=False):
        self._touch_mode = "sync_done" if allow_reboot else "sync_repair"
        self._reset_sync_metrics()
        self._reset_sync_upload_screen()
        self._reset_sync_search_screen()
        key = ("sync_result", bool(ok), str(filename), str(detail), bool(allow_reboot))
        if self._skip_render(key, 700):
            self.refresh_topbar("RaceSense")
            return True
        title = "SYNC OK" if ok else "SYNC FAIL"
        self._start_content_screen()
        self.refresh_topbar("RaceSense")
        self._text(124, 48, title, self._c_text)
        y = 54
        if filename:
            self._centered_scaled(y, self._truncate_text(str(filename).split("/")[-1], 20), scale=2, color=self._c_text)
            y += 28
        if detail:
            for line in str(detail).split("\n")[:3]:
                if line:
                    self._centered_scaled(y, self._truncate_text(line, 22), scale=2, color=self._c_text_dim)
                    y += 22
        self._button(10, 184, 92, 44, "REPAIR", self._c_panel, self._c_text)
        self._button(110, 184, 92, 44, "EXIT", self._c_panel_alt, self._c_text)
        if allow_reboot:
            self._button(210, 184, 100, 44, "REBOOT", self._c_accent, self._c_bg)
        else:
            self._button(210, 184, 100, 44, "WAIT", self._c_panel, self._c_text_muted)
        self._show_region(0, 40, 320, 200)
        return True

    def show_sync_complete(self, synced_count=0, track_name="", allow_reboot=False):
        self._touch_mode = "sync_done" if allow_reboot else "sync_repair"
        self._reset_sync_metrics()
        self._reset_sync_upload_screen()
        self._reset_sync_search_screen()
        key = ("sync_complete", int(synced_count or 0), str(track_name), bool(allow_reboot))
        if self._skip_render(key, 700):
            self.refresh_topbar("RaceSense")
            return True
        self._start_content_screen()
        self.refresh_topbar("RaceSense")
        self._text(112, 48, "SYNC DONE", self._c_text)
        self._draw_panel(12, 48, 296, 138, border=self._c_panel_alt, fill=self._c_panel)
        self._status_pill(22, 58, 132, "FILES SYNCED", str(max(0, int(synced_count or 0))), self._c_accent)
        self._status_pill(166, 58, 132, "CLOUD", "READY", self._c_accent)
        self._status_pill(22, 92, 276, "ACTIVE TRACK", self._truncate_text(track_name or "NONE", 24), self._c_text)
        self._text(24, 136, "STATUS", self._c_text_muted)
        self._text(24, 150, "Upload complete. Ready to exit.", self._c_text)
        self._button(10, 190, 92, 40, "PAIR", self._c_panel_alt, self._c_text)
        self._button(110, 190, 92, 40, "EXIT", self._c_panel_alt, self._c_text)
        if allow_reboot:
            self._button(210, 190, 100, 40, "REBOOT", self._c_accent, self._c_bg)
        else:
            self._button(210, 190, 100, 40, "WAIT", self._c_panel, self._c_text_muted)
        self._show_region(0, 40, 320, 200)
        return True

    def show_sync_idle(self, hb_ok, pending_count=0, pending_bytes=0, low_power=False, allow_reboot=False, phase_label="", last_result="", track_name=""):
        self._touch_mode = "sync_done" if allow_reboot else "sync_repair"
        self._reset_sync_metrics()
        self._reset_sync_upload_screen()
        self._reset_sync_search_screen()
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
            self.refresh_topbar("RaceSense")
            return True
        self._start_content_screen()
        self.refresh_topbar("RaceSense")
        self._text(120, 46, "SYNC READY", self._c_text)
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
        self._button(10, 190, 92, 40, "PAIR", self._c_panel_alt, self._c_text)
        self._button(110, 190, 92, 40, "EXIT", self._c_panel_alt, self._c_text)
        if allow_reboot:
            self._button(210, 190, 100, 40, "REBOOT", self._c_accent, self._c_bg)
        else:
            self._button(210, 190, 100, 40, "WAIT", self._c_panel, self._c_text_muted)
        self._show_region(0, 40, 320, 200)
        return True

    def show_sync_wifi_failed(self, ssid="", allow_retry=True):
        self._touch_mode = "sync_retry" if allow_retry else "sync_repair"
        self._reset_sync_metrics()
        self._reset_sync_upload_screen()
        self._reset_sync_search_screen()
        key = ("sync_wifi_failed", str(ssid), bool(allow_retry))
        if self._skip_render(key, 700):
            self.refresh_topbar("RaceSense")
            return True
        self._start_content_screen()
        self.refresh_topbar("RaceSense")
        self._text(124, 48, "SYNC FAIL", self._c_text)
        self._centered_scaled(62, "WiFi failed", scale=3, color=self._c_text)
        if ssid:
            self._centered_scaled(106, self._truncate_text(str(ssid), 20), scale=2, color=self._c_text_dim)
        if allow_retry:
            self._button(10, 184, 92, 44, "SCAN", self._c_accent, self._c_bg)
            self._button(110, 184, 92, 44, "REPAIR", self._c_panel, self._c_text)
            self._button(210, 184, 100, 44, "EXIT", self._c_panel_alt, self._c_text)
        else:
            self._button(10, 184, 142, 44, "REPAIR", self._c_panel, self._c_text)
            self._button(168, 184, 142, 44, "EXIT", self._c_panel_alt, self._c_text)
        self._show_region(0, 40, 320, 200)
        return True

    def show_logging_started(self, filename, track_name=None, elapsed_minutes=0, force=False, track_data=None):
        self._touch_mode = None
        self._set_logging_context(track_name=track_name, elapsed_minutes=elapsed_minutes, gps_ok=True, track_data=track_data)
        self._logging_status_mode = "status"
        self._logging_status_text = "READY"
        self._logging_status_color = "orange"
        self._logging_last_lap_text = "--.---"
        self._logging_last_lap_color = self._c_text
        self._logging_has_lap = False
        self._draw_logging_background(track_data)
        self.show()
        return True

    def show_logging_live(self, filename, sats=0, gps_ok=False, track_name=None, elapsed_minutes=0, track_data=None):
        self._touch_mode = None
        self._set_logging_context(track_name=track_name, elapsed_minutes=elapsed_minutes, gps_ok=gps_ok, track_data=track_data)
        self._draw_logging_background(track_data)
        self.show()
        return True

    def show_track_event(self, event, track_name=None, sector=None, track_data=None):
        self._touch_mode = None
        self._set_logging_context(
            track_name=track_name or self._logging_track_name,
            elapsed_minutes=self._logging_elapsed_minutes,
            gps_ok=self._logging_gps_ok,
            track_data=track_data,
        )
        self._apply_logging_event(event)
        if self._logging_screen_active:
            self.refresh_topbar("LOGGING", color=self._c_good if self._logging_gps_ok else self._c_bad)
            if str((event or {}).get("type") or "") == "lap_complete":
                self._draw_logging_lap_time_panel()
                self._show_region(10, 68, 300, 118)
            return True
        self._draw_logging_background(track_data)
        self.show()
        return True

    def show_storage_critical(self, used_kb, total_kb, reason="Storage critical"):
        self._touch_mode = None
        pct = 0 if total_kb <= 0 else int((used_kb * 100) / total_kb)
        return self.show_message("STORAGE", "%s\n%d%% full" % (reason, pct), "%d/%d KB" % (used_kb, total_kb))

    def sync_touch(self):
        point, now = self._touch_point()
        if not point:
            return None
        x = point["sx"]
        y = point["sy"]
        print("[TFT] touch:", x, y, self._touch_mode)
        if self._touch_mode == "sync_searching":
            if 206 <= x <= 319 and 190 <= y <= 239:
                self._last_touch_ms = now
                return "exit"
        if self._touch_mode in ("sync_repair", "sync_done"):
            if 110 <= x <= 209 and 176 <= y <= 239:
                self._last_touch_ms = now
                return "exit"
            if 0 <= x <= 109 and 176 <= y <= 239:
                self._last_touch_ms = now
                return "repair"
            if self._touch_mode == "sync_done" and 210 <= x <= 319 and 176 <= y <= 239:
                self._last_touch_ms = now
                return "reboot"
        if self._touch_mode == "sync_retry":
            if 210 <= x <= 319 and 176 <= y <= 239:
                self._last_touch_ms = now
                return "exit"
            if 0 <= x <= 109 and 176 <= y <= 239:
                self._last_touch_ms = now
                return "retry_wifi"
            if 110 <= x <= 209 and 176 <= y <= 239:
                self._last_touch_ms = now
                return "repair"
        return None

    def decision_touch(self):
        point, now = self._touch_point()
        if not point:
            return None
        x = point["sx"]
        y = point["sy"]
        print("[TFT] touch:", x, y)
        # Keep the active area centered, but generous enough for calibration
        # drift and imperfect finger taps on the resistive panel.
        if y < 150 or y > 239:
            return None
        if 0 <= x <= 109:
            self._last_touch_ms = now
            return "yes"
        if 110 <= x <= 210:
            self._last_touch_ms = now
            return "settings"
        if 211 <= x <= 319:
            self._last_touch_ms = now
            return "no"
        return None

    def home_touch(self):
        return self.decision_touch()

    def settings_touch(self):
        point, now = self._touch_point()
        if not point:
            return None
        x = point["sx"]
        y = point["sy"]
        print("[TFT] touch:", x, y, self._touch_mode)
        if self._touch_mode == "archive_confirm":
            if 0 <= x <= 116 and 40 <= y <= 92:
                self._last_touch_ms = now
                return "back"
            if 160 <= x <= 319 and 180 <= y <= 239:
                self._last_touch_ms = now
                return "archive_yes"
            return None
        if self._touch_mode == "wifi_options":
            if 0 <= x <= 116 and 40 <= y <= 92:
                self._last_touch_ms = now
                return "back"
            if 90 <= x <= 230 and 176 <= y <= 239:
                self._last_touch_ms = now
                return "wifi_change"
            return None
        if self._touch_mode == "track_layout":
            if 0 <= x <= 116 and 40 <= y <= 92:
                self._last_touch_ms = now
                return "back"
            if 190 <= x <= 319 and 186 <= y <= 239:
                self._last_touch_ms = now
                return "track_next"
            return None
        if self._touch_mode == "track_detail":
            if 0 <= x <= 116 and 40 <= y <= 92:
                self._last_touch_ms = now
                return "back"
            if 190 <= x <= 319 and 186 <= y <= 239:
                self._last_touch_ms = now
                return "track_prev"
            return None
        if self._touch_mode == "imu_profiles":
            if 0 <= x <= 116 and 40 <= y <= 92:
                self._last_touch_ms = now
                return "back"
            rows = (
                (92, 122, "tank"),
                (126, 156, "tail"),
                (160, 190, "stem"),
                (194, 224, "generic"),
            )
            for y0, y1, label in rows:
                if 22 <= x <= 298 and y0 <= y <= y1:
                    self._last_touch_ms = now
                    return "imu_profile_" + label
            return None
        if self._touch_mode == "imu_prompt":
            if 0 <= x <= 116 and 40 <= y <= 92:
                self._last_touch_ms = now
                return "back"
            if 28 <= x <= 292 and 180 <= y <= 239:
                self._last_touch_ms = now
                return "capture"
            return None
        max_scroll = 3
        if 0 <= x <= 116 and 40 <= y <= 92:
            self._last_touch_ms = now
            return "back"
        if 278 <= x <= 306 and 104 <= y <= 144 and self._settings_scroll_index > 0:
            self._last_touch_ms = now
            return "settings_up"
        if 278 <= x <= 306 and 168 <= y <= 208 and self._settings_scroll_index < max_scroll:
            self._last_touch_ms = now
            return "settings_down"
        if 22 <= x <= 270:
            action_map = ("wifi", "track", "imu_profiles", "calibrate", "toggle_auto_log", "archive")
            rows = (
                (96, 132),
                (138, 174),
                (180, 216),
            )
            for idx, bounds in enumerate(rows):
                y0, y1 = bounds
                if y0 <= y <= y1:
                    item_index = self._settings_scroll_index + idx
                    if 0 <= item_index < len(action_map):
                        self._last_touch_ms = now
                        return action_map[item_index]
                    return None
        return None
