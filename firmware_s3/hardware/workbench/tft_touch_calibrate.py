import machine
import time

from drivers.ili9341 import ILI9341
from drivers.xpt2046 import XPT2046


PIN_SPI_SCK = 12
PIN_SPI_MOSI = 11
PIN_SPI_MISO = 13

PIN_TFT_CS = 36
PIN_TFT_DC = 37
PIN_TFT_RST = 42
PIN_TOUCH_CS = 7
PIN_TOUCH_IRQ = 38


POINTS = (
    ("top-left", 20, 20),
    ("top-right", 299, 20),
    ("bottom-right", 299, 219),
    ("bottom-left", 20, 219),
    ("center", 160, 120),
)


def draw_target(display, x, y, color=0xFFFF):
    display.fill(0x0000)
    display.fill_rect(x - 12, y - 1, 25, 3, color)
    display.fill_rect(x - 1, y - 12, 3, 25, color)


def wait_for_release(touch):
    while touch.touched():
        time.sleep_ms(20)


def collect_tap_sample(touch, label, tap_no, samples=12):
    print("Tap {}: {}".format(tap_no, label))
    while not touch.touched():
        time.sleep_ms(20)

    values_x = []
    values_y = []
    values_z = []
    while touch.touched() and len(values_x) < samples:
        raw = touch.read_raw(samples=3)
        if raw:
            values_x.append(raw["x"])
            values_y.append(raw["y"])
            values_z.append(raw["z"])
        time.sleep_ms(20)

    wait_for_release(touch)
    if not values_x:
        print("  no sample")
        return None

    values_x.sort()
    values_y.sort()
    values_z.sort()
    mid = len(values_x) // 2
    sample = {
        "x": values_x[mid],
        "y": values_y[mid],
        "z": values_z[mid],
    }
    print("  sample", sample)
    return sample


def wait_for_two_taps(touch, label):
    taps = []
    while len(taps) < 2:
        sample = collect_tap_sample(touch, label, len(taps) + 1)
        if sample:
            taps.append(sample)
        time.sleep_ms(200)
    return taps


def main():
    spi = machine.SPI(
        1,
        baudrate=40_000_000,
        polarity=0,
        phase=0,
        sck=machine.Pin(PIN_SPI_SCK),
        mosi=machine.Pin(PIN_SPI_MOSI),
        miso=machine.Pin(PIN_SPI_MISO),
    )

    display = ILI9341(
        spi=spi,
        cs=machine.Pin(PIN_TFT_CS, machine.Pin.OUT),
        dc=machine.Pin(PIN_TFT_DC, machine.Pin.OUT),
        rst=machine.Pin(PIN_TFT_RST, machine.Pin.OUT, value=1),
        rotation=1,
        baudrate=40_000_000,
    )

    touch = XPT2046(
        spi=spi,
        cs=machine.Pin(PIN_TOUCH_CS, machine.Pin.OUT),
        irq=machine.Pin(PIN_TOUCH_IRQ, machine.Pin.IN, machine.Pin.PULL_UP),
        baudrate=2_000_000,
    )

    print("Touch calibration start")
    print("Pins: TFT_CS=36 TFT_DC=37 TFT_RST=42 TOUCH_CS=7 TOUCH_IRQ=38 SPI=11/12/13")
    print("Tap each target twice. The marker advances after 2 taps.")

    results = []
    for label, x, y in POINTS:
        draw_target(display, x, y)
        taps = wait_for_two_taps(touch, label)
        print(label, taps)
        results.append((label, taps))
        time.sleep_ms(300)

    display.fill(0x0000)

    usable = {label: taps[-1] for label, taps in results if taps}
    if len(usable) < 4:
        print("Calibration failed: insufficient samples")
        return

    xmin = min(usable["top-left"]["x"], usable["bottom-left"]["x"])
    xmax = max(usable["top-right"]["x"], usable["bottom-right"]["x"])
    ymin = min(usable["top-left"]["y"], usable["top-right"]["y"])
    ymax = max(usable["bottom-left"]["y"], usable["bottom-right"]["y"])

    print("Suggested calibration:")
    print(
        {
            "xmin": xmin,
            "xmax": xmax,
            "ymin": ymin,
            "ymax": ymax,
            "width": 320,
            "height": 240,
            "swap_xy": True,
            "invert_x": False,
            "invert_y": True,
        }
    )


main()
