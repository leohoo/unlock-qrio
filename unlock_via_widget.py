#!/usr/bin/env python3
"""
Unlock Qrio via Widget Tap.
Wakes device, goes to Home screen, and taps the Qrio widget.
"""

import subprocess
import time
import sys

# CONFIGURATION
# Coordinates of the widget (found via scan)
# NOTE: This assumes the Qrio widget is placed on your PRIMARY home screen 
# at these exact coordinates. If you move the widget, you must update these.
WIDGET_X = 498
WIDGET_Y = 359


def run_adb(args):
    """Run an ADB command."""
    cmd = ["adb"] + args
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ ADB command failed: {' '.join(cmd)}")
        if e.stderr:
            print(f"   Stderr: {e.stderr.strip()}")


def unlock_via_widget():
    """Wake the screen, ensure Home screen is visible, and tap widget."""
    print("📱 Waking device & going to Home...")
    
    # 1. Wake up
    run_adb(["shell", "input", "keyevent", "KEYCODE_WAKEUP"])
    time.sleep(0.3)
    
    # 2. Dismiss Keyguard (Unlock screen)
    # 82 = KEYCODE_MENU (often unlocks swipe screens)
    run_adb(["shell", "input", "keyevent", "82"])
    time.sleep(0.5)

    # 3. Force Home Screen (ensures we are looking at the widget)
    run_adb(["shell", "input", "keyevent", "KEYCODE_HOME"])
    time.sleep(0.5)

    # 4. Tap the widget
    print(f"👆 Tapping widget at ({WIDGET_X}, {WIDGET_Y})...")
    run_adb(["shell", "input", "tap", str(WIDGET_X), str(WIDGET_Y)])
    print("✅ Unlock command sent!")


if __name__ == "__main__":
    unlock_via_widget()