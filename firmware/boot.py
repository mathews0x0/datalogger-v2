# boot.py - ESP32 boot script
import time
from machine import Pin, SPI
from lib.display_config import display_config_exists, load_display_config

PIN_POWER_HOLD = 41
PIN_TFT_RST = 42
PIN_TOUCH_IRQ = 38


def _assert_power_hold():
    try:
        # Assert the self-hold rail as early as possible so the board stays
        # powered after the momentary soft-power button is released.
        hold = Pin(PIN_POWER_HOLD, Pin.OUT, value=1)
        hold.value(1)
        return hold
    except Exception as e:
        print("[PWR] Failed to assert hold:", e)
        return None


def _early_tft_racesense():
    try:
        if not display_config_exists():
            print("[TFT] boot splash skipped: display config not set")
            return
        from drivers.ili9341 import ILI9341
        cfg = load_display_config()
        try:
            Pin(7, Pin.OUT, value=1)
        except Exception:
            pass
        try:
            Pin(PIN_TOUCH_IRQ, Pin.IN, Pin.PULL_UP)
        except Exception:
            pass
        spi = SPI(
            1,
            baudrate=cfg["baudrate"],
            polarity=0,
            phase=0,
            sck=Pin(15),
            mosi=Pin(16),
            miso=Pin(9),
        )
        display = ILI9341(
            spi=spi,
            cs=Pin(5, Pin.OUT),
            dc=Pin(6, Pin.OUT),
            rst=Pin(PIN_TFT_RST, Pin.OUT, value=1),
            rotation=cfg["rotation"],
            baudrate=cfg["baudrate"],
            madctl=cfg["madctl"],
        )
        if not _draw_raw_wordmark(spi, display):
            display.fill(0x0000)
            display.fill_rect(0, 0, 320, 3, 0xE283)
            display.fill_rect(0, 237, 320, 3, 0xE283)
            display.fill_rect(68, 83, 184, 4, 0xE283)
    except Exception as e:
        print("[TFT] boot RaceSense skipped:", e)


def _draw_raw_wordmark(spi, display):
    try:
        f = open("/lib/tft_wordmark.raw", "rb")
    except Exception:
        return False
    try:
        display.set_window(0, 0, 319, 239)
        display._activate_spi()
        display.cs.value(0)
        display.dc.value(1)
        while True:
            chunk = f.read(1024)
            if not chunk:
                break
            spi.write(chunk)
        display.cs.value(1)
        return True
    except Exception:
        try:
            display.cs.value(1)
        except Exception:
            pass
        return False
    finally:
        try:
            f.close()
        except Exception:
            pass


_power_hold = _assert_power_hold()
_early_tft_racesense()

# Status LED blink after the TFT splash so the display comes alive first.
led = Pin(2, Pin.OUT)
for _ in range(3):
    led.value(1)
    time.sleep(0.08)
    led.value(0)
    time.sleep(0.08)
