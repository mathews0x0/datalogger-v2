import json
import os
import time
import machine

DIAG_DIR = "/data/metadata"
STATE_PATH = DIAG_DIR + "/boot_state.json"
HISTORY_PATH = DIAG_DIR + "/boot_history.json"
MAX_HISTORY = 8

_state = None


def _ensure_dir(path):
    try:
        os.mkdir(path)
    except OSError:
        pass


def _ensure_paths():
    _ensure_dir("/data")
    _ensure_dir(DIAG_DIR)


def _load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


def _reset_cause_name():
    cause = machine.reset_cause()
    mapping = {
        getattr(machine, "PWRON_RESET", -1): "PWRON_RESET",
        getattr(machine, "HARD_RESET", -2): "HARD_RESET",
        getattr(machine, "WDT_RESET", -3): "WDT_RESET",
        getattr(machine, "DEEPSLEEP_RESET", -4): "DEEPSLEEP_RESET",
        getattr(machine, "SOFT_RESET", -5): "SOFT_RESET",
        getattr(machine, "BROWN_OUT_RESET", -6): "BROWN_OUT_RESET",
    }
    return mapping.get(cause, "UNKNOWN_%s" % cause)


def _append_history(entry):
    history = _load_json(HISTORY_PATH, [])
    history.append(entry)
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]
    _save_json(HISTORY_PATH, history)


def boot_start():
    global _state

    _ensure_paths()
    prev = _load_json(STATE_PATH, {})
    reset_cause = _reset_cause_name()
    prev_boot_id = prev.get("boot_id", 0)

    if prev and not prev.get("boot_completed") and not prev.get("expected_reset"):
        _append_history({
            "boot_id": prev.get("boot_id"),
            "last_phase": prev.get("last_phase"),
            "last_note": prev.get("last_note"),
            "exception": prev.get("exception"),
            "next_reset_cause": reset_cause,
            "ts": time.time() if hasattr(time, "time") else 0,
        })

    _state = {
        "boot_id": prev_boot_id + 1,
        "reset_cause": reset_cause,
        "last_phase": "BOOT_START",
        "last_note": "",
        "phase_ticks_ms": time.ticks_ms(),
        "boot_completed": False,
        "expected_reset": False,
        "expected_reset_reason": "",
        "exception": "",
    }
    _save_json(STATE_PATH, _state)
    return prev, _state


def record_phase(phase, note=""):
    global _state
    if _state is None:
        boot_start()

    if _state.get("last_phase") == phase and _state.get("last_note") == note:
        return

    _state["last_phase"] = phase
    _state["last_note"] = note
    _state["phase_ticks_ms"] = time.ticks_ms()
    _save_json(STATE_PATH, _state)


def mark_boot_completed(note=""):
    global _state
    if _state is None:
        boot_start()
    _state["boot_completed"] = True
    if note:
        _state["last_note"] = note
    _save_json(STATE_PATH, _state)


def mark_expected_reset(reason):
    global _state
    if _state is None:
        boot_start()
    _state["expected_reset"] = True
    _state["expected_reset_reason"] = reason
    _save_json(STATE_PATH, _state)


def mark_exception(exc):
    global _state
    if _state is None:
        boot_start()
    try:
        _state["exception"] = str(exc)
    except Exception:
        _state["exception"] = "unprintable"
    _save_json(STATE_PATH, _state)


def update_runtime_stats(**kwargs):
    global _state
    if _state is None:
        boot_start()
    for key, value in kwargs.items():
        _state[key] = value
    _save_json(STATE_PATH, _state)


def get_state():
    return _state or _load_json(STATE_PATH, {})
