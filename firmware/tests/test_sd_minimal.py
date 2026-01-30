# test_sd_minimal.py - Raw SPI diagnostics
import machine
import time
import ubinascii

# PINS
SCK = 18
MISO = 19
MOSI = 23
CS = 5

def diagnose():
    print(f"Diagnostics on SPI (SCK={SCK}, MISO={MISO}, MOSI={MOSI}, CS={CS})")
    print("-" * 40)
    
    # 1. Setup CS
    cs = machine.Pin(CS, machine.Pin.OUT)
    cs.value(1) # Disable
    
    # 2. Setup SPI
    try:
        # Lower baud rate for safety (100kHz)
        spi = machine.SPI(2, baudrate=100000, polarity=0, phase=0, 
                          sck=machine.Pin(SCK), mosi=machine.Pin(MOSI), miso=machine.Pin(MISO))
        print("SPI Initialized OK")
    except Exception as e:
        print(f"SPI Init Failed: {e}")
        return

    # 3. Manual CMD0 (Go Idle State) Sequence
    print("Sending CMD0 (Reset)...")
    
    # Wake up clocks
    cs.value(1)
    spi.write(b'\xff' * 10) # 80 clocks
    
    # Assert CS
    cs.value(0)
    
    # Send CMD0: 0x40 (CMD0) | 0x00 00 00 00 (Arg) | 0x95 (CRC)
    spi.write(b'\x40\x00\x00\x00\x00\x95')
    
    # Read Response (R1)
    # Expected: 0x01 (Idle State)
    # If 0xFF: Card processing / No connection (MISO High)
    # If 0x00: Active?
    # If Garbage: Noise
    
    response = bytearray(8)
    spi.readinto(response)
    
    cs.value(1)
    
    print(f"Raw Response Bytes: {ubinascii.hexlify(response)}")
    
    if response[0] == 0x01 or response[1] == 0x01 or response[2] == 0x01:
        print("SUCCESS: Card responded with IDLE state (0x01)!")
        print("Wiring is correct.")
    elif response[0] == 0xFF:
        print("FAILURE: Received 0xFF (All Ones). MISO line might be disconnected.")
    elif response[0] == 0x00:
        print("FAILURE: Received 0x00 (All Zeros). MISO might be shorted to GND.")
    else:
        print("FAILURE: Received Garbage. Noise or Baud rate issue.")

if __name__ == "__main__":
    diagnose()
