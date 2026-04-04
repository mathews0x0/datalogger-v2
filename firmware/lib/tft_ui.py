import time
import framebuf
import machine

from drivers.ili9341 import ILI9341
from drivers.xpt2046 import XPT2046


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
            baudrate=2_000_000,
            calibration={
                "xmin": 303,
                "xmax": 1842,
                "ymin": 278,
                "ymax": 1832,
                "width": 320,
                "height": 240,
                "swap_xy": True,
                "invert_x": True,
                "invert_y": True,
            },
        )
        self._buf = bytearray(self.width * self.height * 2)
        self._fb = framebuf.FrameBuffer(self._buf, self.width, self.height, framebuf.RGB565)
        self._mono_buf = bytearray(self.width)
        self._mono_fb = framebuf.FrameBuffer(self._mono_buf, self.width, 8, framebuf.MONO_VLSB)
        self._last_touch_ms = 0
        self._battery_pct = None
        self._sd_pct = None
        self._sd_ok = None
        self.clear()

    def set_context(self, battery_pct=None, sd_ok=None, sd_pct=None):
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

    def clear(self, color=0x0000):
        self._fb.fill(color)
        self.show()

    def show(self):
        self._display.set_window(0, 0, self.width - 1, self.height - 1)
        self._display._activate_spi()
        self._display.cs.value(0)
        self._display.dc.value(1)
        self._spi.write(self._buf)
        self._display.cs.value(1)

    def _text(self, x, y, text, color=0xFFFF):
        self._fb.text(str(text), int(x), int(y), color)

    def _text_scaled(self, x, y, text, scale=2, color=0xFFFF):
        text = str(text)
        if scale <= 1:
            self._text(x, y, text, color)
            return
        self._mono_fb.fill(0)
        self._mono_fb.text(text, 0, 0, 1)
        width = min(self.width, len(text) * 8)
        for sx in range(width):
            col = self._mono_buf[sx]
            if not col:
                continue
            for sy in range(8):
                if col & (1 << sy):
                    self._fb.fill_rect(x + (sx * scale), y + (sy * scale), scale, scale, color)

    def _centered_scaled(self, y, text, scale=2, color=0xFFFF):
        width = len(str(text)) * 8 * scale
        x = max(0, (self.width - width) // 2)
        self._text_scaled(x, y, text, scale=scale, color=color)

    def _button(self, x, y, w, h, label, fill, fg=0xFFFF):
        self._fb.fill_rect(x, y, w, h, fill)
        self._fb.rect(x, y, w, h, 0xFFFF)
        scale = 2
        tx = x + max(4, (w - (len(label) * 8 * scale)) // 2)
        ty = y + max(4, (h - (8 * scale)) // 2)
        self._text_scaled(tx, ty, label, scale=scale, color=fg)

    def _header(self, title, color=0x001F):
        self._fb.fill_rect(0, 0, self.width, 34, color)
        self._centered_scaled(7, title, scale=2, color=0xFFFF)
        if self._battery_pct is not None:
            self._text(8, 24, "BAT %d%%" % self._battery_pct, 0xFFFF)
        if self._sd_ok is not None:
            sd_label = "SD --"
            if self._sd_ok:
                sd_label = "SD %d%%" % (self._sd_pct if self._sd_pct is not None else 0)
            self._text(self.width - 56, 24, sd_label, 0x07E0 if self._sd_ok else 0xF800)

    def _status_card(self, x, y, label, ok):
        color = 0x07E0 if ok else 0xF800
        self._fb.rect(x, y, 94, 66, color)
        self._text_scaled(x + 10, y + 10, label, scale=2, color=0xFFFF)
        self._text_scaled(x + 20, y + 38, "OK" if ok else "ERR", scale=2, color=color)

    def show_startup_logo(self):
        self._fb.fill(0x0000)
        self._fb.fill_rect(0, 0, self.width, 74, 0xFFFF)
        self._centered_scaled(18, "RACESENSE", scale=3, color=0x0000)
        self._centered_scaled(108, "RS-CORE", scale=3, color=0xFFFF)
        self._fb.fill_rect(54, 164, 212, 4, 0xFFE0)
        self._centered_scaled(184, "BOOTING", scale=2, color=0x07E0)
        self.show()
        return True

    def show_message(self, title, body="", footer=""):
        self._fb.fill(0x0000)
        self._header(title)
        lines = [line for line in str(body).split("\n") if line]
        y = 52
        for line in lines[:6]:
            self._centered_scaled(y, line, scale=2, color=0xFFFF)
            y += 22
        if footer:
            self._centered_scaled(self.height - 24, footer, scale=1, color=0x07E0)
        self.show()
        return True

    def show_boot(self, stage, sd_ok=None, imu_ok=None, gps_ok=None, gps_baud=None, gps_rate_hz=None, storage_info=None, force=False):
        self._fb.fill(0x0000)
        self._header("BOOT")
        self._centered_scaled(46, stage, scale=2, color=0xFFFF)
        if sd_ok is not None:
            self._status_card(10, 92, "SD", sd_ok)
        if imu_ok is not None:
            self._status_card(113, 92, "IMU", imu_ok)
        if gps_ok is not None:
            self._status_card(216, 92, "GPS", gps_ok)
        if gps_baud is not None and gps_rate_hz is not None:
            self._centered_scaled(184, "GPS %s/%sHz" % (gps_baud, gps_rate_hz), scale=2, color=0xFFFF)
        self.show()
        return True

    def show_decision(self, sd_ok, imu_ok, gps_ok, gps_sentences=0, countdown_ms=None):
        self._fb.fill(0x0000)
        self._header("DECISION")
        self._status_card(10, 44, "SD", sd_ok)
        self._status_card(113, 44, "IMU", imu_ok)
        self._status_card(216, 44, "GPS", gps_ok)
        gps_line = "GPS: OK" if gps_ok else "GPS: WAIT %d/5" % gps_sentences
        self._centered_scaled(124, gps_line, scale=2, color=0x07E0 if gps_ok else 0xFFE0)
        if countdown_ms is not None and gps_ok:
            self._centered_scaled(146, "Auto log in %ds" % max(0, countdown_ms // 1000), scale=2, color=0xFFFF)
        else:
            self._centered_scaled(146, "Touch YES for sync", scale=2, color=0xFFFF)
        self._button(20, 164, 120, 52, "YES", 0x07E0, 0x0000)
        self._button(180, 164, 120, 52, "NO", 0xF800, 0xFFFF)
        self.show()
        return True

    def show_first_time_setup(self):
        return self.show_message("SETUP", "No WiFi configured", "Entering sync")

    def show_pairing(self, ssid_hint="RS-Core AP"):
        return self.show_message("PAIRING", "Hotspot active\n" + str(ssid_hint), "Open portal")

    def show_sync_searching(self, ssid):
        return self.show_message("SYNC", "Searching WiFi\n" + str(ssid or ""), "STA connect")

    def show_sync_connected(self, ssid, ip):
        return self.show_message("SYNC", "Connected\n%s\n%s" % (ssid or "", ip or ""), "Cloud handshake")

    def show_heartbeat(self, state, host="", detail=""):
        body = str(state)
        if host:
            body += "\n" + str(host)
        if detail:
            body += "\n" + str(detail)
        return self.show_message("HEARTBEAT", body, "Cloud link")

    def show_track_sync(self, track_name):
        return self.show_message("TRACK", "Active track\n" + str(track_name or "None"), "Track metadata")

    def show_sync_queue(self, files):
        if not files:
            body = "No pending files"
        else:
            names = [str(f).split("/")[-1] for f in files[:4]]
            body = "Pending %d\n%s" % (len(files), "\n".join(names))
        return self.show_message("SYNC QUEUE", body, "Awaiting upload")

    def show_sync_upload(self, filename, file_index, total_files, sent_bytes, total_bytes, global_current=0, global_total=0):
        pct = 0 if total_bytes <= 0 else int((sent_bytes * 100) / total_bytes)
        self._fb.fill(0x0000)
        self._header("SYNCING")
        self._centered_scaled(52, "%d/%d" % (file_index + 1, total_files), scale=3, color=0xFFFF)
        self._centered_scaled(96, str(filename).split("/")[-1], scale=2, color=0xFFFF)
        self._centered_scaled(126, "%d%%" % pct, scale=3, color=0x07E0)
        self._fb.rect(30, 182, 260, 24, 0xFFFF)
        fill_w = int((258 * pct) / 100)
        if fill_w > 0:
            self._fb.fill_rect(31, 183, fill_w, 22, 0x07E0)
        footer = "Uploading"
        if global_total > 0:
            footer = "Global %d%%" % int((global_current * 100) / global_total)
        self._centered_scaled(214, footer, scale=2, color=0xFFFF)
        self.show()
        return True

    def show_sync_result(self, ok, filename="", detail=""):
        title = "SYNC OK" if ok else "SYNC FAIL"
        body = ""
        if filename:
            body += str(filename).split("/")[-1]
        if detail:
            body += ("\n" if body else "") + str(detail)
        return self.show_message(title, body, "Upload complete" if ok else "Retry later")

    def show_sync_idle(self, hb_ok, pending_count=0, low_power=False):
        body = "Cloud: %s\nPending: %d" % ("OK" if hb_ok else "WAIT", pending_count)
        if low_power:
            body += "\nBattery low"
        return self.show_message("SYNC READY", body, "Hold to pair")

    def show_logging_started(self, filename, track_name=None, force=False):
        body = str(filename).split("/")[-1]
        if track_name:
            body += "\n" + str(track_name)
        return self.show_message("LOGGING", body, "Starting")

    def show_logging_live(self, filename, sats=0, gps_ok=False, track_name=None):
        self._fb.fill(0x0000)
        self._header("LOGGING", color=0x07E0 if gps_ok else 0xF800)
        self._centered_scaled(54, str(filename).split("/")[-1], scale=2, color=0xFFFF)
        self._centered_scaled(94, "SATS %d" % max(0, int(sats or 0)), scale=3, color=0xFFE0 if sats < 4 else 0x07E0)
        self._centered_scaled(150, "GPS OK" if gps_ok else "GPS SEARCH", scale=2, color=0x07E0 if gps_ok else 0xF800)
        if track_name:
            self._centered_scaled(194, str(track_name)[:16], scale=2, color=0xFFFF)
        self.show()
        return True

    def show_track_event(self, event, track_name=None, sector=None):
        footer = track_name or ""
        if sector is not None:
            footer = "Sector %s" % sector
        return self.show_message(event, event.replace("_", " "), footer)

    def show_storage_critical(self, used_kb, total_kb, reason="Storage critical"):
        pct = 0 if total_kb <= 0 else int((used_kb * 100) / total_kb)
        return self.show_message("STORAGE", "%s\n%d%% full" % (reason, pct), "%d/%d KB" % (used_kb, total_kb))

    def decision_touch(self):
        point = self._touch.read()
        if not point:
            return None
        now = time.ticks_ms()
        if time.ticks_diff(now, self._last_touch_ms) < 350:
            return None
        self._last_touch_ms = now
        x = point["sx"]
        y = point["sy"]
        print("[TFT] touch:", x, y)
        if 20 <= x <= 150 and 150 <= y <= 239:
            return "yes"
        if 170 <= x <= 319 and 150 <= y <= 239:
            return "no"
        return None
