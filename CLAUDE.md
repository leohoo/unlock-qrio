# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a utility for automating the unlocking of Qrio Smart Lock via Android Debug Bridge (ADB). The tool interacts with an Android device running the Qrio Smart Lock app (`me.qrio.smartlock2`) to perform automated unlock operations. Includes optional RFID trigger support using Sony RC-S380 NFC reader.

## Files

- `unlock_qrio.py` - Core unlock logic (importable module + CLI)
- `rfid_trigger.py` - RFID-triggered unlock daemon for Sony RC-S380
- `notify.py` - ADB-based flash + vibrate notification feedback
- `test_rfid_trigger.py` - Unit tests for rfid_trigger.py
- `unlock_qrio.sh` - Legacy bash script with embedded Python (deprecated)
- `requirements.txt` - Production dependencies (nfcpy)
- `requirements-dev.txt` - Development dependencies (pytest)
- `README.md` - User documentation

## Architecture

### Core Unlock Module (`unlock_qrio.py`)

Designed as both an importable module and CLI tool:

1. **Device Communication Layer** (`run_adb_command`): Uses `subprocess` module to execute ADB commands
2. **UI Detection System** (`wait_for_ui_to_settle`): Implements UI stability detection by comparing consecutive `uiautomator` dumps
3. **Dynamic UI Analysis** (`find_unlock_button`): Parses XML UI hierarchy using `xml.etree.ElementTree` to locate the unlock button
4. **Public API** (`unlock_qrio_lock(verbose=True)`): Main function for programmatic use
5. **CLI Entry Point** (`main`): Wrapper for command-line usage

**Key Technical Approach**:
- Waits for the Qrio app UI to "settle" by comparing consecutive UI dumps (binary file comparison)
- Requires 2 consecutive stable UI snapshots before proceeding (configurable via `REQUIRED_STABLE`)
- Uses `FLAG_ACTIVITY_SINGLE_TOP` to reuse existing app instance (prevents duplicate activities)
- Searches for clickable elements >300px wide/tall in the center screen area (x1 < 300, x2 > 400)
- Falls back to hardcoded coordinates (360, 684) if dynamic button detection fails
- Saves final UI dump to `~/sandbox/playground/ui_final.xml` for inspection
- Uses `finally` block to ensure cleanup of temporary files even on errors

### RFID Trigger Daemon (`rfid_trigger.py`)

Event-driven daemon for RFID-triggered unlock:

1. **Card Authorization** (`AuthorizedCards`): Manages whitelist of authorized NFC card IDs in JSON config
2. **NFC Reader Interface**: Uses `nfcpy` library to communicate with Sony RC-S380 via USB
3. **Multi-Protocol Support**: Polls for both NFC (Type4Tag) and FeliCa (Type3Tag) simultaneously
   - `'212F', '424F'` = FeliCa at 212/424 kbps (for Mobile Suica, etc.)
   - `'106A', '106B'` = ISO-DEP at 106 kbps (for physical NFC cards)
4. **Smart ID Selection** (`card_id_to_string`): Automatically prefers stable FeliCa IDm over random UID
   - If `tag.idm` exists → use IDm (FeliCa stable identifier)
   - Otherwise → use `tag.identifier` (standard NFC UID)
5. **Event Loop**: Continuously monitors for NFC card/phone presence
6. **Cooldown Mechanism**: Prevents rapid repeated unlocks (5 seconds default)
7. **Card Management**: CLI commands for adding/removing/listing authorized cards
8. **Syslog Integration**: Logs all events to syslog for system monitoring and auditing

**Design Decisions**:
- Imports `unlock_qrio_lock()` function from core module (no code duplication)
- Silent unlock mode (`verbose=False`) for daemon operation
- JSON config stored in `~/.config/qrio/authorized_cards.json`
- Card IDs stored as uppercase hex strings for consistency
- Scan mode (`--scan`) for discovering card IDs without triggering unlock
- Supports Android phones with Mobile Suica/FeliCa apps (stable IDm)
- Uses Python's built-in `syslog` module for system logging
  - Logs to `LOG_DAEMON` facility with program name `qrio-rfid`
  - Includes PID in logs via `LOG_PID` flag
  - Uses appropriate severity levels: `LOG_INFO`, `LOG_WARNING`, `LOG_ERR`
  - All card detection and unlock events are logged for auditing

## Prerequisites

- **ADB (Android Debug Bridge)**: Must be installed and available in PATH
- **Python 3.7+**: Required for type hints and pathlib
- **Android Device**: Must be connected via ADB with USB debugging enabled
- **Qrio Smart Lock App**: Must be installed on the device (`me.qrio.smartlock2`)
- **Sony RC-S380 NFC Reader** (optional): For RFID trigger feature

## Installation

Local development environment is managed using [uv](https://docs.astral.sh/uv/).

```bash
# Install dependencies (creates .venv automatically)
uv sync

# For development (includes pytest)
uv sync --all-extras

# Make scripts executable
chmod +x unlock_qrio.py rfid_trigger.py
```

## Running the Scripts

### Manual Unlock
```bash
python3 unlock_qrio.py
# or
./unlock_qrio.py
```

### RFID Trigger Daemon
```bash
# Scan for card IDs
./rfid_trigger.py --scan

# Authorize a card
./rfid_trigger.py --add-card CARD_ID

# Authorize a card with a name
./rfid_trigger.py --add-card CARD_ID --name "Wei's Phone"

# Run daemon
./rfid_trigger.py --daemon
```

## Configuration

Key constants in `unlock_qrio.py` (lines 17-30):

- `QRIO_PACKAGE`: Android package name (`me.qrio.smartlock2`)
- `QRIO_MAIN_ACTIVITY`: Main activity to launch (`me.qrio.smartlock2/.presentation.lock.common.LockHomeActivity`)
- `MAX_ATTEMPTS`: Maximum UI settling detection attempts (default: 10)
- `REQUIRED_STABLE`: Number of consecutive stable UI snapshots needed (default: 2)
- `UI_FINAL_PATH`: Where to save final UI dump (default: `~/sandbox/playground/ui_final.xml`)

**Timing Configuration** (optimized for speed, ~2.6s total unlock time):
- `SLEEP_AFTER_WAKE`: 0.3s - Wait after waking device
- `SLEEP_AFTER_SWIPE`: 0.3s - Wait after unlock swipe
- `SLEEP_AFTER_LAUNCH`: 1.0s - Wait after launching app
- `SLEEP_BETWEEN_DUMPS`: 0.5s - Wait between UI dumps

Timing constants in `rfid_trigger.py`:
- `COOLDOWN_SECONDS`: 5s - Minimum time between unlocks

## Troubleshooting

- If the script fails to find the unlock button, check the saved UI dump at `~/sandbox/playground/ui_final.xml`
- The script saves temporary UI dumps to `/tmp/ui_current.xml` and `/tmp/ui_previous.xml` during execution (auto-cleaned on exit)
- Default tap coordinates (360, 684) are used as fallback if dynamic detection fails
- The `UI_FINAL_PATH` constant may need adjustment for different user environments

## Development Notes

### Modifying Core Unlock Logic (`unlock_qrio.py`)

- **Main API**: `unlock_qrio_lock(verbose=True)` at line ~201 - this is the primary entry point for imports
- **Button Detection**: `find_unlock_button()` at line ~133 searches for clickable elements >300px wide/tall in center area
- **UI Settling**: `files_are_identical()` at line ~81 uses binary file comparison
- **Sleep Timings**: All timing uses configurable constants (lines 26-30):
  - `SLEEP_AFTER_WAKE` = 0.3s (after device wake)
  - `SLEEP_AFTER_SWIPE` = 0.3s (after screen unlock swipe)
  - `SLEEP_AFTER_LAUNCH` = 1.0s (after launching app, reduced from 2.0s due to `FLAG_ACTIVITY_SINGLE_TOP`)
  - `SLEEP_BETWEEN_DUMPS` = 0.5s (between UI dumps, reduced from 1.0s)
  - Total unlock time: ~2.6 seconds (40% faster than original 4.5s)
- **Error Handling**: All ADB commands use `subprocess.run()` with proper error handling
- **Cleanup**: `cleanup()` function ensures temporary files are removed even if script fails
- **Verbose Mode**: When `verbose=False`, functions run silently for daemon use

### Modifying RFID Trigger (`rfid_trigger.py`)

- **Card Storage**: `AuthorizedCards` class manages JSON config at `~/.config/qrio/authorized_cards.json`
  - Config format: `{"authorized_cards": {"CARD_ID": "Name", ...}}` (dict of card_id → name)
  - Empty string for name if not set; backward compatible with old list format
  - Use `--name` argument with `--add-card` to assign friendly names
  - Names appear in syslog entries and daemon output as `CARD_ID (Name)`
- **Card ID Format**: Always converted to uppercase hex via `card_id_to_string(tag)` at line ~90
  - Prefers FeliCa IDm (`tag.idm`) when available (stable for Mobile Suica)
  - Falls back to standard UID (`tag.identifier`) for regular NFC cards
- **Multi-Protocol Polling**: Lines ~151 and ~222 poll for multiple NFC types:
  ```python
  'targets': ['212F', '424F', '106A', '106B']
  ```
  - `212F/424F` = FeliCa (Type3Tag) at 212/424 kbps
  - `106A/106B` = ISO-DEP (Type4Tag) at 106 kbps
- **Cooldown**: `COOLDOWN_SECONDS = 5` prevents rapid repeated unlocks
- **NFC Library**: Uses `nfcpy.ContactlessFrontend('usb')` to connect to RC-S380
- **Event Loop**: `run_daemon()` continuously polls for cards with 0.1s sleep to prevent CPU spinning
- **Signal Handling**: Uses `signal.SIGINT` handler + `stop_flag` to allow graceful Ctrl+C shutdown
  - The `terminate` callback in `clf.connect()` checks `stop_flag['stop']` to break out of blocking NFC reads
  - This allows Ctrl+C to work even when waiting for NFC cards
- **USB Permissions**: On Linux, may require udev rules for non-root access (see README.md)

### Running Tests

```bash
# Run all tests
uv run pytest test_rfid_trigger.py -v
```

### Testing Without Hardware

```python
# Test unlock logic without RFID reader
from unlock_qrio import unlock_qrio_lock
unlock_qrio_lock(verbose=True)
```

### Common Customizations

- **Different NFC reader**: Modify `clf = nfc.ContactlessFrontend('usb')` in `rfid_trigger.py`
- **Different unlock coordinates**: Change fallback at line ~280 in `unlock_qrio.py`
- **Faster/slower unlock**: Adjust timing constants (lines 26-30) in `unlock_qrio.py`
- **Custom cooldown**: Modify `COOLDOWN_SECONDS` in `rfid_trigger.py`
- **Custom config path**: Use `--config` argument with `rfid_trigger.py`

### Recent Optimizations

1. **Timing Optimization** (40% speed improvement):
   - Reduced app launch wait from 2.0s → 1.0s (safe with `FLAG_ACTIVITY_SINGLE_TOP`)
   - Reduced UI dump interval from 1.0s → 0.5s
   - Reduced wake/swipe delays from 0.5s → 0.3s each

2. **Signal Handling** (Ctrl+C responsiveness):
   - Added `signal.SIGINT` handlers in both `run_daemon()` and `scan_mode()`
   - Used `terminate` callback in `clf.connect()` to check stop flag
   - Allows graceful shutdown even during blocking NFC reads

3. **FeliCa/Mobile Suica Support**:
   - Added multi-protocol polling for both NFC and FeliCa
   - Implemented smart ID selection that prefers stable FeliCa IDm
   - Enables Android phones with Mobile Suica to work as unlock credentials
   - Physical NFC cards and FeliCa cards both supported simultaneously

### Performance Profiling Baseline (2024-12)

**Test Environment:**
- Device: Android phone connected via ADB over USB
- Lock: Qrio Smart Lock connected via Bluetooth

**Unlock Flow Timing:**

| Step | Time | Notes |
|------|------|-------|
| Wake device | ~0.6s | KEYCODE_WAKEUP + swipe + sleeps |
| Launch app | ~1.3s | am start + 1.0s sleep |
| UI dump | ~3.0s | `uiautomator dump` - **main bottleneck** |
| Popup dismiss | ~0.5s | If popup present |
| Find button | <0.1s | XML parsing |
| Tap button | ~0.2s | input tap command |

**End-to-End Timing:**

| Scenario | Time | UI Dumps |
|----------|------|----------|
| Warm start (app connected) | ~6-7s | 1 |
| Cold start (no popup) | ~9-10s | 2 |
| Cold start (with popup) | ~13-14s | 3 |

**Key Bottleneck:**
- `adb shell uiautomator dump` takes ~3 seconds per call
- This is an Android/hardware limitation, not easily optimizable
- Screenshot (`screencap`) is faster (~1-1.5s) but can't extract text

**Optimization Strategies Tried:**
1. Screenshot-based UI settlement: Faster but still needs 1 UI dump for button detection
2. Skip settlement, check state directly: Reduced dumps from 3+ to 1-3
3. Early return if already unlocked: Saves time on repeated unlocks

**Future Optimization Ideas:**
- Use image recognition to detect lock state from screenshot (avoid UI dump)
- Cache button coordinates if UI layout is consistent
- Reduce `SLEEP_AFTER_LAUNCH` if Bluetooth connection is fast
