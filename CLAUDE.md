# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a utility for automating the unlocking of Qrio Smart Lock via Android Debug Bridge (ADB). The tool interacts with an Android device running the Qrio Smart Lock app (`me.qrio.smartlock2`) to perform automated unlock operations. Includes optional RFID trigger support using Sony RC-S380 NFC reader.

## Files

- `unlock_via_widget.py` - The unlock path: taps the Qrio home screen widget (importable + CLI)
- `unlock_qrio.py` - CLI wrapper around the widget tap, plus read-only `--status` diagnostics
- `rfid_trigger.py` - RFID-triggered unlock daemon for Sony RC-S380
- `notify.py` - ADB-based flash + vibrate notification feedback
- `test_unlock_qrio.py` - Unit tests for unlock_qrio.py and unlock_via_widget.py
- `test_rfid_trigger.py` - Unit tests for rfid_trigger.py
- `requirements.txt` - Production dependencies (nfcpy)
- `requirements-dev.txt` - Development dependencies (pytest)
- `README.md` - User documentation

## Architecture

### Unlock Path (`unlock_via_widget.py`)

The only way the codebase unlocks the lock. Both the daemon and the CLI call `unlock_via_widget(verbose=True)`:

1. `KEYCODE_WAKEUP` to wake the screen
2. `wm dismiss-keyguard` to get past the lock screen
3. `KEYCODE_HOME` twice (handles an open folder or submenu)
4. `input tap 498 359` on the Qrio widget

**Key Technical Approach**:
- No `uiautomator dump` anywhere on this path - that call costs ~3s, which is why unlocking used to take 6-14s and now takes well under a second
- The widget coordinates (`WIDGET_X`/`WIDGET_Y`, lines 14-15) are hardcoded. **If the widget is moved, or the launcher grid/density changes, unlocking breaks silently** - `input tap` always succeeds, so the daemon still reports success
- Only Qrio's **unlock** widget is on the home screen; the lock widget was deliberately never added. Taps are therefore idempotent - a repeat tap cannot lock the door
- Blind by design: it reports success whenever ADB exits 0, and cannot tell whether the door actually opened. Use `unlock_qrio.py --status` to see actual lock state

### CLI + Diagnostics (`unlock_qrio.py`)

1. **Device Communication Layer** (`run_adb_command`): Uses `subprocess` module to execute ADB commands
2. **Public API** (`unlock_qrio_lock(verbose=True)`): Checks ADB connectivity (raises `RuntimeError` if no device), then delegates to `unlock_via_widget()`
3. **Status Diagnostics** (`check_lock_status(verbose=True)`): Launches the app, dumps the UI, dismisses popups, returns `"Locked"`/`"Unlocked"`/`"Connecting"`/`None`. Never taps the widget, so it cannot move the lock
4. **Lock State Reader** (`get_lock_state`): Parses the UI dump with `xml.etree.ElementTree`, matching state text
5. **Popup Handling** (`find_popup_button`, `dismiss_popup`): Finds clickable nodes by text and taps them to clear dialogs covering the state text
6. **CLI Entry Point** (`main`): `argparse` - no flags unlocks, `--status` reports state

**Key Technical Approach**:
- Uses `FLAG_ACTIVITY_SINGLE_TOP` to reuse existing app instance (prevents duplicate activities)
- `--status` deliberately **keeps** the pulled dump at `/tmp/ui_current.xml` and prints its path - when the state comes back `Unknown`, the raw XML is the only way to see why
- `cleanup()` (in a `finally` block) removes only the on-device dump at `/sdcard/ui_current.xml`
- `dismiss_popup()`'s label list is English-only (`Later`, `OK`, `Cancel`, `Close`, `Dismiss`, `Not now`, `Skip`). A localised dialog (e.g. 後で) will not match - verify against a real dump before trusting it

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
- Imports `unlock_via_widget()` (unlock) and `notify.py` helpers (feedback) - no code duplication. It does **not** import `unlock_qrio.py`
- Calls `unlock_via_widget()` with default `verbose=True`, so unlock progress lands in the journal (`journalctl -u qrio-rfid`)
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
chmod +x unlock_qrio.py unlock_via_widget.py rfid_trigger.py
```

## Running the Scripts

### Manual Unlock
```bash
python3 unlock_qrio.py
# or
./unlock_qrio.py

# Same tap, without the ADB connectivity check
./unlock_via_widget.py
```

### Lock Status (read-only, does not move the lock)
```bash
./unlock_qrio.py --status
# 🔍 Lock state: Locked
# 📄 UI dump kept at /tmp/ui_current.xml
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

**Widget coordinates** in `unlock_via_widget.py` (lines 14-15) - the only config the unlock path has:

- `WIDGET_X` / `WIDGET_Y`: `498, 359` - center of the Qrio widget on the primary home screen

Key constants in `unlock_qrio.py` (lines 22-33), all used only by `--status`:

- `QRIO_PACKAGE`: Android package name (`me.qrio.smartlock2`)
- `QRIO_MAIN_ACTIVITY`: Main activity to launch (`me.qrio.smartlock2/.presentation.lock.common.LockHomeActivity`)
- `UI_DUMP_PATH`: On-device dump path (`/sdcard/ui_current.xml`, removed on exit)
- `TMP_CURRENT`: Local dump path (`/tmp/ui_current.xml`, deliberately kept for inspection)
- `MAX_STATE_ATTEMPTS`: Dumps to try while the app connects over Bluetooth (default: 5)

**Timing Configuration** (`--status` only - the unlock path uses fixed 0.1s/0.3s sleeps in `unlock_via_widget.py`):
- `SLEEP_AFTER_WAKE`: 0.3s - Wait after waking device
- `SLEEP_AFTER_SWIPE`: 0.3s - Wait after unlock swipe
- `SLEEP_AFTER_LAUNCH`: 1.0s - Wait after launching app
- `SLEEP_BETWEEN_STATE_CHECKS`: 0.5s - Wait between lock state checks

Timing constants in `rfid_trigger.py`:
- `COOLDOWN_SECONDS`: 5s - Minimum time between unlocks

## Troubleshooting

- **Unlock silently does nothing**: the widget tap landed on empty space. Run `./unlock_qrio.py --status` and check the dump at `/tmp/ui_current.xml` for a `me.qrio.smartlock2` node containing (498, 359); if the widget moved, update `WIDGET_X`/`WIDGET_Y`
- **`--status` reports `Unknown`**: the app was still connecting, or a dialog/localised UI defeated the text matching. Inspect `/tmp/ui_current.xml` - it is left in place for exactly this
- `--status` removes the on-device dump (`/sdcard/ui_current.xml`) but keeps the local copy

## Development Notes

### Modifying Unlock Logic

- **Unlock path**: `unlock_via_widget(verbose=True)` in `unlock_via_widget.py` - change this and both the daemon and the CLI change together
- **Main API**: `unlock_qrio_lock(verbose=True)` in `unlock_qrio.py` - ADB check + delegation; raises `RuntimeError` when no device is connected
- **Diagnostics**: `check_lock_status(verbose=True)` - the only code that still calls `uiautomator dump`
- **Sleep Timings** (`--status` only): `SLEEP_AFTER_WAKE` 0.3s, `SLEEP_AFTER_SWIPE` 0.3s, `SLEEP_AFTER_LAUNCH` 1.0s (reduced from 2.0s due to `FLAG_ACTIVITY_SINGLE_TOP`), `SLEEP_BETWEEN_STATE_CHECKS` 0.5s
- **Error Handling**: All ADB commands use `subprocess.run()` with proper error handling
- **Cleanup**: `cleanup()` runs in a `finally` block and removes the on-device dump only
- **Verbose Mode**: When `verbose=False`, both `unlock_via_widget()` and `check_lock_status()` run silently for daemon/API use

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
# Run all tests (test_rfid_trigger.py needs nfcpy importable)
uv run --with pytest --with nfcpy pytest test_unlock_qrio.py test_rfid_trigger.py -v

# unlock/diagnostics tests only - no hardware, no nfcpy
uv run --with pytest pytest test_unlock_qrio.py -v
```

Note: `rfid_trigger.py` calls `sys.exit(1)` at import when `nfc` is missing, so
`test_rfid_trigger.py` cannot even be collected without nfcpy installed.

### Testing Without Hardware

```python
# Test unlock logic without RFID reader (taps the widget - opens the door)
from unlock_qrio import unlock_qrio_lock
unlock_qrio_lock(verbose=True)

# Read lock state without moving the lock
from unlock_qrio import check_lock_status
check_lock_status(verbose=True)
```

### Common Customizations

- **Different NFC reader**: Modify `clf = nfc.ContactlessFrontend('usb')` in `rfid_trigger.py`
- **Different unlock coordinates**: Change `WIDGET_X`/`WIDGET_Y` (lines 14-15) in `unlock_via_widget.py`
- **Faster/slower `--status`**: Adjust timing constants (lines 29-33) in `unlock_qrio.py`
- **Custom cooldown**: Modify `COOLDOWN_SECONDS` in `rfid_trigger.py`
- **Custom config path**: Use `--config` argument with `rfid_trigger.py`

### Recent Optimizations

1. **Widget-based unlocking** (the big one, #7): replaced the launch-app → `uiautomator dump` →
   find-button → tap flow with a single tap on the Qrio home screen widget. Removes the ~3s-per-dump
   bottleneck entirely, taking unlock from 6-14s to well under a second. `unlock_qrio.py` now
   delegates to the same function, so manual runs exercise the daemon's actual path
   - Trade-off: the tap is blind and the coordinates are hardcoded (see `unlock_via_widget.py`)

2. **Signal Handling** (Ctrl+C responsiveness):
   - Added `signal.SIGINT` handlers in both `run_daemon()` and `scan_mode()`
   - Used `terminate` callback in `clf.connect()` to check stop flag
   - Allows graceful shutdown even during blocking NFC reads

3. **FeliCa/Mobile Suica Support**:
   - Added multi-protocol polling for both NFC and FeliCa
   - Implemented smart ID selection that prefers stable FeliCa IDm
   - Enables Android phones with Mobile Suica to work as unlock credentials
   - Physical NFC cards and FeliCa cards both supported simultaneously

### Performance Profiling Baseline (2024-12, historical)

**These numbers describe the dump-based unlock path, which no longer exists.** They are kept because
they explain why the widget approach was adopted, and they still apply to `--status`, which is the
only remaining caller of `uiautomator dump`.

**Test Environment:**
- Device: Android phone connected via ADB over USB
- Lock: Qrio Smart Lock connected via Bluetooth

**Step Timing:**

| Step | Time | Notes |
|------|------|-------|
| Wake device | ~0.6s | KEYCODE_WAKEUP + swipe + sleeps |
| Launch app | ~1.3s | am start + 1.0s sleep |
| UI dump | ~3.0s | `uiautomator dump` - **main bottleneck** |
| Popup dismiss | ~0.5s | If popup present |
| Find button | <0.1s | XML parsing |
| Tap button | ~0.2s | input tap command |

**End-to-End Timing (old dump-based unlock):**

| Scenario | Time | UI Dumps |
|----------|------|----------|
| Warm start (app connected) | ~6-7s | 1 |
| Cold start (no popup) | ~9-10s | 2 |
| Cold start (with popup) | ~13-14s | 3 |

Current unlock (widget tap) is ~0.6s: four ADB calls plus 0.6s of fixed sleeps, no dump, no app launch.

**Key Bottleneck (still true for `--status`):**
- `adb shell uiautomator dump` takes ~3 seconds per call
- This is an Android/hardware limitation, not easily optimizable
- Screenshot (`screencap`) is faster (~1-1.5s) but can't extract text
