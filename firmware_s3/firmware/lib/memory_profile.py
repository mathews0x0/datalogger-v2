import gc

try:
    import esp32
except ImportError:
    esp32 = None


def _sum_region_values(regions, index):
    total = 0
    for region in regions:
        try:
            total += int(region[index])
        except Exception:
            pass
    return total


def _max_region_value(regions, index):
    value = 0
    for region in regions:
        try:
            current = int(region[index])
            if current > value:
                value = current
        except Exception:
            pass
    return value


def get_memory_profile():
    try:
        gc.collect()
    except Exception:
        pass

    gc_free = 0
    gc_alloc = 0
    try:
        gc_free = int(gc.mem_free())
        gc_alloc = int(gc.mem_alloc())
    except Exception:
        pass

    regions = []
    if esp32 and hasattr(esp32, "idf_heap_info") and hasattr(esp32, "HEAP_DATA"):
        try:
            regions = esp32.idf_heap_info(esp32.HEAP_DATA) or []
        except Exception:
            regions = []

    info = {
        "gc_free": gc_free,
        "gc_alloc": gc_alloc,
        "gc_total": gc_free + gc_alloc,
        "idf_regions": len(regions),
        "idf_total": _sum_region_values(regions, 0),
        "idf_free": _sum_region_values(regions, 1),
        "idf_largest": _max_region_value(regions, 2),
        "idf_min_free": _sum_region_values(regions, 3),
    }
    info["psram_present"] = bool(info["gc_total"] >= (1024 * 1024) or info["idf_total"] >= (2 * 1024 * 1024))
    return info


def format_bytes(num_bytes):
    if num_bytes >= 1024 * 1024:
        return "%.2f MB" % (num_bytes / (1024.0 * 1024.0))
    return "%.1f KB" % (num_bytes / 1024.0)


def format_memory_profile(info):
    parts = [
        "GC total=%s" % format_bytes(info.get("gc_total", 0)),
        "free=%s" % format_bytes(info.get("gc_free", 0)),
    ]
    if info.get("idf_total", 0):
        parts.append("IDF total=%s" % format_bytes(info.get("idf_total", 0)))
        parts.append("free=%s" % format_bytes(info.get("idf_free", 0)))
        parts.append("largest=%s" % format_bytes(info.get("idf_largest", 0)))
    parts.append("PSRAM=%s" % ("yes" if info.get("psram_present") else "no"))
    return " | ".join(parts)


def recommended_stream_chunk_size():
    info = get_memory_profile()
    free_mem = info.get("gc_free", 0)
    max_chunk = 128 * 1024 if info.get("psram_present") else 4 * 1024
    if free_mem <= 0:
        return 1024
    target = free_mem // 4
    if target < 1024:
        return 1024
    if target > max_chunk:
        return max_chunk
    return target - (target % 1024)
