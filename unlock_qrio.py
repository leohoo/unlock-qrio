#!/usr/bin/env python3
"""
Qrio Smart Lock CLI.

Unlocking taps the home screen widget (see unlock_via_widget.py) - the same path the
RFID daemon uses, so a manual run exercises production behaviour. Adds an ADB
connectivity check on top of it, plus a read-only --status mode that reports the lock
state from a UI dump.
"""

import argparse
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import re
from pathlib import Path
from typing import Optional, Tuple

from unlock_via_widget import unlock_via_widget


QRIO_PACKAGE = "me.qrio.smartlock2"
QRIO_MAIN_ACTIVITY = "me.qrio.smartlock2/.presentation.lock.common.LockHomeActivity"
UI_DUMP_PATH = "/sdcard/ui_current.xml"
TMP_CURRENT = "/tmp/ui_current.xml"

# How many UI dumps to try while the app connects to the lock over Bluetooth
MAX_STATE_ATTEMPTS = 5

# Timing configuration (in seconds)
SLEEP_AFTER_WAKE = 0.3          # Wait after waking device
SLEEP_AFTER_SWIPE = 0.3         # Wait after unlock swipe
SLEEP_AFTER_LAUNCH = 1.0        # Wait after launching app
SLEEP_BETWEEN_STATE_CHECKS = 0.5  # Wait between lock state checks


def run_adb_command(args: list, check: bool = True, capture_output: bool = False) -> subprocess.CompletedProcess:
    """
    Run an ADB command with the given arguments.

    Raises:
        RuntimeError: If the adb executable is not on PATH.
        subprocess.CalledProcessError: If adb exits non-zero and check is True.
    """
    cmd = ["adb"] + args
    try:
        return subprocess.run(cmd, check=check, capture_output=capture_output, text=True)
    except FileNotFoundError:
        raise RuntimeError("adb not found in PATH - install Android platform-tools")


def check_device_connected() -> bool:
    """Check if an Android device is connected via ADB."""
    try:
        result = run_adb_command(["devices"], capture_output=True)
    except subprocess.CalledProcessError:
        # If adb itself fails there is no usable device
        return False
    # Look for lines ending with "device" (not "unauthorized" or other states)
    return any(line.strip().endswith("device") for line in result.stdout.splitlines()[1:])


def wake_device(verbose: bool = True):
    """Wake up the device and unlock the screen."""
    if verbose:
        print("📲 Waking up device...")
    run_adb_command(["shell", "input", "keyevent", "KEYCODE_WAKEUP"])
    time.sleep(SLEEP_AFTER_WAKE)

    # Unlock screen (swipe up)
    run_adb_command(["shell", "input", "swipe", "500", "1500", "500", "500"])
    time.sleep(SLEEP_AFTER_SWIPE)


def launch_qrio_app(verbose: bool = True):
    """Launch the Qrio Smart Lock app (reuses existing instance if already running)."""
    if verbose:
        print("🚀 Launching Qrio app...")
    # Use FLAG_ACTIVITY_SINGLE_TOP (0x20000000) to reuse existing instance
    # This prevents creating duplicate instances if the activity is already running
    run_adb_command([
        "shell", "am", "start",
        "-n", QRIO_MAIN_ACTIVITY,
        "-f", "0x20000000"  # FLAG_ACTIVITY_SINGLE_TOP
    ], capture_output=True)
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


def get_button_center(bounds: str) -> Optional[Tuple[int, int]]:
    """Extract center coordinates from bounds string like '[x1,y1][x2,y2]'."""
    match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
    if match:
        x1, y1, x2, y2 = map(int, match.groups())
        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2
        return (center_x, center_y)
    return None


def get_lock_state() -> Optional[str]:
    """
    Get the current lock state from the UI.
    Returns "Locked", "Unlocked", "Connecting", or None if unknown.
    """
    try:
        tree = ET.parse(TMP_CURRENT)
        root = tree.getroot()

        for elem in root.iter():
            text = elem.get('text', '')
            if text in ('Locked', 'Unlocked', 'Connecting'):
                return text
        return None
    except Exception:
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
    except Exception:
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

    except Exception:
        return False


def cleanup():
    """Remove the UI dump from the device (the local copy is kept for inspection)."""
    run_adb_command(
        ["shell", "rm", "-f", UI_DUMP_PATH],
        check=False,
        capture_output=True
    )


def unlock_qrio_lock(verbose: bool = True) -> bool:
    """
    Unlock the Qrio smart lock by tapping its home screen widget.

    This is the same path the RFID daemon uses (see unlock_via_widget.py), so it needs
    no UI dump and takes well under a second.

    Args:
        verbose: If True, prints status messages. If False, runs silently.

    Returns:
        True if the unlock command was sent, False otherwise.

    Raises:
        RuntimeError: If no ADB device is connected.
    """
    if not check_device_connected():
        raise RuntimeError("No ADB device connected")

    return unlock_via_widget(verbose=verbose)


def check_lock_status(verbose: bool = True) -> Optional[str]:
    """
    Report the lock state without touching the widget.

    Launches the app, dumps the UI, dismisses any popup in the way and reads the state
    text. The local UI dump is left at TMP_CURRENT so it can be inspected - useful when
    the state comes back unknown. Never taps the widget, so the lock does not move.

    State is only ever read from a dump this call pulled successfully: any dump left by
    an earlier run is deleted up front, and a failed dump yields None rather than a
    stale answer.

    Args:
        verbose: If True, prints progress messages. If False, runs silently.

    Returns:
        "Locked", "Unlocked", "Connecting", or None if the state is unknown.

    Raises:
        RuntimeError: If no ADB device is connected, or adb is not on PATH.
    """
    if not check_device_connected():
        raise RuntimeError("No ADB device connected")

    try:
        # A dump from an earlier run must never be mistaken for the current state
        Path(TMP_CURRENT).unlink(missing_ok=True)

        wake_device(verbose=verbose)
        launch_qrio_app(verbose=verbose)

        state = None
        for attempt in range(1, MAX_STATE_ATTEMPTS + 1):
            fresh = dump_ui_to_file()

            # A popup can cover the state text, so clear it and dump again
            if fresh and dismiss_popup(verbose=verbose):
                fresh = dump_ui_to_file()

            if fresh:
                state = get_lock_state()
                if state in ('Locked', 'Unlocked'):
                    break
            elif verbose:
                print(f"   ⚠️  UI dump failed (attempt {attempt}/{MAX_STATE_ATTEMPTS})")

            if verbose and fresh:
                print(f"   Still connecting... (attempt {attempt}/{MAX_STATE_ATTEMPTS})")
            time.sleep(SLEEP_BETWEEN_STATE_CHECKS)

        return state

    except subprocess.CalledProcessError as e:
        # Device dropped offline mid-run (a documented failure mode on this setup)
        if verbose:
            print(f"❌ ADB command failed: {e}")
        return None

    finally:
        cleanup()


def main():
    """Main execution flow for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Unlock the Qrio Smart Lock by tapping its home screen widget."
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="report the lock state without unlocking (read-only, does not move the lock)"
    )
    args = parser.parse_args()

    try:
        if args.status:
            state = check_lock_status(verbose=True)
            print(f"🔍 Lock state: {state or 'Unknown'}")
            print(f"📄 UI dump kept at {TMP_CURRENT}")
            sys.exit(0 if state else 1)

        print("🔓 Unlocking Qrio Smart Lock...")
        sys.exit(0 if unlock_qrio_lock(verbose=True) else 1)

    except RuntimeError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
