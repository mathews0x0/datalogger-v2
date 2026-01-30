# test_sd.py - Verify SD Card Writing
import machine
import os
import sys
import time

# Add drivers to path if needed (MicroPython usually finds root folders)
try:
    from drivers.sdcard import SDCard
except ImportError:
    print("Error: drivers/sdcard.py not found. Upload it first!")
    sys.exit(1)

# PIN CONFIGURATION (ESP32 DevKit V1 Default SPI)
PIN_SCK = 18
PIN_MISO = 19
PIN_MOSI = 23
PIN_CS = 5

def test_sd():
    print(f"Initializing SD Card (SCK={PIN_SCK}, MISO={PIN_MISO}, MOSI={PIN_MOSI}, CS={PIN_CS})...")
    
    try:
        # 1. Setup SPI
        # Lower baudrate to 400kHz for better stability with jumper wires
        spi = machine.SPI(2, 
                          baudrate=400000, 
                          polarity=0, 
                          phase=0, 
                          sck=machine.Pin(PIN_SCK), 
                          mosi=machine.Pin(PIN_MOSI), 
                          miso=machine.Pin(PIN_MISO))
        
        # 2. Setup SD Driver with Retries
        sd = None
        for attempt in range(3):
            try:
                cs = machine.Pin(PIN_CS, machine.Pin.OUT)
                sd = SDCard(spi, cs)
                break
            except Exception as e:
                print(f"Attempt {attempt+1} failed: {e}")
                time.sleep(0.5)
        
        if not sd:
            raise Exception("Failed to init SD card after 3 attempts")

        # 3. Mount Filesystem
        vfs = os.VfsFat(sd)
        os.mount(vfs, "/sd")
        print("Mount successful -> /sd")
        
        # 4. List Files
        print("Files on SD:", os.listdir("/sd"))
        
        # 5. Write Test
        print("Writing test file...")
        with open("/sd/test_write.txt", "w") as f:
            f.write("Hello from ESP32 DataLogger!\n")
            f.write(f"Timestamp: {machine.time_pulse_us()}\n")
            
        # 6. Read Test
        print("Reading back...")
        with open("/sd/test_write.txt", "r") as f:
            content = f.read()
            print("-" * 20)
            print(content.strip())
            print("-" * 20)
            
        print("TEST PASSED: SD Card is ready.")
        
    except Exception as e:
        print(f"TEST FAILED: {e}")
        
if __name__ == "__main__":
    test_sd()
