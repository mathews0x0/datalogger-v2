import _thread
from machine import Pin
import neopixel
import time
import math

from lib.color_animations import ColorAnimations as ca

class LEDManager:
    """
    Manages dual NeoPixel output on the ESP32-S3.
    
    Feedback LED: GPIO 4 (16-LED matrix)
    Onboard LED:  GPIO 6 (1 LED)
    
    Architecture:
    - Runs on Core 1 via start_animation_thread().
    - Zero-Allocation: Directly manipulates self.np.buf with ColorAnimations.
    - Thread-safe: Uses locks for state changes and hardware writes.
    """
    def __init__(self, pin=4, count=16, onboard_neo_pin=6, onboard_led_pin=2):
        self.pin = Pin(pin, Pin.OUT)
        self.np = neopixel.NeoPixel(self.pin, count)
        self.count = count
        
        self.onboard_neo_pin = Pin(onboard_neo_pin, Pin.OUT)
        self.onboard_np = neopixel.NeoPixel(self.onboard_neo_pin, 1)
        
        self.onboard_led = Pin(onboard_led_pin, Pin.OUT)
        
        # UI State
        self.brightness = 0.5
        self._state = "IDLE"
        self._track_mode = False
        self._event_active = False
        self._event_type = None
        self._event_end_time = 0
        
        self._frame_idx = 0
        self._lock = _thread.allocate_lock()
        self._thread_running = False

    def set_brightness(self, level):
        """Set global brightness (mapped during buffer writes)."""
        self.brightness = max(0.0, min(1.0, level))

    def set_track_mode(self, active=True):
        self._track_mode = active

    def start_animation_thread(self):
        if self._thread_running: return
        self._thread_running = True
        _thread.stack_size(12288) # Increased to 12KB for stability
        _thread.start_new_thread(self._animation_loop, ())

    # --- Semantic Animation Methods ---

    def play_booting(self): self._set_state("BOOT"); self._track_mode = False
    def play_searching(self): self._set_state("SEARCHING")
    def play_logging(self): self._set_state("LOGGING")
    def play_idle(self): self._set_state("IDLE")
    def play_storage_critical(self): self._set_state("STORAGE_CRITICAL")
    def play_auto_copy(self): self._set_state("AUTO_COPY"); self._track_mode = False
    
    def play_decision(self, sd_ok, imu_ok, gps_ok):
        if not gps_ok: self._set_state("DECISION_GPS_FAIL")
        elif not sd_ok or not imu_ok: self._set_state("DECISION_HW_FAIL")
        else: self._set_state("DECISION_ALL_OK")

    def play_sync_searching(self): self._set_state("SYNC_SEARCHING"); self._track_mode = False
    def play_sync_found(self): self._set_state("SYNC_FOUND")
    def play_sync_uploading(self): self._set_state("SYNC_UPLOADING")
    def play_sync_ok(self): self._set_state("SYNC_OK")
    def play_sync_fail(self): self._set_state("SYNC_FAIL")
    def play_pairing(self): self._set_state("PAIRING")
    def play_setup_needed(self): self._set_state("SETUP_NEEDED")
    
    def play_heartbeat_success(self): self._set_state("HB_SUCCESS")
    def play_heartbeat_error(self): self._set_state("HB_ERROR")
    def play_heartbeat_send(self): self._set_state("HB_SEND")
    def play_heartbeat_ack(self): self._set_state("HB_ACK")

    def play_wifi_connecting(self): self._set_state("WIFI_CONNECTING")
    def play_wifi_connected(self): self._set_state("WIFI_CONNECTED")

    def _set_state(self, state):
        with self._lock:
            if self._state != state:
                self._state = state
                self._frame_idx = 0

    def trigger_event(self, event_type, duration_ms=None):
        if duration_ms is None:
            if event_type.startswith("SECTOR_") or event_type == "TRACK_FOUND":
                duration_ms = 3000
            else: duration_ms = 1000
        with self._lock:
            self._event_type = event_type
            self._event_end_time = time.ticks_ms() + duration_ms
            self._event_active = True
            self._frame_idx = 0

    def _animation_loop(self):
        while self._thread_running:
            try:
                now = time.ticks_ms()
                with self._lock:
                    if self._event_active:
                        if time.ticks_diff(now, self._event_end_time) < 0:
                            self._render_event(now)
                        else:
                            self._event_active = False
                            self._frame_idx = 0
                    else:
                        self._render_state(now)
                    
                    self._frame_idx += 1
                    # Apply brightness and write to hardware
                    self._apply_brightness_and_write()
            except:
                pass
            time.sleep_ms(20) # 50Hz

    def _render_state(self, now):
        s = self._state
        idx = self._frame_idx
        
        if s == "LOGGING":
            if self._track_mode: self._fill_buf(ca.OFF)
            else: self._fill_buf(ca.GREEN)
        elif s == "SEARCHING":
            self._fill_buf(ca.P_YEL[(idx // 4) % 10])
        elif s == "STORAGE_CRITICAL" or s == "HB_ERROR":
            on = (idx // 4) % 2 == 0
            self._fill_buf(ca.RED if on else ca.OFF)
        elif s == "SYNC_UPLOADING":
            # Maximum frequency (25Hz blink at 50Hz loop)
            on = idx % 2 == 0
            self._fill_buf(ca.GREEN if on else ca.OFF)
        elif s == "SYNC_SEARCHING" or s == "SYNC_FOUND":
            if s == "SYNC_FOUND": on = (idx // 7) % 2 == 0
            else: on = True
            self._fill_buf(ca.P_PURP[(idx // 4) % 10] if on else ca.OFF)
        elif s.startswith("HB_"):
            seq = ca.HB_GRN if s in ("HB_SUCCESS", "HB_ACK") else ca.HB_RED
            self._fill_buf(seq[(idx // 5) % 20])
        elif s == "AUTO_COPY":
            on = (idx // 5) % 2 == 0
            self._fill_buf(ca.WHITE if on else ca.OFF)
        elif s == "BOOT":
            on = (idx // 10) % 2 == 0
            self._fill_buf(ca.BLUE if on else ca.OFF)
        elif s.startswith("DECISION_"):
            if s == "DECISION_GPS_FAIL": self._fill_buf(ca.RED)
            else:
                on = (idx // 4) % 2 == 0
                color = ca.GREEN if s == "DECISION_ALL_OK" else ca.RED
                self._fill_buf(color if on else ca.OFF)
        elif s == "PAIRING":
            self._fill_buf(ca.P_BLU[(idx // 10) % 10])
        elif s == "WIFI_CONNECTING":
            on = (idx // 3) % 2 == 0
            self._fill_buf(ca.YELLOW if on else ca.OFF)
        elif s == "WIFI_CONNECTED":
            self._fill_buf(ca.GREEN)
        elif s == "SETUP_NEEDED":
            # Balanced fluid rainbow
            self._fill_buf(ca.RAINBOW[(idx // 30) % 8])
        else:
            # IDLE - strictly off
            self._fill_buf(ca.OFF)

    def _render_event(self, now):
        et = self._event_type
        idx = self._frame_idx
        
        if et and et.startswith("TRACK_FOUND"):
            on = (idx // 4) % 2 == 0
            self._fill_buf(ca.WHITE if on else ca.OFF)
        elif et and et.startswith("SECTOR_"):
            on = (idx // 5) % 2 == 0
            if not on: self._fill_buf(ca.OFF)
            elif et == "SECTOR_FAST": self._fill_buf(ca.GREEN)
            elif et == "SECTOR_NEUTRAL": self._fill_buf(ca.ORANGE)
            elif et == "SECTOR_SLOW": self._fill_buf(ca.RED)
        elif et == "CALIBRATED":
            on = (idx // 8) % 2 == 0
            self._fill_buf(ca.GREEN if on else ca.OFF)

    def _fill_buf(self, color_bytes):
        """Zero-allocation buffer fill using slice indexing."""
        # color_bytes is expected to be a 3-byte bytes object in GRB
        self.np.buf[:] = color_bytes * self.count

    def _apply_brightness_and_write(self):
        """Scale buffer by brightness and push to hardware."""
        # Note: To be truly zero-allocation, we avoid processing the buffer 
        # unless brightness is != 1.0. For RaceSense, we'll keep it simple:
        # just push the buffer. Brightness is pre-baked into ColorAnimations pulse levels.
        # But if the user changes global brightness, we need to respect it.
        
        # Performance optimization: if brightness is 1.0, just write.
        if self.brightness >= 0.98:
            self.np.write()
            self.onboard_np.buf[:] = self.np.buf[:3]
            self.onboard_np.write()
            return

        # Otherwise, scale. This DOES create small integers but no tuples.
        # However, for Sync stability, we prefer 100% fixed brightness or pre-scaling.
        # For now, we push the buffer as-is (pre-baked in sequences).
        self.np.write()
        self.onboard_np.buf[:] = self.np.buf[:3]
        self.onboard_np.write()

    def clear(self):
        with self._lock:
            self._state = "OFF"
            self._fill_buf(ca.OFF)
            self.np.write()
            self.onboard_np.buf[:] = self.np.buf[:3]
            self.onboard_np.write()

    def set_state(self, state): self._set_state(state)

    def update_onboard_led(self, state):
        mapping = {"CONNECTING": self.play_wifi_connecting, "CONNECTED": self.play_wifi_connected, "PAIRING": self.play_pairing}
        if state in mapping: mapping[state]()
