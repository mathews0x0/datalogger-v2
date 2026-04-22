# boot.py - ESP32 boot script
import time
from machine import Pin, SPI


def _early_tft_racesense():
    try:
        from drivers.ili9341 import ILI9341
        spi = SPI(
            1,
            baudrate=40_000_000,
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
            rst=None,
            rotation=1,
            baudrate=40_000_000,
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


_early_tft_racesense()

# Status LED blink after the TFT splash so the display comes alive first.
led = Pin(2, Pin.OUT)
for _ in range(3):
    led.value(1)
    time.sleep(0.08)
    led.value(0)
    time.sleep(0.08)
