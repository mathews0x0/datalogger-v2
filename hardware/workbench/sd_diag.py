import machine
import os
import time
import sys


PIN_SD_SCK = 12
PIN_SD_MOSI = 11
PIN_SD_MISO = 13
PIN_SD_CS = 10
PIN_SD_CD = 40


def card_detect_state():
    pin = machine.Pin(PIN_SD_CD, machine.Pin.IN, machine.Pin.PULL_UP)
    raw = pin.value()
    inserted = (raw == 0)
    print("[SD] card detect raw=%d inserted=%s" % (raw, inserted))
    return inserted


def try_mount(label, delay_ms=0):
    if delay_ms:
        time.sleep_ms(delay_ms)
    sd = None
    print("[SD] attempt %s" % label)
    try:
        sd = machine.SDCard(
            slot=2,
            width=1,
            sck=machine.Pin(PIN_SD_SCK),
            mosi=machine.Pin(PIN_SD_MOSI),
            miso=machine.Pin(PIN_SD_MISO),
            cs=machine.Pin(PIN_SD_CS),
        )
        print("[SD] SDCard object created")
        os.mount(sd, "/sd")
        print("[SD] mount OK")
        print("[SD] root:", os.listdir("/sd"))
        path = "/sd/diag.txt"
        with open(path, "w") as f:
            f.write("sd diag ok\n")
        with open(path, "r") as f:
            print("[SD] readback:", f.read().strip())
        try:
            os.remove(path)
        except Exception:
            pass
        return True
    except Exception as e:
        print("[SD] failure:", e)
        sys.print_exception(e)
        return False
    finally:
        try:
            os.umount("/sd")
            print("[SD] unmounted")
        except Exception:
            pass
        if sd is not None:
            try:
                sd.deinit()
                print("[SD] deinit OK")
            except Exception:
                pass


def run():
    print("=" * 40)
    print("SD DIAG START")
    print("pins: cs=10 mosi=11 sck=12 miso=13 cd=40")
    print("=" * 40)
    card_detect_state()
    ok = False
    for idx, delay_ms in enumerate((0, 100, 300, 800), start=1):
        if try_mount("%d delay=%dms" % (idx, delay_ms), delay_ms=delay_ms):
            ok = True
            break
    print("=" * 40)
    print("SD DIAG RESULT:", "PASS" if ok else "FAIL")
    print("=" * 40)


run()
