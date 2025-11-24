# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a utility for automating the unlocking of Qrio Smart Lock via Android Debug Bridge (ADB). The tool interacts with an Android device running the Qrio Smart Lock app (`me.qrio.smartlock2`) to perform automated unlock operations.

## Files

- `unlock_qrio.py` - Main Python script (recommended)
- `unlock_qrio.sh` - Legacy bash script with embedded Python (deprecated)

## Architecture

**Python Script Design**: The functionality is implemented in `unlock_qrio.py` with clean separation of concerns:

1. **Device Communication Layer** (`run_adb_command`): Uses `subprocess` module to execute ADB commands
2. **UI Detection System** (`wait_for_ui_to_settle`): Implements UI stability detection by comparing consecutive `uiautomator` dumps
3. **Dynamic UI Analysis** (`find_unlock_button`): Parses XML UI hierarchy using `xml.etree.ElementTree` to locate the unlock button
4. **Workflow Orchestration** (`main`): Coordinates the unlock sequence with proper error handling and cleanup

**Key Technical Approach**:
- Waits for the Qrio app UI to "settle" by comparing consecutive UI dumps (binary file comparison)
- Requires 2 consecutive stable UI snapshots before proceeding (configurable via `REQUIRED_STABLE`)
- Searches for clickable elements >300px wide/tall in the center screen area (x1 < 300, x2 > 400)
- Falls back to hardcoded coordinates (360, 684) if dynamic button detection fails
- Saves final UI dump to `~/sandbox/playground/ui_final.xml` for inspection
- Uses `finally` block to ensure cleanup of temporary files even on errors

## Prerequisites

- **ADB (Android Debug Bridge)**: Must be installed and available in PATH
- **Python 3**: Required for embedded UI analysis script
- **Android Device**: Must be connected via ADB with USB debugging enabled
- **Qrio Smart Lock App**: Must be installed on the device (`me.qrio.smartlock2`)

## Running the Script

```bash
# Using Python script (recommended)
python3 unlock_qrio.py

# Or make it executable
chmod +x unlock_qrio.py
./unlock_qrio.py
```

## Configuration

Key constants in `unlock_qrio.py` (lines 11-19):

- `QRIO_PACKAGE`: Android package name (`me.qrio.smartlock2`)
- `QRIO_MAIN_ACTIVITY`: Main activity to launch (`me.qrio.smartlock2/.presentation.lock.common.LockHomeActivity`)
- `MAX_ATTEMPTS`: Maximum UI settling detection attempts (default: 10)
- `REQUIRED_STABLE`: Number of consecutive stable UI snapshots needed (default: 2)
- `UI_FINAL_PATH`: Where to save final UI dump (default: `~/sandbox/playground/ui_final.xml`)

## Troubleshooting

- If the script fails to find the unlock button, check the saved UI dump at `~/sandbox/playground/ui_final.xml`
- The script saves temporary UI dumps to `/tmp/ui_current.xml` and `/tmp/ui_previous.xml` during execution (auto-cleaned on exit)
- Default tap coordinates (360, 684) are used as fallback if dynamic detection fails
- The `UI_FINAL_PATH` constant may need adjustment for different user environments

## Development Notes

When modifying `unlock_qrio.py`:

- The `find_unlock_button()` function (lines 118-146) searches for clickable elements >300px wide/tall in the center screen area
- UI settling detection uses binary file comparison via `files_are_identical()` (lines 73-79)
- Sleep timings are tuned for typical Qrio app behavior:
  - 0.5s after device wake/screen unlock
  - 2s after launching app
  - 1s between UI dumps
- All ADB commands use `subprocess.run()` with proper error handling
- The `cleanup()` function ensures temporary files are removed even if script fails
