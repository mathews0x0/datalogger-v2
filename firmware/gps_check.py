import machine
import time

# Confirmed Pinout:
# ESP32 RX = 27  (Connects to GPS TX)
# ESP32 TX = 26  (Connects to GPS RX)
PIN_RX = 27
PIN_TX = 26
BAUD = 9600

print(f"--- FINAL GPS CHECK (RX={PIN_RX}, TX={PIN_TX}) ---")
uart = machine.UART(2, baudrate=BAUD, rx=machine.Pin(PIN_RX), tx=machine.Pin(PIN_TX), timeout=500)

print("Listening for NMEA data...")
start = time.time()
count = 0

while time.time() - start < 10:
    if uart.any():
        try:
            line = uart.readline()
            if line:
                print(line.decode('utf-8', 'ignore').strip())
                count += 1
                if count > 5:
                    print("\nData received successfully!")
                    break
        except Exception as e:
            print(f"Error: {e}")
    time.sleep(0.01)

if count == 0:
    print("\nNO DATA RECEIVED.")
