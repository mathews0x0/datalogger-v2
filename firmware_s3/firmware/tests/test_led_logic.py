import sys
from unittest.mock import MagicMock

class MockNeoPixel:
    def __init__(self, pin, count):
        self.count = count
        self.buf = bytearray(count * 3)
    def __setitem__(self, i, color):
        base = i * 3
        self.buf[base:base + 3] = bytes(color)
    def __getitem__(self, i):
        base = i * 3
        return tuple(self.buf[base:base + 3])
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
sys.path.append('/Users/mj/Documents/datalogger-v2/firmware')
from lib.led_manager import LEDManager

def test_led_logic():
    print("Starting LEDManager Logic Test...")
    
    led = LEDManager(count=16)
    led.set_brightness(1.0)
    
    led.play_logging()
    assert led._state == "LOGGING"
    print("✓ State 'LOGGING' set correctly")
    
    led._render_state(1000)
    assert led.np.buf[:3] == b'\xFF\x00\x00'
    print("✓ Rendering 'LOGGING' produces green pixels")
    
    led.trigger_event("TRACK_FOUND", duration_ms=1000)
    assert led._event_active is True
    led._render_event(1500)
    assert led.np.buf[:3] == b'\xFF\xFF\xFF'
    print("✓ Event 'TRACK_FOUND' overlays white pixels correctly")
    
    led.play_logging()
    led.set_track_mode(True)
    led._render_state(1000)
    assert led.np.buf[:3] == b'\x00\x00\x00'
    print("✓ Stealth Mode: 'LOGGING' renders black when track_mode is active")

    led.trigger_event("SECTOR_FAST")
    assert led._event_active is True
    led._render_event(1000)
    assert led.np.buf[:3] == b'\xFF\x00\x00'
    print("✓ Sector Pulse: Overlays even while in Stealth Mode")

    led.play_booting()
    assert led.get_health()["track_mode"] is False
    print("✓ Track Mode reset upon 'play_booting'")

    led.play_heartbeat_send()
    led._render_state(100)
    assert led.np.buf[:3] == b'\x00\xFF\x00'
    led.play_heartbeat_ack()
    led._render_state(100)
    assert led.np.buf[:3] == b'\xFF\x00\x00'
    print("✓ Heartbeat Colors: Red for send, Green for ACK")

    led.play_logging()
    led.set_brightness(0.5)
    led._render_state(100)
    led._apply_brightness_and_write()
    assert led.np.buf[:3] == b'\x7F\x00\x00'
    print("✓ Brightness scaling applies to rendered output")

    health = led.get_health()
    assert "error_count" in health
    assert health["error_count"] == 0
    print("✓ LED health reporting works")

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
