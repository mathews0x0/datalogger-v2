import machine
import time

led = machine.Pin(2, machine.Pin.OUT)

print("Starting blink test on GPIO 2...")
while True:
    led.value(1)
    time.sleep(0.5)
    led.value(0)
    time.sleep(0.5)
    print("Blink...")
