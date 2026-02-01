import machine
import time

# User Wiring:
# GPS TX Pin ---> ESP32 GPIO 27 (So ESP32 needs to LISTEN/RX on 27)
# GPS RX Pin <--- ESP32 GPIO 26 (So ESP32 needs to TALK/TX on 26)

PIN_ESP_RX = 27
PIN_ESP_TX = 26
BAUD_RATES = [9600, 38400, 115200]

print("\n==================================")
print(f"GPS WIRING VERIFICATION")
print(f"ESP32 RX Pin: {PIN_ESP_RX} (Expecting signal from GPS TX)")
print(f"ESP32 TX Pin: {PIN_ESP_TX} (Sending signal to GPS RX)")
print("==================================\n")

for baud in BAUD_RATES:
    print(f"Testing Baud Rate: {baud}...")
    try:
        # buf_rx=1024 to catch burst data
        uart = machine.UART(2, baudrate=baud, rx=machine.Pin(PIN_ESP_RX), tx=machine.Pin(PIN_ESP_TX), timeout=300, timeout_char=50)
        
        # Listen for 3 seconds
        start = time.time()
        timeout = 3
        
        data_found = False
        while time.time() - start < timeout:
             if uart.any():
                raw = uart.read()
                if raw:
                    try:
                        text = raw.decode('utf-8', 'ignore').strip()
                        # Filter for NMEA start char
                        if '$' in text:
                            print(f"\n[SUCCESS] Data received at {baud} baud!")
                            print("-" * 40)
                            print(text[:200]) # Print first 200 chars
                            print("-" * 40)
                            data_found = True
                            break
                        else:
                            # Print non-NMEA noise just in case
                            print(".", end='') 
                    except:
                        print("?", end='')
             time.sleep(0.05)
             
        if data_found:
            print(f"\nLocked on {baud} baud. Monitoring stream for 5 more seconds...")
            mon_start = time.time()
            while time.time() - mon_start < 5:
                if uart.any():
                    line = uart.readline()
                    if line:
                        print(line.decode('utf-8', 'ignore').strip())
                time.sleep(0.01)
            break
            
    except Exception as e:
        print(f"\nUART Error: {e}")
        
    print("\nNo valid data found at this rate.")

print("\nTest Complete.")
