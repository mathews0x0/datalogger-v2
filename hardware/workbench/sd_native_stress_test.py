import machine
import os
import time
import gc

# Pin Configuration
PIN_CS = 10
PIN_SCK = 12
PIN_MOSI = 11
PIN_MISO = 13

# Test Configuration
TEST_FILE = "/sd/stress_test.bin"
FILE_SIZE_MB = 5
CHUNK_SIZE = 16 * 1024  # 16KB buffer for speed

def run_stress_test():
    print("=" * 50)
    print(" NATIVE SD CARD STRESS TEST (5MB)")
    print("=" * 50)
    
    sd = None
    try:
        print("[1] Initializing machine.SDCard (Slot 2)...")
        sd = machine.SDCard(slot=2, width=1,
                            sck=machine.Pin(PIN_SCK),
                            mosi=machine.Pin(PIN_MOSI),
                            miso=machine.Pin(PIN_MISO),
                            cs=machine.Pin(PIN_CS))
        
        print("[2] Mounting /sd...")
        os.mount(sd, "/sd")
        
        # Cleanup previous test
        try: os.remove(TEST_FILE)
        except: pass
        
        # --- WRITE TEST ---
        print(f"[3] Writing {FILE_SIZE_MB}MB file using {CHUNK_SIZE/1024}KB chunks...")
        data = os.urandom(CHUNK_SIZE) # Fixed random pattern for this run
        
        start_write = time.ticks_ms()
        bytes_written = 0
        with open(TEST_FILE, "wb") as f:
            for i in range((FILE_SIZE_MB * 1024 * 1024) // CHUNK_SIZE):
                f.write(data)
                bytes_written += CHUNK_SIZE
                if i % 16 == 0:
                    print(f"    Written: {bytes_written / (1024*1024):.1f} MB...", end="\r")
        
        end_write = time.ticks_ms()
        write_time = time.ticks_diff(end_write, start_write) / 1000
        write_speed = (bytes_written / 1024) / write_time
        print(f"\n    Write Complete: {write_time:.2f}s ({write_speed:.2f} KB/s)")
        
        # --- READ & VERIFY TEST ---
        print(f"[4] Reading back and verifying...")
        gc.collect()
        
        start_read = time.ticks_ms()
        bytes_read = 0
        with open(TEST_FILE, "rb") as f:
            for i in range((FILE_SIZE_MB * 1024 * 1024) // CHUNK_SIZE):
                check_data = f.read(CHUNK_SIZE)
                if check_data != data:
                    print(f"\n    DATA CORRUPTION at chunk {i}!")
                    return
                bytes_read += CHUNK_SIZE
                if i % 16 == 0:
                    print(f"    Read: {bytes_read / (1024*1024):.1f} MB...", end="\r")
                    
        end_read = time.ticks_ms()
        read_time = time.ticks_diff(end_read, start_read) / 1000
        read_speed = (bytes_read / 1024) / read_time
        print(f"\n    Read Complete: {read_time:.2f}s ({read_speed:.2f} KB/s)")
        
        print("\n" + "=" * 50)
        print(" SUCCESS: 5MB STRESS TEST PASSED BIT-PERFECT!")
        print("=" * 50)
        
    except Exception as e:
        print("\nFAILED:", e)
        import sys
        sys.print_exception(e)
    finally:
        try: os.umount("/sd")
        except: pass
        if sd:
            try: sd.deinit()
            except: pass

if __name__ == "__main__":
    run_stress_test()
