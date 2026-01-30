# test_gps.py - Verify GPS Module
import machine
import time
import sys

try:
    from drivers.gps import GPS
except ImportError:
    print("Error: drivers/gps.py not found.")
    sys.exit(1)

# PIN CONFIGURATION (ESP32 DevKit V1 - Remapped)
# RX0/TX0 are for USB. We use Software Remap.
# GPS TX -> ESP GPIO 26 (RX)
# GPS RX -> ESP GPIO 27 (TX)
PIN_RX = 26
PIN_TX = 27

def test_gps():
    print(f"Initializing GPS on UART2 (RX={PIN_RX}, TX={PIN_TX})...")
    
    # 1. Setup UART
    # baudrate=9600 is standard for most modules (NEO-6M, etc)
    # Notes: UART2 is safe to remap. UART1 sometimes shares pins with Flash.
    uart = machine.UART(2, baudrate=9600, rx=PIN_RX, tx=PIN_TX, timeout=500)
    
    # 2. Setup Driver
    gps = GPS(uart)
    
    print("Waiting for GPS data (Ctrl+C to stop)...")
    print("Note: If indoors, you might not get a fix (valid=False), but you should see Time updating.")
    
    while True:
        fix = gps.update()
        
        # Pretty Print
        ts = fix.get('timestamp') or "--:--:--"
        valid = "FIX" if fix.get('valid') else "NO FIX"
        sats = fix.get('satellites')
        lat = fix.get('lat')
        lon = fix.get('lon')
        speed = fix.get('speed_kmh')
        
        print(f"[{ts}] Status: {valid} | Sats: {sats} | Speed: {speed:.1f} km/h | Loc: {lat}, {lon}")
        
        time.sleep(1.0)

if __name__ == "__main__":
    test_gps()
