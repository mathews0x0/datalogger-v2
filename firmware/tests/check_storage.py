import os
try:
    s = os.statvfs('/')
    free_bytes = s[0] * s[3]
    total_bytes = s[0] * s[2]
    print(f"Total: {total_bytes/1024:.1f} KB")
    print(f"Free:  {free_bytes/1024:.1f} KB")
    
    # Estimate Capacity
    # 60 bytes/line @ 10Hz = 36KB/min
    minutes_10hz = (free_bytes / 1024) / 36
    print(f"Est. 10Hz Recording Time: {minutes_10hz:.0f} minutes")
    
except Exception as e:
    print(f"Error: {e}")
