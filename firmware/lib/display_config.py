import os
import ujson


DISPLAY_CONFIG_PATH = "/data/metadata/display.json"
DEFAULT_DISPLAY_CONFIG = {
    "name": "legacy-default",
    "rotation": 1,
    "madctl": 0x28,
    "baudrate": 40_000_000,
}
DISPLAY_PRESETS = (
    {
        "name": "legacy-default",
        "rotation": 1,
        "madctl": 0x28,
        "baudrate": 40_000_000,
    },
    {
        "name": "panel-222",
        "rotation": 1,
        "madctl": 0x88,
        "baudrate": 40_000_000,
    },
    {
        "name": "panel-225",
        "rotation": 1,
        "madctl": 0x4C,
        "baudrate": 40_000_000,
    },
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
    cfg["rotation"] = int(cfg.get("rotation", 1)) % 4
    cfg["madctl"] = int(cfg.get("madctl", DEFAULT_DISPLAY_CONFIG["madctl"])) & 0xFF
    cfg["baudrate"] = max(1_000_000, int(cfg.get("baudrate", DEFAULT_DISPLAY_CONFIG["baudrate"])))
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
        with open(DISPLAY_CONFIG_PATH, "w") as f:
            ujson.dump(cfg, f)
        return True
    except Exception as e:
        print("[TFT] Display config save failed:", e)
        return False
