#!/usr/bin/env python3
"""
Qrio Smart Lock Unlock Script with UI settling detection.
Waits for UI to stabilize before attempting unlock.
"""

import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import re
import shutil
from pathlib import Path
from typing import Optional, Tuple


QRIO_PACKAGE = "me.qrio.smartlock2"
QRIO_MAIN_ACTIVITY = "me.qrio.smartlock2/.presentation.lock.common.LockHomeActivity"
MAX_ATTEMPTS = 10
REQUIRED_STABLE = 2  # UI must be stable for 2 consecutive checks
UI_DUMP_PATH = "/sdcard/ui_current.xml"
TMP_CURRENT = "/tmp/ui_current.xml"
TMP_PREVIOUS = "/tmp/ui_previous.xml"
UI_FINAL_PATH = Path.home() / "sandbox/playground/ui_final.xml"

# Timing configuration (in seconds)
SLEEP_AFTER_WAKE = 0.3      # Wait after waking device (default: 0.5)
SLEEP_AFTER_SWIPE = 0.3     # Wait after unlock swipe (default: 0.5)
SLEEP_AFTER_LAUNCH = 1.0    # Wait after launching app (default: 2.0)
SLEEP_BETWEEN_DUMPS = 0.5   # Wait between UI dumps (default: 1.0)


def run_adb_command(args: list, check: bool = True, capture_output: bool = False) -> subprocess.CompletedProcess:
    """Run an ADB command with the given arguments."""
    cmd = ["adb"] + args
    return subprocess.run(cmd, check=check, capture_output=capture_output, text=True)


def check_device_connected() -> bool:
    """Check if an Android device is connected via ADB."""
    result = run_adb_command(["devices"], capture_output=True)
    # Look for lines ending with "device" (not "unauthorized" or other states)
    return any(line.strip().endswith("device") for line in result.stdout.splitlines()[1:])


def wake_device():
    """Wake up the device and unlock the screen."""
    print("📲 Waking up device...")
    run_adb_command(["shell", "input", "keyevent", "KEYCODE_WAKEUP"])
    time.sleep(SLEEP_AFTER_WAKE)

    # Unlock screen (swipe up)
    run_adb_command(["shell", "input", "swipe", "500", "1500", "500", "500"])
    time.sleep(SLEEP_AFTER_SWIPE)


def launch_qrio_app():
    """Launch the Qrio Smart Lock app (reuses existing instance if already running)."""
    print("🚀 Launching Qrio app...")
    # Use FLAG_ACTIVITY_SINGLE_TOP (0x20000000) to reuse existing instance
    # This prevents creating duplicate instances if the activity is already running
    run_adb_command([
        "shell", "am", "start",
        "-n", QRIO_MAIN_ACTIVITY,
        "-f", "0x20000000"  # FLAG_ACTIVITY_SINGLE_TOP
    ])
    time.sleep(SLEEP_AFTER_LAUNCH)


def dump_ui_to_file() -> bool:
    """Dump the current UI hierarchy to a file."""
    try:
        run_adb_command(
            ["shell", "uiautomator", "dump", UI_DUMP_PATH],
            capture_output=True
        )
        run_adb_command(["pull", UI_DUMP_PATH, TMP_CURRENT], capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False


def files_are_identical(file1: str, file2: str) -> bool:
    """Check if two files are identical."""
    try:
        with open(file1, 'rb') as f1, open(file2, 'rb') as f2:
            return f1.read() == f2.read()
    except FileNotFoundError:
        return False


def wait_for_ui_to_settle() -> bool:
    """Wait for the UI to stabilize by comparing consecutive UI dumps."""
    print("⏳ Waiting for UI to settle...")
    stable_count = 0

    for i in range(1, MAX_ATTEMPTS + 1):
        if not dump_ui_to_file():
            print(f"   ⚠️  Failed to dump UI (attempt {i}/{MAX_ATTEMPTS})")
            time.sleep(SLEEP_BETWEEN_DUMPS)
            continue

        if i > 1:
            # Compare with previous dump
            if files_are_identical(TMP_PREVIOUS, TMP_CURRENT):
                stable_count += 1
                print(f"   UI stable ({stable_count}/{REQUIRED_STABLE})")

                if stable_count >= REQUIRED_STABLE:
                    print("✅ UI has settled")
                    return True
            else:
                stable_count = 0
                print(f"   UI still changing... (attempt {i}/{MAX_ATTEMPTS})")
        else:
            print("   Taking initial snapshot...")

        # Copy current to previous for next iteration
        shutil.copy(TMP_CURRENT, TMP_PREVIOUS)
        time.sleep(SLEEP_BETWEEN_DUMPS)

    print("⚠️  Warning: UI may not be fully settled, proceeding anyway...")
    return False


def get_button_center(bounds: str) -> Optional[Tuple[int, int]]:
    """Extract center coordinates from bounds string like '[x1,y1][x2,y2]'."""
    match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
    if match:
        x1, y1, x2, y2 = map(int, match.groups())
        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2
        return (center_x, center_y)
    return None


def find_popup_button(button_text: str) -> Optional[Tuple[int, int]]:
    """
    Find a button by text in a popup dialog.
    Returns coordinates as (x, y) tuple or None if not found.
    """
    try:
        tree = ET.parse(TMP_CURRENT)
        root = tree.getroot()

        # Look for buttons with specific text (Later, Confirm, OK, etc.)
        for elem in root.iter():
            text = elem.get('text', '')
            clickable = elem.get('clickable', 'false')
            bounds = elem.get('bounds', '')

            if clickable == 'true' and button_text.lower() in text.lower() and bounds:
                coords = get_button_center(bounds)
                if coords:
                    return coords

        return None
    except Exception as e:
        return None


def dismiss_popup(verbose: bool = True) -> bool:
    """
    Detect and dismiss popup dialogs by looking for common dismiss buttons.
    Tries multiple button texts to handle various popup types.
    Returns True if a popup was dismissed, False otherwise.
    """
    # Common dismiss button texts (case-insensitive matching)
    dismiss_buttons = ['Later', 'OK', 'Cancel', 'Close', 'Dismiss', 'Not now', 'Skip']

    try:
        for button_text in dismiss_buttons:
            coords = find_popup_button(button_text)
            if coords:
                if verbose:
                    print(f"   ℹ️  Popup detected, tapping '{button_text}' at ({coords[0]}, {coords[1]})...")
                run_adb_command(["shell", "input", "tap", str(coords[0]), str(coords[1])])
                time.sleep(0.5)  # Wait for popup to dismiss
                return True

        return False

    except Exception as e:
        return False


def find_unlock_button() -> Optional[Tuple[int, int]]:
    """
    Analyze the UI dump to find the unlock button.
    Returns coordinates as (x, y) tuple or None if not found.
    """
    try:
        tree = ET.parse(TMP_CURRENT)
        root = tree.getroot()

        # Look for the main unlock button (large circular button in center)
        # It's a FrameLayout that's clickable and in the middle of the screen
        for elem in root.iter():
            clickable = elem.get('clickable', 'false')
            bounds = elem.get('bounds', '')

            if clickable == 'true' and bounds:
                match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if match:
                    x1, y1, x2, y2 = map(int, match.groups())
                    width = x2 - x1
                    height = y2 - y1

                    # Look for large square-ish button in the middle area
                    # The unlock button is typically 300-500px wide and centered
                    if width > 300 and height > 300 and x1 < 300 and x2 > 400:
                        coords = get_button_center(bounds)
                        if coords:
                            return coords

        return None
    except Exception as e:
        print(f"   ⚠️  Error parsing UI: {e}")
        return None


def tap_unlock_button(x: int, y: int):
    """Tap at the given coordinates."""
    print(f"🔓 Tapping unlock button at ({x}, {y})...")
    run_adb_command(["shell", "input", "tap", str(x), str(y)])
    print("✅ Unlock command sent!")


def cleanup():
    """Clean up temporary files."""
    for tmp_file in [TMP_CURRENT, TMP_PREVIOUS]:
        Path(tmp_file).unlink(missing_ok=True)

    run_adb_command(
        ["shell", "rm", "-f", UI_DUMP_PATH],
        check=False,
        capture_output=True
    )


def save_final_ui_dump():
    """Save the final UI dump for inspection."""
    try:
        UI_FINAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(TMP_CURRENT, UI_FINAL_PATH)
        print(f"💾 Saved final UI state to {UI_FINAL_PATH}")
    except Exception as e:
        print(f"   ⚠️  Could not save final UI dump: {e}")


def unlock_qrio_lock(verbose: bool = True) -> bool:
    """
    Unlock the Qrio smart lock via ADB.

    Args:
        verbose: If True, prints status messages. If False, runs silently.

    Returns:
        True if unlock was successful, False otherwise.

    Raises:
        RuntimeError: If no ADB device is connected.
    """
    if verbose:
        print("🔓 Unlocking Qrio Smart Lock...")

    # Check if device is connected
    if not check_device_connected():
        raise RuntimeError("No ADB device connected")

    try:
        # Wake up device and unlock screen
        if verbose:
            wake_device()
        else:
            run_adb_command(["shell", "input", "keyevent", "KEYCODE_WAKEUP"])
            time.sleep(SLEEP_AFTER_WAKE)
            run_adb_command(["shell", "input", "swipe", "500", "1500", "500", "500"])
            time.sleep(SLEEP_AFTER_SWIPE)

        # Launch Qrio app
        if verbose:
            launch_qrio_app()
        else:
            run_adb_command([
                "shell", "am", "start",
                "-n", QRIO_MAIN_ACTIVITY,
                "-f", "0x20000000"
            ], capture_output=True)
            time.sleep(SLEEP_AFTER_LAUNCH)

        # Wait for UI to settle
        if verbose:
            wait_for_ui_to_settle()
        else:
            # Silent version
            stable_count = 0
            for i in range(1, MAX_ATTEMPTS + 1):
                if not dump_ui_to_file():
                    time.sleep(SLEEP_BETWEEN_DUMPS)
                    continue
                if i > 1 and files_are_identical(TMP_PREVIOUS, TMP_CURRENT):
                    stable_count += 1
                    if stable_count >= REQUIRED_STABLE:
                        break
                else:
                    stable_count = 0
                shutil.copy(TMP_CURRENT, TMP_PREVIOUS)
                time.sleep(SLEEP_BETWEEN_DUMPS)

        # Save final UI dump (always silent)
        try:
            UI_FINAL_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(TMP_CURRENT, UI_FINAL_PATH)
        except Exception:
            pass

        # Check for and dismiss any popups
        if dismiss_popup(verbose=verbose):
            # Popup was dismissed, wait a moment and get fresh UI dump
            time.sleep(0.5)
            dump_ui_to_file()

        # Analyze UI to find unlock button
        coords = find_unlock_button()

        if coords:
            x, y = coords
            if verbose:
                print(f"✅ Found unlock button at: {x} {y}")
            tap_unlock_button(x, y)
        else:
            # Fallback to default coordinates
            if verbose:
                print("⚠️  Using default coordinates (360, 684)")
            run_adb_command(["shell", "input", "tap", "360", "684"])

        if verbose:
            print("✅ Unlock command sent!")

        return True

    except Exception as e:
        if verbose:
            print(f"❌ Error: {e}")
        return False
    finally:
        # Always cleanup temporary files
        cleanup()


def main():
    """Main execution flow for CLI usage."""
    print("🔓 Qrio Smart Lock Unlock Script (with UI settling)")
    print("=" * 52)

    try:
        unlock_qrio_lock(verbose=True)
        print()
        print("🎉 Done!")
        print()
        print(f"💡 Tip: Check {UI_FINAL_PATH} to see the final UI state")
    except RuntimeError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
