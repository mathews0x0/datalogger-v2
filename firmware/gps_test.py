import machine
import time

# SWAPPED PINS TEST
# Original: RX=26, TX=27
# New: RX=27, TX=26
PIN_RX = 27
PIN_TX = 26
BAUDS = [9600, 38400]

print("--- GPS SWAPPED PIN SCAN (RX=27, TX=26) ---")

for baud in BAUDS:
    print(f"\nTrying Baud: {baud}...")
    try:
        uart = machine.UART(2, baudrate=baud, rx=machine.Pin(PIN_RX), tx=machine.Pin(PIN_TX), timeout=200)
        
        start = time.time()
        found = False
        while time.time() - start < 3:
            if uart.any():
                data = uart.read()
                if data:
                    try:
                        decoded = data.decode('utf-8', 'ignore').strip()
                        if '$' in decoded:
                            print(f"SUCCESS! Found NMEA data at {baud} (Swapped Pins):")
                            print(decoded[:100] + "...")
                            found = True
                            break
                    except: pass
            time.sleep(0.05)
            
        if found: break
            
    except Exception as e:
        print(f"Error: {e}")

print("\nScan Complete.")
