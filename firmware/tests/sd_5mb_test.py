"""
SD Card 5MB Stress Write Test
==============================
Writes ~5MB of realistic CSV data to test SD card performance.
Power cycle ESP32 before running.
"""

import machine
import time
import os
import gc

# Pin Configuration
PIN_CS = 5
PIN_SCK = 18
PIN_MOSI = 23
PIN_MISO = 33

# CSV Header (matches actual logged data)
CSV_HEADER = "timestamp,latitude,longitude,speed,satellites,imu_x,imu_y,imu_z,gyro_x,gyro_y,gyro_z,pressure\n"

# Target size: ~5MB
TARGET_SIZE = 5 * 1024 * 1024  # 5MB


def generate_csv_row(base_time, row_num):
    """Generate a realistic CSV row"""
    ts = base_time + (row_num * 0.1)  # ~10Hz
    lat = 11.127990 + (row_num * 0.000001)
    lon = 77.186050 + (row_num * 0.0000005)
    speed = 0.05 + (row_num % 100) * 0.01
    sats = 12
    imu_x = -3600 + (row_num % 200) - 100
    imu_y = -8280 + (row_num % 150) - 75
    imu_z = 13640 + (row_num % 300) - 150
    gyro_x = 290 + (row_num % 50) - 25
    gyro_y = -275 + (row_num % 60) - 30
    gyro_z = 70 + (row_num % 40) - 20
    
    return "%.6f,%.9f,%.11f,%.6f,%d,%d,%d,%d,%d,%d,%d,\n" % (
        ts, lat, lon, speed, sats, imu_x, imu_y, imu_z, gyro_x, gyro_y, gyro_z
    )


def main():
    print("=" * 50)
    print(" SD CARD 5MB STRESS WRITE TEST")
    print("=" * 50)
    
    # Initialize SPI
    print("\n[1] Initializing SPI...")
    spi = machine.SPI(1, baudrate=100000, polarity=0, phase=0,
                      sck=machine.Pin(PIN_SCK),
                      mosi=machine.Pin(PIN_MOSI),
                      miso=machine.Pin(PIN_MISO))
    cs = machine.Pin(PIN_CS, machine.Pin.OUT, value=1)
    
    # Initialize SD card
    print("[2] Initializing SD card...")
    import drivers.sdcard as sdcard
    sd = sdcard.SDCard(spi, cs, baudrate=10_000_000)  # 10MHz
    print("    Sectors: %d (%.2f GB)" % (sd.sectors, sd.sectors * 512 / (1024**3)))
    
    # Mount
    print("[3] Mounting...")
    try:
        os.umount('/sd')
    except:
        pass
    os.mount(sd, '/sd')
    
    stats = os.statvfs('/sd')
    free_before = stats[0] * stats[3]
    print("    Free before: %.2f MB" % (free_before / (1024*1024)))
    
    # Calculate rows needed
    sample_row = generate_csv_row(1768637949.0, 0)
    row_size = len(sample_row)
    rows_needed = TARGET_SIZE // row_size
    print("\n[4] Write Plan:")
    print("    Row size: %d bytes" % row_size)
    print("    Rows needed: %d" % rows_needed)
    print("    Target file: ~5 MB")
    
    # Buffer writes in 4KB chunks for best performance
    BUFFER_SIZE = 4096
    
    print("\n[5] Writing 5MB of CSV data...")
    gc.collect()
    
    filename = '/sd/stress_test.csv'
    base_time = 1768637949.0
    
    start = time.ticks_ms()
    bytes_written = 0
    rows_written = 0
    buffer = ""
    
    with open(filename, 'w') as f:
        # Write header
        f.write(CSV_HEADER)
        bytes_written += len(CSV_HEADER)
        
        # Write rows with buffering
        while bytes_written < TARGET_SIZE:
            row = generate_csv_row(base_time, rows_written)
            buffer += row
            rows_written += 1
            
            # Flush buffer when it's big enough
            if len(buffer) >= BUFFER_SIZE:
                f.write(buffer)
                bytes_written += len(buffer)
                buffer = ""
                
                # Progress every 1MB
                if bytes_written % (1024 * 1024) < BUFFER_SIZE:
                    elapsed = time.ticks_diff(time.ticks_ms(), start)
                    speed = bytes_written * 1000 / elapsed if elapsed > 0 else 0
                    print("    Written: %.2f MB (%.1f KB/s)" % (
                        bytes_written / (1024*1024), speed / 1024))
                    gc.collect()
        
        # Flush remaining buffer
        if buffer:
            f.write(buffer)
            bytes_written += len(buffer)
    
    elapsed = time.ticks_diff(time.ticks_ms(), start)
    
    print("\n[6] Write Complete!")
    print("    Total: %.2f MB" % (bytes_written / (1024*1024)))
    print("    Rows: %d" % rows_written)
    print("    Time: %.2f seconds" % (elapsed / 1000))
    print("    Speed: %.2f KB/s" % (bytes_written / elapsed))
    
    # Verify file
    print("\n[7] Verifying...")
    stat = os.stat(filename)
    file_size = stat[6]
    print("    File size: %.2f MB" % (file_size / (1024*1024)))
    
    # Read first and last lines
    with open(filename, 'r') as f:
        first_line = f.readline()
        print("    Header: %s" % first_line.strip()[:50])
        
    # Check free space
    stats = os.statvfs('/sd')
    free_after = stats[0] * stats[3]
    print("    Space used: %.2f MB" % ((free_before - free_after) / (1024*1024)))
    
    print("\n" + "=" * 50)
    print(" 5MB WRITE TEST COMPLETE!")
    print("=" * 50)


if __name__ == "__main__":
    main()
