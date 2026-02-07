from machine import Pin
import neopixel
import time
import math

class LEDManager:
    """
    Manages NeoPixel animations on the ESP32.
    Data Pin: GPIO 4
    
    Priority System:
    1. Storage Critical (>= 90%) - Solid Red
    2. Sector Events (Flash) - Green/Orange/Red
    3. Track Found (3s White Flash)
    4. Normal Logging/Search animations
    """
    def __init__(self, pin=4, count=8):
        self.pin = Pin(pin, Pin.OUT)
        self.np = neopixel.NeoPixel(self.pin, count)
        self.count = count
        self._last_tick = time.ticks_ms()
        
        # Event state
        self._event_active = False
        self._event_end_time = 0
        self._event_type = None

    def clear(self):
        for i in range(self.count):
            self.np[i] = (0, 0, 0)
        self.np.write()

    def set_color(self, r, g, b):
        for i in range(self.count):
            self.np[i] = (r, g, b)
        self.np.write()

    def animation_boot(self, duration_ms=2000):
        """Rainbow cycle boot animation"""
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < duration_ms:
            t = time.ticks_diff(time.ticks_ms(), start) / 1000.0
            for i in range(self.count):
                hue = (i / self.count) + t
                r, g, b = self._wheel(int(hue * 255) & 255)
                self.np[i] = (r, g, b)
            self.np.write()
            time.sleep(0.02)
        self.clear()

    def update(self, state, has_fix=False):
        """Update animation based on system state"""
        now = time.ticks_ms()
        t = now / 1000.0
        
        if state == "STORAGE_FULL":
            # Fast Red Flash
            on = (now % 200 < 100)
            self.set_color(255 if on else 0, 0, 0)

        elif state == "STORAGE_WARN":
            # Yellow Pulse (85%)
            val = int((math.sin(t * 4.0) + 1) / 2 * 180)
            self.set_color(val, val, 0)

        elif state == "SEARCHING":
            # Slow Red Pulse
            intensity = int((math.sin(t * 3.0) + 1) / 2 * 150)
            self.set_color(intensity, 0, 0)
            
        elif state == "LOGGING":
            # Blue Scanner (KITT style)
            self.clear_buffer()
            pos = (math.sin(t * 4.0) + 1) / 2 * (self.count - 1)
            for i in range(self.count):
                dist = abs(pos - i)
                if dist < 2.5: # Wider tail for 16 LEDs
                    bright = int((1.0 - (dist / 2.5)) * 255)
                    self.np[i] = (0, 0, bright)
            self.np.write()
            
        elif state == "PAUSED":
            # Slow Amber Pulse (1s cycle)
            val = int((math.sin(t * 6.28) + 1) / 2 * 150)
            self.set_color(val, int(val * 0.6), 0) # Amber: (R, G*0.6, 0)

        elif state == "CALIBRATING":
            # Fast Blue Sweep
            self.clear_buffer()
            pos = (t * 10.0) % self.count
            for i in range(self.count):
                if abs(i - pos) < 2:
                    self.np[i] = (0, 0, 255)
            self.np.write()
            
        else:
            # IDLE - Very Dim Green Breath
            intensity = int((math.sin(t * 1.0) + 1) / 2 * 10)
            self.set_color(0, intensity, 0)

    def clear_buffer(self):
        for i in range(self.count):
            self.np[i] = (0, 0, 0)

    def _wheel(self, pos):
        """Standard Neopixel Rainbow Wheel"""
        if pos < 85:
            return (pos * 3, 255 - pos * 3, 0)
        elif pos < 170:
            pos -= 85
            return (255 - pos * 3, 0, pos * 3)
        else:
            pos -= 170
            return (0, pos * 3, 255 - pos * 3)

    # --- Event-Based Animations ---
    
    def trigger_event(self, event_type, duration_ms=3000):
        """
        Trigger a priority event animation.
        Events override normal state animations until they expire.
        
        event_type: "TRACK_FOUND", "SECTOR_FAST", "SECTOR_NEUTRAL", "SECTOR_SLOW", "STORAGE_CRITICAL"
        """
        self._event_active = True
        self._event_end_time = time.ticks_ms() + duration_ms
        self._event_type = event_type
        
        # Immediate visual feedback
        if event_type == "TRACK_FOUND":
            self.set_color(255, 255, 255)  # White
        elif event_type == "SECTOR_FAST":
            self.set_color(0, 255, 0)  # Green
        elif event_type == "SECTOR_NEUTRAL":
            self.set_color(255, 165, 0)  # Orange
        elif event_type == "SECTOR_SLOW":
            self.set_color(255, 0, 0)  # Red
        elif event_type == "STORAGE_CRITICAL":
            self.set_color(255, 0, 0)  # Solid Red
    
    def update_with_events(self, base_state):
        """
        Main update loop with event priority handling.
        
        Priority:
        1. Storage Critical (>= 90%) - Solid Red (permanent until resolved)
        2. Active Events (flashing)
        3. Base State (LOGGING, SEARCHING, IDLE)
        """
        now = time.ticks_ms()
        t = now / 1000.0
        
        # Priority 1: Storage Critical (handled externally, passed as base_state)
        if base_state == "STORAGE_CRITICAL":
            self.set_color(255, 0, 0)
            return
        
        # Priority 2: Active Events
        if self._event_active:
            if time.ticks_diff(now, self._event_end_time) < 0:
                # Event still active - do flash animation
                self._animate_event(now)
                return
            else:
                # Event expired
                self._event_active = False
                self._event_type = None
        
        # Priority 3: Base State Animations
        self.update(base_state)
    
    def is_event_active(self):
        """Check if an event animation is currently playing."""
        if not self._event_active:
            return False
        if time.ticks_diff(time.ticks_ms(), self._event_end_time) >= 0:
            self._event_active = False
            return False
        return True

    def show_paused(self):
        """Short-cut for main loop state"""
        self.update_with_events("PAUSED")

    def show_calibrating(self):
        """Fast blue sweep for calibration"""
        self.update_with_events("CALIBRATING")

    def show_calibrated(self):
        """3x quick green flash"""
        self.trigger_event("CALIBRATED", duration_ms=1000)

    def _animate_event(self, now):
        """Animate the current event (flashing pattern)."""
        if self._event_type == "TRACK_FOUND":
            # Fast white flash for 3 seconds
            on = (now % 150 < 75)
            self.set_color(255 if on else 0, 255 if on else 0, 255 if on else 0)
            
        elif self._event_type == "CALIBRATED":
            # 3 quick green flashes
            cycle = (now % 333) < 166
            self.set_color(0, 255 if cycle else 0, 0)

        elif self._event_type in ("SECTOR_FAST", "SECTOR_NEUTRAL", "SECTOR_SLOW"):
            # 3 distinct flashes over ~600ms
            cycle = (now % 600) // 200  # 0, 1, 2
            phase = (now % 200)  # 0-199
            on = phase < 100
            
            if self._event_type == "SECTOR_FAST":
                self.set_color(0, 255 if on else 0, 0)  # Green
            elif self._event_type == "SECTOR_NEUTRAL":
                self.set_color(255 if on else 0, 165 if on else 0, 0)  # Orange
            else:
                self.set_color(255 if on else 0, 0, 0)  # Red
                
        elif self._event_type == "STORAGE_CRITICAL":
            self.set_color(255, 0, 0)  # Solid red
    
    def is_event_active(self):
        """Check if an event animation is currently playing."""
        if not self._event_active:
            return False
        if time.ticks_diff(time.ticks_ms(), self._event_end_time) >= 0:
            self._event_active = False
            return False
        return True
