import _thread
import time

from drivers.oled import SH1106_I2C, SSD1306_I2C


CHAR_W = 8
CHAR_H = 8
SAFE_RIGHT_PX = 8


def _short_name(path_or_name):
    try:
        return str(path_or_name).split("/")[-1]
    except Exception:
        return str(path_or_name)


class OLEDStatus:
    def __init__(self, i2c, addr=0x3C, controller="sh1106", width=128, height=64):
        self._lock = _thread.allocate_lock()
        self._enabled = False
        self._display = None
        self._width = width
        self._height = height
        self._battery_pct = None
        self._battery_pct_filtered = None
        self._sd_ok = None
        self._sd_pct = None
        try:
            if (controller or "sh1106").lower() == "ssd1306":
                self._display = SSD1306_I2C(width, height, i2c, addr=addr)
            else:
                self._display = SH1106_I2C(width, height, i2c, addr=addr)
            self._prime_panel()
            self._enabled = True
        except Exception as e:
            print("[OLED] Init Failed:", e)

    def _prime_panel(self):
        # Raw wake is handled before OLEDStatus is created. Keep constructor init visually quiet.
        self._display.fill(0)
        self._display.show()
        time.sleep_ms(50)

    def is_enabled(self):
        return self._enabled and self._display is not None

    def set_context(self, battery_pct=None, sd_ok=None, sd_pct=None):
        if battery_pct is not None:
            try:
                battery_pct = int(battery_pct)
            except Exception:
                battery_pct = None
        if battery_pct is not None:
            battery_pct = max(0, min(100, battery_pct))
            if self._battery_pct_filtered is None:
                self._battery_pct_filtered = float(battery_pct)
                self._battery_pct = battery_pct
            else:
                self._battery_pct_filtered = (self._battery_pct_filtered * 0.85) + (battery_pct * 0.15)
                filtered_pct = int(round(self._battery_pct_filtered))
                if self._battery_pct is None or abs(filtered_pct - self._battery_pct) >= 2:
                    self._battery_pct = filtered_pct
        if sd_ok is not None:
            self._sd_ok = bool(sd_ok)
        if sd_pct is not None:
            try:
                self._sd_pct = max(0, min(100, int(sd_pct)))
            except Exception:
                self._sd_pct = None

    def _max_chars(self, reserve_px=0):
        usable = max(0, self._width - reserve_px - SAFE_RIGHT_PX)
        return max(1, usable // CHAR_W)

    def _fit_text(self, text, reserve_px=0):
        text = str(text)
        max_chars = self._max_chars(reserve_px=reserve_px)
        if len(text) <= max_chars:
            return text
        return text[:max_chars]

    def _center_x(self, text):
        text = self._fit_text(text, reserve_px=1)
        width = len(text) * CHAR_W
        x = (self._width - width) // 2
        return 0 if x < 0 else x

    def _draw_text(self, x, y, text, color=1):
        x = int(x)
        reserve_px = max(0, x)
        self._display.text(self._fit_text(text, reserve_px=reserve_px), x, int(y), color)

    def _draw_center(self, y, text, color=1):
        self._draw_text(self._center_x(text), y, text, color)

    def _draw_bold(self, x, y, text, color=1):
        text = self._fit_text(text, reserve_px=int(x) + 1)
        self._draw_text(x, y, text, color)
        self._draw_text(x + 1, y, text, color)

    def _draw_center_bold(self, y, text, color=1):
        text = self._fit_text(text, reserve_px=1)
        width = (len(text) * CHAR_W) + 1
        x = (self._width - width) // 2
        if x < 0:
            x = 0
        self._draw_bold(x, y, text, color)

    def _draw_battery_icon(self, x, y, color=0):
        self._display.rect(x, y, 10, 6, color)
        self._display.fill_rect(x + 10, y + 2, 1, 2, color)
        if self._battery_pct is None:
            return
        fill_w = int((max(0, min(100, self._battery_pct)) * 8) / 100)
        if fill_w > 0:
            self._display.fill_rect(x + 1, y + 1, fill_w, 4, color)

    def _draw_sd_icon(self, x, y, color=0):
        self._display.rect(x + 1, y, 8, 8, color)
        self._display.fill_rect(x + 6, y, 2, 2, color)
        self._display.hline(x + 2, y + 3, 5, color)
        self._display.hline(x + 2, y + 5, 5, color)

    def _draw_header(self, title):
        self._display.fill_rect(0, 0, self._width, 12, 1)
        self._draw_center(2, title, 0)

    def _draw_status_row(self, y, color=1):
        if self._battery_pct is not None:
            self._draw_battery_icon(0, y + 1, color)
            self._draw_text(12, y, "%d%%" % max(0, min(100, int(self._battery_pct))), color)
        if self._sd_ok is not None:
            right_x = self._width - 36
            if right_x < 72:
                right_x = 72
            self._draw_sd_icon(right_x, y, color)
            if self._sd_ok and self._sd_pct is not None:
                self._draw_text(right_x + 11, y, "%d%%" % self._sd_pct, color)
            else:
                self._draw_text(right_x + 11, y, "OK" if self._sd_ok else "--", color)

    def _draw_footer(self, footer):
        if footer:
            self._draw_center(self._height - CHAR_H, footer, 1)

    def _render_screen(self, title, lines=None, footer=None, progress=None):
        self._display.fill(0)
        self._draw_header(title)
        y = 16
        self._draw_status_row(y, 1)
        y += 10
        if lines:
            for line in lines[:4]:
                self._draw_text(0, y, line)
                y += 10
        if progress is not None:
            value, maximum = progress
            maximum = max(1, int(maximum))
            value = max(0, min(int(value), maximum))
            bar_x = 4
            bar_y = self._height - 12
            bar_w = self._width - 8
            bar_h = 8
            self._display.rect(bar_x, bar_y, bar_w, bar_h, 1)
            fill_w = ((bar_w - 2) * value) // maximum
            if fill_w > 0:
                self._display.fill_rect(bar_x + 1, bar_y + 1, fill_w, bar_h - 2, 1)
        else:
            self._draw_footer(footer)
        self._display.show()

    def _render_message(self, title, body="", footer=""):
        lines = []
        if body:
            for line in str(body).split("\n"):
                if line:
                    lines.append(line)
        self._render_screen(title, lines=lines, footer=footer if footer else "")

    def _show(self, kind, *args):
        if not self.is_enabled():
            return False
        with self._lock:
            if kind == "screen":
                self._render_screen(*args)
            else:
                self._render_message(*args)
        return True

    def tick(self, force=False):
        return False

    def show_message(self, title, body="", footer="", force=False):
        return self._show("message", title, body, footer)

    def show_startup_logo(self):
        if not self.is_enabled():
            return False
        with self._lock:
            self._display.fill(0)
            self._display.fill_rect(0, 0, self._width, 16, 1)
            self._draw_center_bold(4, "RACESENSE", 0)
            self._display.hline(12, 24, self._width - 24, 1)
            self._draw_center_bold(32, "RS-CORE", 1)
            self._display.show()
        return True

    def show_boot(self, stage, sd_ok=None, imu_ok=None, gps_ok=None, gps_baud=None, gps_rate_hz=None, storage_info=None, force=False):
        lines = [stage]
        if sd_ok is not None:
            lines.append("SD: " + ("OK" if sd_ok else "ERR"))
        if imu_ok is not None:
            lines.append("IMU: " + ("OK" if imu_ok else "ERR"))
        if gps_ok is not None:
            lines.append("GPS: " + ("OK" if gps_ok else "ERR"))
        if gps_baud is not None and gps_rate_hz is not None:
            lines.append("GPS %s/%sHz" % (gps_baud, gps_rate_hz))
        return self._show("screen", "BOOT", lines, "Starting", None)

    def show_decision(self, sd_ok, imu_ok, gps_ok, gps_sentences=0, countdown_ms=None):
        lines = [
            "SD: " + ("OK" if sd_ok else "ERR"),
            "IMU: " + ("OK" if imu_ok else "ERR"),
            "GPS: " + ("OK" if gps_ok else ("WAIT %d/5" % gps_sentences)),
        ]
        footer = "Press sync to upload"
        if countdown_ms is not None and gps_ok:
            footer = "Sync in %ds" % max(0, countdown_ms // 1000)
        return self._show("screen", "SYNC?", lines, footer, None)

    def show_setup_needed(self):
        return self.show_message("SETUP", "No WiFi saved", "Hold for pairing")

    def show_first_time_setup(self):
        return self.show_message("SETUP", "First-time setup", "Open pairing mode")

    def show_flash_transfer(self):
        return self._show("screen", "STORAGE", ["Moving files to SD", "Please wait"], "Internal -> SD", None)

    def show_pairing(self, ssid_hint="RS-Core AP"):
        return self._show("screen", "PAIRING", ["Hotspot active", ssid_hint], "Open portal", None)

    def show_sync_searching(self, ssid):
        return self._show("screen", "SYNC", ["Searching WiFi", ssid or ""], "STA connect", None)

    def show_sync_connected(self, ssid, ip):
        return self._show("screen", "SYNC", ["WiFi connected", ssid or "", ip or ""], "Cloud handshake", None)

    def show_heartbeat(self, state, host="", detail=""):
        lines = [state]
        if host:
            lines.append(host)
        if detail:
            lines.append(detail)
        return self._show("screen", "HEARTBEAT", lines, "Cloud link", None)

    def show_track_sync(self, track_name):
        return self._show("screen", "TRACK", ["Server track", track_name or "None"], "Track metadata", None)

    def show_sync_queue(self, files):
        if not files:
            lines = ["No pending files"]
        else:
            lines = ["%d file(s)" % len(files)]
            for fname in files[:3]:
                lines.append(_short_name(fname))
        return self._show("screen", "SYNC QUEUE", lines, "Awaiting upload", None)

    def show_sync_upload(self, filename, file_index, total_files, sent_bytes, total_bytes, global_current=0, global_total=0):
        pct = 0 if total_bytes <= 0 else int((sent_bytes * 100) / total_bytes)
        lines = [
            "%d/%d %s" % (file_index + 1, total_files, _short_name(filename)),
            "%d/%d KB" % (sent_bytes // 1024, total_bytes // 1024),
        ]
        footer = "Uploading"
        if global_total > 0:
            footer = "Global %d%%" % int((global_current * 100) / global_total)
        return self._show("screen", "SYNCING", lines, footer, (pct, 100))

    def show_sync_result(self, ok, filename="", detail=""):
        title = "SYNC OK" if ok else "SYNC FAIL"
        lines = []
        if filename:
            lines.append(_short_name(filename))
        if detail:
            lines.append(str(detail))
        footer = "Upload complete" if ok else "Retry later"
        return self._show("screen", title, lines, footer, None)

    def show_sync_idle(self, hb_ok, pending_count=0, low_power=False):
        lines = ["Cloud: " + ("OK" if hb_ok else "WAIT"), "Pending: %d" % pending_count]
        if low_power:
            lines.append("Battery: low")
        return self._show("screen", "SYNC READY", lines, "Hold to pair", None)

    def show_logging_started(self, filename, track_name=None, force=False):
        lines = [_short_name(filename)]
        lines.append(track_name or "No active track")
        return self._show("screen", "LOGGING", lines, "", None)

    def show_track_event(self, event, track_name=None, sector=None):
        footer = track_name or ""
        if sector is not None:
            footer = "Sector %s" % sector
        return self._show("message", event, event.replace("_", " "), footer)

    def show_storage_critical(self, used_kb, total_kb, reason="Storage critical"):
        pct = 0 if total_kb <= 0 else int((used_kb * 100) / total_kb)
        lines = [reason, "%d/%d KB" % (used_kb, total_kb)]
        return self._show("screen", "STORAGE", lines, "", (pct, 100))
