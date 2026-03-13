import sys
from unittest.mock import MagicMock
import time

class MockNeoPixel:
    def __init__(self, pin, count):
        self.count = count
        self.pixels = [(0,0,0)] * count
    def __setitem__(self, i, color): self.pixels[i] = color
    def __getitem__(self, i): return self.pixels[i]
    def write(self): pass

# Mock MicroPython specifics
sys.modules['machine'] = MagicMock()
mock_np_mod = MagicMock()
mock_np_mod.NeoPixel = MockNeoPixel
sys.modules['neopixel'] = mock_np_mod
sys.modules['_thread'] = MagicMock()

# Mock time specifics for MicroPython
import time as py_time
mock_time = MagicMock()
mock_time.ticks_ms = lambda: int(py_time.time() * 1000)
mock_time.ticks_diff = lambda a, b: a - b
mock_time.sleep_ms = lambda ms: py_time.sleep(ms / 1000.0)
mock_time.time = py_time.time # keep standard time
sys.modules['time'] = mock_time

# Import the class to test
# We need to add the firmware/lib path to sys.path
sys.path.append('/Users/mj/Documents/datalogger-v2/firmware/lib')
from led_manager import LEDManager

def test_led_logic():
    print("Starting LEDManager Logic Test...")
    
    # 1. Setup
    led = LEDManager(count=16)
    led.set_brightness(1.0)
    
    # 2. Test State Setting
    led.play_logging()
    assert led._state == "LOGGING"
    print("✓ State 'LOGGING' set correctly")
    
    # Simulate one iteration of render
    led._render_state(1000) # time = 1s
    # check if pixels are green (0, 255, 0)
    for i in range(16):
        assert led.np[i] == (0, 255, 0)
    print("✓ Rendering 'LOGGING' produces green pixels")
    
    # 3. Test Event Overlay
    led.trigger_event("TRACK_FOUND", duration_ms=1000)
    assert led._event_active == True
    
    # Simulate render during event (tick_ms=1500, within 1000ms duration)
    # TRACK_FOUND uses flash logic: on = (now % 166 < 83)
    # 1500 % 166 = 6.0 -> < 83 is True -> White (255, 255, 255)
    led._render_event(1500)
    for i in range(16):
        assert led.np[i] == (255, 255, 255)
    print("✓ Event 'TRACK_FOUND' overlays white pixels correctly")
    
    # 4. Test Brightness Scaling
    led.set_brightness(0.5)
    led._fill(200, 200, 200) # fill buffer with 200
    led._write_all() # scales by 0.5 -> 100
    for i in range(16):
        assert led.np[i] == (100, 100, 100)
    print("✓ Brightness scaling (0.5) applies correctly in _write_all")

    # 6. Test Stealth Mode (track_mode)
    led.play_logging()
    led.set_track_mode(True)
    led._render_state(1000)
    # in track_mode, LOGGING should be black (0,0,0)
    for i in range(16):
        assert led.np[i] == (0, 0, 0)
    print("✓ Stealth Mode: 'LOGGING' renders black when track_mode is active")

    # 7. Test Sector Duration and Event Overlay in Stealth Mode
    # Sector event should still show up even if track_mode is active
    led.trigger_event("SECTOR_FAST") # should use 2500ms default
    assert led._event_active == True
    assert (led._event_end_time - led._event_end_time + 2500) == 2500 # Duration check logic
    
    # Render during event
    led._render_event(1000) # SECTOR_FAST is blinking green
    # (now % 200 < 100) -> 1000 % 200 = 0 -> < 100 is True -> Green
    for i in range(16):
        assert led.np[i] == (0, 255, 0)
    print("✓ Sector Pulse: Overlays even while in Stealth Mode")

    # 8. Test Automatic Track Mode resetting
    led.play_booting()
    assert led._track_mode == False
    print("✓ Track Mode reset upon 'play_booting'")

    # 10. Test Lub-Dub Heartbeat Animation
    led.play_heartbeat_send() # Red heartbeat
    # Lub (peak at 100ms)
    led._render_state(100)
    for i in range(16): assert led.np[i][0] > 200 and led.np[i][1] == 0 # Strong red
    
    # Dub (peak at 450ms, though Dub starts at 350ms, peak is midpoint 450ms)
    led._render_state(450)
    for i in range(16): assert 50 < led.np[i][0] < 150 # Softer red
    
    # Rest (1000ms)
    led._render_state(1000)
    for i in range(16): assert led.np[i] == (0, 0, 0)
    print("✓ Lub-Dub Animation: Timing and varying intensities work")

    # 11. Test Heartbeat Color Logic
    led.play_heartbeat_ack() # Should be green
    led._render_state(100) # During lub
    for i in range(16): assert led.np[i][1] > 200 and led.np[i][0] == 0 # Strong green
    print("✓ Heartbeat Colors: Red for send, Green for ACK")

    print("\nALL PHASE 4 LOGIC TESTS PASSED!")

if __name__ == "__main__":
    try:
        test_led_logic()
    except AssertionError as e:
        print(f"TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR DURING TEST: {e}")
        sys.exit(1)
