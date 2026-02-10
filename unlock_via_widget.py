#!/usr/bin/env python3
"""
Unlock Qrio via Widget Tap.
Wakes device, goes to Home screen, and taps the Qrio widget.
"""

import subprocess
import time

# CONFIGURATION
# Coordinates of the widget (found via scan)
# NOTE: This assumes the Qrio widget is placed on your PRIMARY home screen 
# at these exact coordinates. If you move the widget, you must update these.
WIDGET_X = 498
WIDGET_Y = 359


def run_adb(args):
    """
    Run an ADB command.
    
    Returns:
        bool: True if the command completed successfully, False otherwise.
    """
    cmd = ["adb"] + args
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ ADB command failed: {' '.join(cmd)}")
        if e.stderr:
            print(f"   Stderr: {e.stderr.strip()}")
        return False


def unlock_via_widget():
    """
    Wake the screen, ensure Home screen is visible, and tap widget.
    
    Returns:
        bool: True if all ADB commands succeeded, False otherwise.
    """
    print("📱 Waking device & going to Home...")
    
    success = True
    
    # 1. Wake up
    if not run_adb(["shell", "input", "keyevent", "KEYCODE_WAKEUP"]):
        success = False
    time.sleep(0.1)
    
    # 2. Dismiss Keyguard (Unlock screen)
    if not run_adb(["shell", "wm", "dismiss-keyguard"]):
        success = False
    time.sleep(0.1)

    # 3. Force Home Screen (ensures we are looking at the widget)
    # Sending it twice handles cases where an app folder is open or we're in a submenu
    if not run_adb(["shell", "input", "keyevent", "KEYCODE_HOME"]):
        success = False
    time.sleep(0.1)
    if not run_adb(["shell", "input", "keyevent", "KEYCODE_HOME"]):
        success = False
    time.sleep(0.3)  # Wait for animation

    # 4. Tap the widget
    print(f"👆 Tapping widget at ({WIDGET_X}, {WIDGET_Y})...")
    if not run_adb(["shell", "input", "tap", str(WIDGET_X), str(WIDGET_Y)]):
        success = False

    if success:
        print("✅ Unlock command sent!")
    else:
        print("❌ Unlock failed; see ADB error output above.")
    
    return success


if __name__ == "__main__":
    success = unlock_via_widget()
    exit(0 if success else 1)