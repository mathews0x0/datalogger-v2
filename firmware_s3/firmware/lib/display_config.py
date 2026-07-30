import os
import ujson


DISPLAY_CONFIG_PATH = "/data/metadata/display.json"
DEFAULT_DISPLAY_CONFIG = {
    "name": "legacy-default",
    "rotation": 1,
    "madctl": 0x20,
    "baudrate": 40_000_000,
    "swap_bytes": True,
}
DISPLAY_PRESETS = (
    {
        "name": "legacy-default",
        "rotation": 1,
        "madctl": 0x20,
        "baudrate": 40_000_000,
        "swap_bytes": True,
    },
    {
        "name": "panel-222",
        "rotation": 1,
        "madctl": 0x80,
        "baudrate": 40_000_000,
        "swap_bytes": True,
    },
    {
        "name": "panel-225",
        "rotation": 1,
        "madctl": 0x44,
        "baudrate": 40_000_000,
        "swap_bytes": True,
    },
)


def display_configs_equal(a, b):
    a = normalize_display_config(a)
    b = normalize_display_config(b)
    return (
        a.get("rotation") == b.get("rotation")
        and a.get("madctl") == b.get("madctl")
        and a.get("baudrate") == b.get("baudrate")
        and bool(a.get("swap_bytes")) == bool(b.get("swap_bytes"))
    )


def normalize_display_config(data=None):
    cfg = dict(DEFAULT_DISPLAY_CONFIG)
    if isinstance(data, dict):
        if data.get("name"):
            cfg["name"] = str(data["name"])
        for key in ("rotation", "madctl", "baudrate"):
            if key in data:
                try:
                    cfg[key] = int(data[key])
                except Exception:
                    pass
        if "swap_bytes" in data:
            cfg["swap_bytes"] = bool(data["swap_bytes"])
    cfg["rotation"] = int(cfg.get("rotation", 1)) % 4
    cfg["madctl"] = int(cfg.get("madctl", DEFAULT_DISPLAY_CONFIG["madctl"])) & 0xFF
    cfg["baudrate"] = max(1_000_000, int(cfg.get("baudrate", DEFAULT_DISPLAY_CONFIG["baudrate"])))
    cfg["swap_bytes"] = bool(cfg.get("swap_bytes", True))
    return cfg


def iter_display_presets():
    return [normalize_display_config(item) for item in DISPLAY_PRESETS]


def display_config_exists():
    try:
        os.stat(DISPLAY_CONFIG_PATH)
        return True
    except OSError:
        return False


def load_display_config(default=None):
    try:
        with open(DISPLAY_CONFIG_PATH, "r") as f:
            return normalize_display_config(ujson.load(f))
    except Exception:
        return normalize_display_config(default)


def _ensure_metadata_dir():
    try:
        os.mkdir("/data")
    except OSError:
        pass
    try:
        os.mkdir("/data/metadata")
    except OSError:
        pass


def save_display_config(config):
    try:
        _ensure_metadata_dir()
        cfg = normalize_display_config(config)
        tmp_path = DISPLAY_CONFIG_PATH + ".tmp"
        with open(tmp_path, "w") as f:
            ujson.dump(cfg, f)
        try:
            os.remove(DISPLAY_CONFIG_PATH)
        except OSError:
            pass
        os.rename(tmp_path, DISPLAY_CONFIG_PATH)
        loaded = load_display_config()
        if not display_configs_equal(cfg, loaded):
            print("[TFT] Display config verify failed:", cfg, loaded)
            return False
        return True
    except Exception as e:
        print("[TFT] Display config save failed:", e)
        return False
