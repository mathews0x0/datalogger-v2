# boot.py - ESP32 Boot Script
import network
import time
from machine import Pin

# Status LED
led = Pin(2, Pin.OUT)
led.value(1)  # On during boot
