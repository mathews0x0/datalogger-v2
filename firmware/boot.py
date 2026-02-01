# boot.py - ESP32 Boot Script
import network
import time
from machine import Pin

# Status LED
led = Pin(2, Pin.OUT)
# Blink 3 times quickly to indicate boot
for _ in range(3):
    led.value(1)
    time.sleep(0.1)
    led.value(0)
    time.sleep(0.1)
led.value(1) # Keep on during main boot
