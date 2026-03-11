import _thread
from machine import Pin
import neopixel
import time
import math

class LEDManager:
    """
    Manages dual NeoPixel output on the ESP32-S3.
    
    Feedback LED: GPIO 4 (16-LED matrix) — main visual feedback.
    Onboard LED:  GPIO 6 (1 LED)          — mirrors feedback[0] color.
    
    All animations are simple: solid colors, pulses, and fades.
    No chasers, scanners, or sequential patterns.
    Speed and color communicate state.
    """
    def __init__(self, pin=4, count=16, onboard_neo_pin=6, onboard_led_pin=2):
        # Feedback NeoPixel strip (16 LEDs on IO4)
        self.pin = Pin(pin, Pin.OUT)
        self.np = neopixel.NeoPixel(self.pin, count)
        self.count = count
        
        # Onboard NeoPixel (1 LED on IO6) — mirrors feedback
        self.onboard_neo_pin = Pin(onboard_neo_pin, Pin.OUT)
        self.onboard_np = neopixel.NeoPixel(self.onboard_neo_pin, 1)
        
        # Onboard debug LED (GPIO 2)
        self.onboard_led = Pin(onboard_led_pin, Pin.OUT)
        
        # Event state
        self._event_active = False
        self._event_end_time = 0
        self._event_type = None

        # Lock for thread-safe NeoPixel writes
        self._lock = _thread.allocate_lock()

    def _write_all(self):
        """Write to both NeoPixel strips with thread lock."""
        with self._lock:
            self.np.write()
            self.onboard_np[0] = self.np[0]
            self.onboard_np.write()

    def clear(self):
        for i in range(self.count):
            self.np[i] = (0, 0, 0)
        self._write_all()

    def set_color(self, r, g, b):
        """Set all pixels to a solid color."""
        for i in range(self.count):
            self.np[i] = (r, g, b)
        self._write_all()

    # --- Boot & Decision Window Animations (blocking) ---

    def animation_boot(self):
        """3 blue pulses indicating device is alive."""
        for _ in range(3):
            self.set_color(0, 0, 180)
            time.sleep_ms(150)
            self.clear()
            time.sleep_ms(150)

    def animation_decision_tick(self, sd_ok):
        """
        Fast blink during the 10s decision window.
        Green if SD card detected, Red if not.
        Called repeatedly from the decision loop.
        """
        now = time.ticks_ms()
        on = (now % 150 < 75)  # Fast blink (~6.6Hz)
        if sd_ok:
            self.set_color(0, 255 if on else 0, 0)   # Green
        else:
            self.set_color(255 if on else 0, 0, 0)    # Red

    # --- Sync Mode Animations (non-blocking, called from loop) ---

    def update_sync(self, sync_state):
        """
        Update LEDs for sync mode states:
        - SYNC_SEARCHING:  slow purple fade (looking for WiFi)
        - SYNC_FOUND:      fast purple blink (network found)
        - SYNC_UPLOADING:  fast green blink (files transferring)
        - SYNC_OK:         slow green fade (upload complete)
        - SYNC_FAIL:       slow red fade (upload failed)
        - PAIRING:         blue breathing fade (captive portal)
        """
        now = time.ticks_ms()
        t = now / 1000.0

        if sync_state == "SYNC_SEARCHING":
            # Slow purple fade
            val = int((math.sin(t * 2.0) + 1) / 2 * 180)
            self.set_color(val, 0, val)

        elif sync_state == "SYNC_FOUND":
            # Fast purple blink
            on = (now % 200 < 100)
            self.set_color(180 if on else 0, 0, 180 if on else 0)

        elif sync_state == "SYNC_UPLOADING":
            # Fast green blink
            on = (now % 200 < 100)
            self.set_color(0, 255 if on else 0, 0)

        elif sync_state == "SYNC_OK":
            # Slow green fade
            val = int((math.sin(t * 1.5) + 1) / 2 * 180)
            self.set_color(0, val, 0)

        elif sync_state == "SYNC_FAIL":
            # Slow red fade
            val = int((math.sin(t * 1.5) + 1) / 2 * 180)
            self.set_color(val, 0, 0)

        elif sync_state == "PAIRING":
            # Blue breathing fade
            val = int((math.sin(t * 2.0) + 1) / 2 * 200)
            self.set_color(0, 0, val)

        elif sync_state == "SETUP_NEEDED":
            # Rainbow cycle — tells user to complete first-time setup
            hue = int(t * 80) % 255
            r, g, b = self._hsv_to_rgb(hue)
            self.set_color(r, g, b)

    # --- Logging Mode Animations (non-blocking) ---

    def update(self, state):
        """
        Update animation for logging mode states.
        All animations are simple pulses or solid colors.
        """
        now = time.ticks_ms()
        t = now / 1000.0

        if state == "STORAGE_FULL":
            # Fast red flash
            on = (now % 200 < 100)
            self.set_color(255 if on else 0, 0, 0)

        elif state == "STORAGE_WARN":
            # Yellow pulse
            val = int((math.sin(t * 4.0) + 1) / 2 * 180)
            self.set_color(val, val, 0)

        elif state == "SEARCHING":
            # Slow yellow pulse (searching for GPS)
            val = int((math.sin(t * 3.0) + 1) / 2 * 150)
            self.set_color(val, val, 0)

        elif state == "LOGGING":
            # Solid green
            self.set_color(0, 150, 0)

        elif state == "PAUSED":
            # Slow amber pulse
            val = int((math.sin(t * 6.28) + 1) / 2 * 150)
            self.set_color(val, int(val * 0.6), 0)

        elif state == "CALIBRATING":
            # Fast blue pulse
            val = int((math.sin(t * 8.0) + 1) / 2 * 255)
            self.set_color(0, 0, val)

        else:
            # IDLE — very dim green breath
            val = int((math.sin(t * 1.0) + 1) / 2 * 10)
            self.set_color(0, val, 0)

    # --- Event-Based Animations ---

    def trigger_event(self, event_type, duration_ms=3000):
        """
        Trigger a priority event animation that overrides normal state.
        event_type: TRACK_FOUND, SECTOR_FAST, SECTOR_NEUTRAL, SECTOR_SLOW,
                    STORAGE_CRITICAL, CALIBRATED
        """
        self._event_active = True
        self._event_end_time = time.ticks_ms() + duration_ms
        self._event_type = event_type

        # Immediate flash
        if event_type == "TRACK_FOUND":
            self.set_color(255, 255, 255)
        elif event_type == "SECTOR_FAST":
            self.set_color(0, 255, 0)
        elif event_type == "SECTOR_NEUTRAL":
            self.set_color(255, 165, 0)
        elif event_type == "SECTOR_SLOW":
            self.set_color(255, 0, 0)
        elif event_type == "STORAGE_CRITICAL":
            self.set_color(255, 0, 0)

    def update_with_events(self, base_state):
        """
        Main update loop with event priority handling.
        Priority: Storage Critical > Active Events > Base State
        """
        now = time.ticks_ms()

        if base_state == "STORAGE_CRITICAL":
            self.set_color(255, 0, 0)
            return

        if self._event_active:
            if time.ticks_diff(now, self._event_end_time) < 0:
                self._animate_event(now)
                return
            else:
                self._event_active = False
                self._event_type = None

        self.update(base_state)

    def is_event_active(self):
        if not self._event_active:
            return False
        if time.ticks_diff(time.ticks_ms(), self._event_end_time) >= 0:
            self._event_active = False
            return False
        return True

    def show_calibrated(self):
        self.trigger_event("CALIBRATED", duration_ms=1000)

    def _animate_event(self, now):
        """Animate the current event (simple flashing)."""
        if self._event_type == "TRACK_FOUND":
            on = (now % 150 < 75)
            c = 255 if on else 0
            self.set_color(c, c, c)

        elif self._event_type == "CALIBRATED":
            on = (now % 333 < 166)
            self.set_color(0, 255 if on else 0, 0)

        elif self._event_type in ("SECTOR_FAST", "SECTOR_NEUTRAL", "SECTOR_SLOW"):
            on = (now % 200 < 100)
            if self._event_type == "SECTOR_FAST":
                self.set_color(0, 255 if on else 0, 0)
            elif self._event_type == "SECTOR_NEUTRAL":
                self.set_color(255 if on else 0, 165 if on else 0, 0)
            else:
                self.set_color(255 if on else 0, 0, 0)

        elif self._event_type == "STORAGE_CRITICAL":
            self.set_color(255, 0, 0)

    # --- GPIO 2 Debug LED ---

    def update_onboard_led(self, state):
        """GPIO 2 blink patterns (kept for debug/backward compat)."""
        now = time.ticks_ms()
        if state == "CONNECTED":
            self.onboard_led.value(1)
        elif state == "CONNECTING":
            self.onboard_led.value(1 if (now % 500 < 250) else 0)
        elif state == "PAIRING":
            cycle = now % 3000
            if cycle < 2000:
                self.onboard_led.value(1 if (cycle % 333 < 166) else 0)
            else:
                self.onboard_led.value(0)
        else:
            self.onboard_led.value(0)

    def _hsv_to_rgb(self, h):
        """Convert hue (0-255) to RGB tuple. Simple rainbow helper."""
        if h < 85:
            return (h * 3, 255 - h * 3, 0)
        elif h < 170:
            h -= 85
            return (255 - h * 3, 0, h * 3)
        else:
            h -= 170
            return (0, h * 3, 255 - h * 3)
