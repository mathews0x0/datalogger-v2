import gc
import time

from lib.memory_profile import format_memory_profile, get_memory_profile


def fmt(num_bytes):
    if num_bytes >= 1024 * 1024:
        return "%.2f MB" % (num_bytes / (1024.0 * 1024.0))
    return "%.1f KB" % (num_bytes / 1024.0)


def main():
    print("=== RS-Core PSRAM Probe ===")
    info = get_memory_profile()
    print("[Probe] Initial:", format_memory_profile(info))

    if not info.get("psram_present"):
        print("[Probe] PSRAM inference: NOT DETECTED")
        print("[Probe] This usually means the wrong MicroPython image is flashed on N16R8.")
        return

    print("[Probe] PSRAM inference: DETECTED")
    largest_ok = 0
    buf = None
    for size in (
        256 * 1024,
        512 * 1024,
        1024 * 1024,
        2 * 1024 * 1024,
        3 * 1024 * 1024,
        4 * 1024 * 1024,
    ):
        try:
            gc.collect()
            buf = bytearray(size)
            buf[0] = 0x55
            buf[-1] = 0xAA
            largest_ok = size
            print("[Probe] Alloc ok:", fmt(size))
            time.sleep_ms(20)
            del buf
            buf = None
        except Exception as exc:
            print("[Probe] Alloc failed at %s: %s" % (fmt(size), exc))
            break

    gc.collect()
    print("[Probe] Largest successful contiguous allocation:", fmt(largest_ok))
    print("[Probe] Final:", format_memory_profile(get_memory_profile()))


main()
