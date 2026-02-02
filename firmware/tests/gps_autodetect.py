import machine
import time

# Function to test a specific configuration
def test_gps(rx_pin, tx_pin, label):
    print(f"\n--- Testing Config: {label} ---")
    print(f"ESP32 RX Pin: {rx_pin}")
    print(f"ESP32 TX Pin: {tx_pin}")
    
    BAUDS = [9600, 38400, 115200]
    
    for baud in BAUDS:
        print(f"  > Baud {baud}...", end=" ")
        try:
            # Short timeout check
            uart = machine.UART(2, baudrate=baud, rx=machine.Pin(rx_pin), tx=machine.Pin(tx_pin), timeout=100)
            
            # Flush
            while uart.any(): uart.read()
            
            start = time.time()
            found = False
            chunk = b""
            
            while time.time() - start < 1.5: # 1.5s per baud check
                if uart.any():
                    chunk += uart.read()
                    try:
                        decoded = chunk.decode('utf-8', 'ignore')
                        if '$' in decoded and ('RMC' in decoded or 'GGA' in decoded or 'GLL' in decoded):
                            print("SUCCESS! Valid NMEA found.")
                            print(f"\n[LOCKED] FOUND GPS at Baud {baud} using {label}")
                            print("-" * 40)
                            print(decoded.strip()[:200])
                            print("-" * 40)
                            return True
                    except: pass
                time.sleep(0.01)
            
            print("No data.")
            
        except Exception as e:
            print(f"Error ({e})")
            
    return False

print("\n=== STARTING GPS AUTO-DETECT ===")

# Test 1: Swapped/User Config (RX=27, TX=26)
# This assumes GPS TX is connected to ESP Pin 27
if test_gps(27, 26, "User Config (RX=27, TX=26)"):
    pass

# Test 2: Standard Config (RX=26, TX=27)
# This assumes GPS TX is connected to ESP Pin 26
elif test_gps(26, 27, "Standard Config (RX=26, TX=27)"):
    pass

else:
    print("\n[FAILED] Could not detect GPS on either pin configuration.")
    print("Check: Power (LED?), Wiring integrity, Module orientation.")

print("\n=== DONE ===")
