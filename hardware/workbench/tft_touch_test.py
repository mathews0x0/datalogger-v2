import machine
import time

from drivers.ili9341 import ILI9341
from drivers.xpt2046 import XPT2046


# Shared with SD card on RS-Core V2.
PIN_SPI_SCK = 12
PIN_SPI_MOSI = 11
PIN_SPI_MISO = 13

# Temporary bench mapping: use free GPIOs 36/37/38.
PIN_TFT_CS = 36
PIN_TFT_DC = 37
PIN_TOUCH_CS = 38

# Keep reset and IRQ off-GPIO for the minimal wiring path.
PIN_TFT_RST = None
PIN_TOUCH_IRQ = None


COLORS = (
    0xF800,  # red
    0x07E0,  # green
    0x001F,  # blue
    0xFFE0,  # yellow
    0xFFFF,  # white
    0x0000,  # black
)


def mark_touch(display, x, y):
    size = 6
    display.fill_rect(x - size, y - 1, size * 2, 3, 0xFFFF)
    display.fill_rect(x - 1, y - size, 3, size * 2, 0xFFFF)


def main():
    print("ILI9341 + XPT2046 bring-up")
    print("SPI: SCK=12 MOSI=11 MISO=13")
    print("TFT: CS=36 DC=37 RST=tied-high-or-EN")
    print("TOUCH: CS=38 IRQ=unused")

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
        rst=None,
        rotation=1,
        baudrate=40_000_000,
    )

    touch = XPT2046(
        spi=spi,
        cs=machine.Pin(PIN_TOUCH_CS, machine.Pin.OUT),
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

    for color in COLORS:
        display.fill(color)
        time.sleep_ms(400)

    display.fill(0x0000)
    print("Touch the panel to print coordinates and draw a marker.")

    last = time.ticks_ms()
    while True:
        point = touch.read()
        if point:
            if time.ticks_diff(time.ticks_ms(), last) > 80:
                print("raw=({x},{y}) z={z} screen=({sx},{sy})".format(**point))
                display.fill(0x0000)
                mark_touch(display, point["sx"], point["sy"])
                last = time.ticks_ms()
        time.sleep_ms(10)


main()
