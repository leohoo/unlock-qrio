#!/usr/bin/env python3
"""
Local notification feedback via ADB for Qrio RFID trigger.
Provides flash + vibrate feedback on the connected Android device.
"""

import subprocess
import threading
import time

TORCH_LED = "/sys/class/leds/flashlight/brightness"
TORCH_ON = "200"
TORCH_OFF = "0"


def _adb(args: list) -> bool:
    """Run an ADB command silently. Returns True on success."""
    try:
        subprocess.run(["adb"] + args, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False


def _torch(on: bool):
    """Turn torch on or off via sysfs LED path."""
    value = TORCH_ON if on else TORCH_OFF
    _adb(["shell", f"echo {value} > {TORCH_LED}"])


def _vibrate(duration_ms: int = 200):
    """Vibrate for given duration in ms."""
    _adb(["shell", "cmd", "vibrator_manager", "synced", "-d", str(duration_ms), "prebaked", "1"])


def _flash_pattern(pattern: list):
    """
    Execute a flash pattern.
    pattern: list of (on: bool, duration: float) tuples
    """
    for on, duration in pattern:
        _torch(on)
        time.sleep(duration)
    _torch(False)  # ensure torch is off at end


def notify_success():
    """
    Authorized card — 3 quick blinks + short vibrate.
    Runs in background thread so it doesn't block unlock.
    """
    def _run():
        pattern = [
            (True, 0.1), (False, 0.1),
            (True, 0.1), (False, 0.1),
            (True, 0.1), (False, 0.1),
        ]
        _flash_pattern(pattern)
        _vibrate(100)

    threading.Thread(target=_run, daemon=True).start()


def notify_unauthorized():
    """
    Unauthorized card — 2 slow blinks + long vibrate.
    Runs in background thread.
    """
    def _run():
        pattern = [
            (True, 0.4), (False, 0.2),
            (True, 0.4), (False, 0.2),
        ]
        _flash_pattern(pattern)
        _vibrate(500)

    threading.Thread(target=_run, daemon=True).start()


def notify_cooldown():
    """
    Card in cooldown — single short blink, no vibrate.
    """
    def _run():
        pattern = [(True, 0.05), (False, 0.0)]
        _flash_pattern(pattern)

    threading.Thread(target=_run, daemon=True).start()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "success":
            print("Testing success notification...")
            notify_success()
        elif cmd == "unauthorized":
            print("Testing unauthorized notification...")
            notify_unauthorized()
        elif cmd == "cooldown":
            print("Testing cooldown notification...")
            notify_cooldown()
        else:
            print(f"Unknown: {cmd}. Use: success | unauthorized | cooldown")
        time.sleep(2)  # wait for background thread
    else:
        print("Usage: python3 notify.py [success|unauthorized|cooldown]")
