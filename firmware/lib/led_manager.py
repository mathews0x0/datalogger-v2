import _thread
from machine import Pin
import neopixel
import time
import math

class LEDManager:
    """
    Manages dual NeoPixel output on the ESP32-S3.
    
    Feedback LED: GPIO 4 (16-LED matrix)
    Onboard LED:  GPIO 6 (1 LED)
    
    Architecture:
    - Runs on Core 1 via start_animation_thread().
    - Single Writer: Only the background loop calls hardware .write().
    - Brightness Aware: Global self.brightness (0.0-1.0) applied to all outputs.
    """
    def __init__(self, pin=4, count=16, onboard_neo_pin=6, onboard_led_pin=2):
        self.pin = Pin(pin, Pin.OUT)
        self.np = neopixel.NeoPixel(self.pin, count)
        self.count = count
        
        self.onboard_neo_pin = Pin(onboard_neo_pin, Pin.OUT)
        self.onboard_np = neopixel.NeoPixel(self.onboard_neo_pin, 1)
        
        self.onboard_led = Pin(onboard_led_pin, Pin.OUT)
        
        # UI State
        self.brightness = 0.5  # Default 50% brightness
        self._state = "IDLE"
        self._track_mode = False # Stealth mode when on track
        self._event_active = False
        self._event_type = None
        self._event_end_time = 0
        
        self._lock = _thread.allocate_lock()
        self._thread_running = False

    def set_brightness(self, level):
        """Set global brightness (0.0 to 1.0)."""
        self.brightness = max(0.0, min(1.0, level))

    def set_track_mode(self, active=True):
        """Enable stealth mode (LEDs off during logging)."""
        self._track_mode = active

    def start_animation_thread(self):
        """Spawns worker thread for fluid UI feedback."""
        if self._thread_running: return
        self._thread_running = True
        _thread.stack_size(8192)
        _thread.start_new_thread(self._animation_loop, ())

    # --- Semantic Animation Methods (Non-blocking calling from Core 0) ---

    def play_booting(self): self._state = "BOOT"; self._track_mode = False
    def play_searching(self): self._state = "SEARCHING"
    def play_logging(self): self._state = "LOGGING"
    def play_paused(self): self._state = "PAUSED"
    def play_calibrating(self): self._state = "CALIBRATING"
    def play_idle(self): self._state = "IDLE"
    def play_storage_critical(self): self._state = "STORAGE_CRITICAL"
    def play_auto_copy(self): self._state = "AUTO_COPY"; self._track_mode = False
    
    def play_decision(self, sd_ok, imu_ok, gps_ok):
        if not gps_ok:
            self._state = "DECISION_GPS_FAIL"
        elif not sd_ok or not imu_ok:
            self._state = "DECISION_IMU_SD_FAILED"
        else:
            self._state = "DECISION_ALL_OK"

    def play_sync_searching(self): self._state = "SYNC_SEARCHING"; self._track_mode = False
    def play_sync_found(self): self._state = "SYNC_FOUND"
    def play_sync_uploading(self): self._state = "SYNC_UPLOADING"
    def play_sync_ok(self): self._state = "SYNC_OK"
    def play_sync_fail(self): self._state = "SYNC_FAIL"
    def play_pairing(self): self._state = "PAIRING"
    def play_setup_needed(self): self._state = "SETUP_NEEDED"
    
    def play_heartbeat_success(self): self._state = "HB_SUCCESS"
    def play_heartbeat_error(self): self._state = "HB_ERROR"
    def play_heartbeat_send(self): self._state = "HB_SEND"
    def play_heartbeat_ack(self): self._state = "HB_ACK"

    def play_wifi_connecting(self): self._state = "WIFI_CONNECTING"
    def play_wifi_connected(self): self._state = "WIFI_CONNECTED"

    def trigger_event(self, event_type, duration_ms=None):
        """Overlay a priority event (e.g. lap crossing) over the base state."""
        if duration_ms is None:
            # Default durations: 2.5s for racing sectors, 1s for others
            if event_type.startswith("SECTOR_") or event_type == "TRACK_FOUND":
                duration_ms = 2500
            else:
                duration_ms = 1000

        self._event_type = event_type
        self._event_end_time = time.ticks_ms() + duration_ms
        self._event_active = True

    # --- Worker Logic (Core 1) ---

    def _animation_loop(self):
        while self._thread_running:
            try:
                now = time.ticks_ms()
                
                # Check if high-priority event is active
                if self._event_active:
                    if time.ticks_diff(now, self._event_end_time) < 0:
                        self._render_event(now)
                    else:
                        self._event_active = False
                else:
                    self._render_state(now)
                
                self._write_all()
            except:
                pass
            time.sleep_ms(20) # 50Hz update rate

    def _render_state(self, now):
        """Render the base state animation into the pixel buffer."""
        t = now / 1000.0
        s = self._state
        
        if s == "LOGGING":
            if self._track_mode:
                self._fill(0, 0, 0) # Stealth mode: No distraction while racing
            else:
                self._fill(0, 255, 0) # Solid green for casual logging
        elif s == "SEARCHING":
            val = int((math.sin(t * 3.0) + 1) / 2 * 255)
            self._fill(val, val, 0)
        elif s == "PAUSED":
            val = int((math.sin(t * 6.0) + 1) / 2 * 255)
            self._fill(val, int(val * 0.6), 0)
        elif s == "CALIBRATING":
            val = int((math.sin(t * 10.0) + 1) / 2 * 255)
            self._fill(0, 0, val)
        elif s == "STORAGE_CRITICAL" or s == "HB_ERROR":
            val = int((math.sin(t * 15.0) + 1) / 2 * 255)
            self._fill(val, 0, 0)
        elif s == "SYNC_UPLOADING":
            on = (now % 200 < 100)
            self._fill(0, 255 if on else 10, 0)
        elif s == "SYNC_SEARCHING" or s == "SYNC_FOUND":
            # Purple fade/blink
            on = (now % 300 < 150) if s == "SYNC_FOUND" else True
            val = int((math.sin(t * 4.0) + 1) / 2 * 200) if s == "SYNC_SEARCHING" else 200
            self._fill(val if on else 0, 0, val if on else 0)
        elif s.startswith("HB_") or s.startswith("SYNC_HEARTBEAT_"):
            # "Lub-Dub" Heartbeat (2s cycle)
            ms = now % 2000
            val = 0
            if ms < 200: # Lub
                val = int(math.sin((ms / 200.0) * math.pi) * 255)
            elif 350 < ms < 550: # Dub
                val = int(math.sin(((ms - 350) / 200.0) * math.pi) * 120)
            
            # Color Mapping
            is_green = s in ("HB_SUCCESS", "HB_ACK", "SYNC_HEARTBEAT_GREEN")
            if is_green: self._fill(0, val, 0)
            else: self._fill(val, 0, 0) # HB_SEND, HB_ERROR, SYNC_HEARTBEAT_RED
        elif s == "AUTO_COPY":
            on = (now % 200 < 100)
            val = 255 if on else 0
            self._fill(val, val, val)
        elif s == "BOOT":
            on = (now % 400 < 200)
            self._fill(0, 0, 255 if on else 0)
        elif s.startswith("DECISION_"):
            if s == "DECISION_GPS_FAIL":
                # Solid red
                self._fill(200, 0, 0)
            else:
                # Fast blink (Green for ALL_OK, Red for SD/IMU fail)
                on = (now % 150 < 75)
                if s == "DECISION_ALL_OK": self._fill(0, 200 if on else 0, 0)
                else: self._fill(200 if on else 0, 0, 0) # DECISION_IMU_SD_FAILED
        elif s == "PAIRING":
            val = int((math.sin(t * 2.0) + 1) / 2 * 200)
            self._fill(0, 0, val)
        elif s == "WIFI_CONNECTING":
            val = int((math.sin(t * 8.0) + 1) / 2 * 255)
            self._fill(val, val, 0) # Rapid yellow pulse
        elif s == "WIFI_CONNECTED":
            self._fill(0, 255, 0) # Solid green for a moment (usually transitions quickly)
        elif s == "SETUP_NEEDED":
            # Rainbow cycle
            hue = int(t * 100) % 255
            r, g, b = self._hsv_to_rgb(hue)
            self._fill(r, g, b)
        else:
            # IDLE - very dim green breath
            val = int((math.sin(t * 1.5) + 1) / 2 * 5)
            self._fill(0, val, 0)

    def _render_event(self, now):
        """Render priority event animations."""
        et = self._event_type
        if et == "TRACK_FOUND":
            on = (now % 166 < 83)
            c = 255 if on else 0
            self._fill(c, c, c)
        elif et in ("SECTOR_FAST", "SECTOR_NEUTRAL", "SECTOR_SLOW"):
            on = (now % 200 < 100)
            if not on: 
                self._fill(0, 0, 0)
            elif et == "SECTOR_FAST": self._fill(0, 255, 0)
            elif et == "SECTOR_NEUTRAL": self._fill(255, 165, 0)
            else: self._fill(255, 0, 0)
        elif et == "CALIBRATED":
            on = (now % 333 < 166)
            self._fill(0, 255 if on else 0, 0)

    def _fill(self, r, g, b):
        """Fill the internal buffer with a color."""
        for i in range(self.count):
            self.np[i] = (r, g, b)

    def _write_all(self):
        """Apply brightness and write to both NeoPixel strips."""
        with self._lock:
            # Scale colors by brightness
            # Note: NeoPixel stores values in (G, R, B) or (R, G, B) depending on config.
            # MicroPython's neopixel lib uses (R, G, B) tuples.
            # We apply brightness here just before writing.
            for i in range(self.count):
                r, g, b = self.np[i]
                self.np[i] = (int(r * self.brightness), int(g * self.brightness), int(b * self.brightness))
            
            self.np.write()
            self.onboard_np[0] = self.np[0]
            self.onboard_np.write()

    def _hsv_to_rgb(self, h):
        if h < 85: return (h * 3, 255 - h * 3, 0)
        elif h < 170: h -= 85; return (255 - h * 3, 0, h * 3)
        else: h -= 170; return (0, h * 3, 255 - h * 3)

    # --- Legacy / Utility ---
    def clear(self):
        self._state = "OFF"
        self._fill(0, 0, 0)
        self._write_all()

    def set_state(self, state):
        """For backward compat: maps old state strings to new methods."""
        self._state = state

    def update_onboard_led(self, state):
        """Backward compatibility for legacy WiFi/Portal flow."""
        mapping = {
            "CONNECTING": self.play_wifi_connecting,
            "CONNECTED": self.play_wifi_connected,
            "PAIRING": self.play_pairing,
        }
        if state in mapping:
            mapping[state]()
        else:
            print(f"[LED] Warning: Unknown legacy state '{state}'")
