# test_gps_raw.py - Raw NMEA monitor
import machine
import time

# RS-Core V2 Pin Config
PIN_GPS_TX = 17 # ESP TX -> GPS RX
PIN_GPS_RX = 18 # ESP RX <- GPS TX

print("Initializing GPS UART (9600 baud)...")
# Note: UART1 on S3 is flexible. 
uart = machine.UART(1, baudrate=9600, tx=machine.Pin(PIN_GPS_TX), rx=machine.Pin(PIN_GPS_RX), timeout=100)

print("Monitoring for NMEA sentences (Ctrl+C to stop)...")
start_time = time.time()
while time.time() - start_time < 30: # Run for 30 seconds
    if uart.any():
        line = uart.read()
        try:
            print(line.decode('utf-8'), end='')
        except:
            print(line, end='')
    time.sleep(0.1)

print("\nTest complete.")
