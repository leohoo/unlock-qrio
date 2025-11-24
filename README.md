# Qrio Smart Lock Automation

Automate unlocking of Qrio Smart Lock via Android Debug Bridge (ADB), with optional RFID card trigger support using Sony RC-S380 NFC reader.

## Features

- **Automated Unlock**: Unlock Qrio Smart Lock via ADB with UI settling detection
- **RFID Trigger**: Trigger unlock by scanning authorized NFC cards (Sony RC-S380)
- **Multi-Protocol Support**: Works with both NFC (Type4Tag) and FeliCa (Type3Tag) cards
- **Mobile Suica Support**: Use your Android phone with Mobile Suica as a stable unlock credential
- **Smart Detection**: Waits for app UI to stabilize before attempting unlock
- **Dynamic Button Finding**: Automatically locates unlock button in UI hierarchy
- **Card Authorization**: Manage whitelist of authorized NFC cards and phone IDs

## Prerequisites

- **Python 3.7+**
- **ADB (Android Debug Bridge)**: Must be installed and in PATH
- **Android Device**: Connected via ADB with USB debugging enabled
- **Qrio Smart Lock App**: Installed on the device (`me.qrio.smartlock2`)
- **Sony RC-S380 NFC Reader** (optional, for RFID trigger feature)

## Installation

```bash
# Install Python dependencies
pip install -r requirements.txt

# Make scripts executable
chmod +x unlock_qrio.py rfid_trigger.py
```

## Usage

### Manual Unlock

Run the unlock script directly:

```bash
python3 unlock_qrio.py
# or
./unlock_qrio.py
```

### RFID Trigger Setup

1. **Scan a card to get its ID:**
   ```bash
   ./rfid_trigger.py --scan
   ```

2. **Authorize a card:**
   ```bash
   ./rfid_trigger.py --add-card CARD_ID_HERE
   ```

3. **List authorized cards:**
   ```bash
   ./rfid_trigger.py --list-cards
   ```

4. **Run the daemon:**
   ```bash
   ./rfid_trigger.py --daemon
   ```

   The daemon will monitor for NFC cards and automatically unlock when an authorized card is detected.

5. **Remove a card:**
   ```bash
   ./rfid_trigger.py --remove-card CARD_ID_HERE
   ```

### Configuration

Authorized cards are stored in: `~/.config/qrio/authorized_cards.json`

You can also specify a custom config file:
```bash
./rfid_trigger.py --config /path/to/config.json --daemon
```

### Running as a Service

To run the RFID trigger daemon automatically on system startup, you can create a systemd service (Linux) or launchd service (macOS).

**Example systemd service** (`/etc/systemd/system/qrio-rfid.service`):
```ini
[Unit]
Description=Qrio RFID Trigger Daemon
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/path/to/unlock-qrio
ExecStart=/usr/bin/python3 /path/to/unlock-qrio/rfid_trigger.py --daemon
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable qrio-rfid
sudo systemctl start qrio-rfid
```

## How It Works

### Unlock Process

1. Check for connected ADB device
2. Wake up device and unlock screen
3. Launch Qrio app (reuses existing instance if already running)
4. Wait for UI to stabilize (compares consecutive UI dumps)
5. Parse UI hierarchy XML to find unlock button
6. Tap the unlock button
7. Clean up temporary files

### RFID Trigger

1. Connects to Sony RC-S380 NFC reader via USB
2. Continuously monitors for both NFC and FeliCa cards
3. When a card/phone is detected:
   - Polls for FeliCa (Type3Tag) and NFC (Type4Tag) simultaneously
   - For FeliCa cards (e.g., Mobile Suica): uses stable IDm as identifier
   - For regular NFC cards: uses UID as identifier
   - Checks if card/phone ID is in authorized list
   - Applies cooldown to prevent rapid repeated unlocks (5 seconds default)
   - Calls `unlock_qrio_lock()` function
   - Logs the event with timestamp

## Troubleshooting

### ADB Issues

- Ensure device is connected: `adb devices`
- Enable USB debugging on Android device
- Accept USB debugging prompt on device

### NFC Reader Issues

- Test connection: `python3 -m nfc`
- Check USB permissions (may need root or udev rules on Linux)
- Verify device is detected: `lsusb | grep Sony` (should show `054c:06c3`)
- **Ctrl+C not working?** The script uses signal handling to allow graceful shutdown. Press Ctrl+C and wait up to 1 second for the current NFC read operation to complete.

### Mobile Phone NFC Issues

- **Android phones generate random UIDs** for privacy - this is normal
- **Solution for Android**: Use Mobile Suica, Mobile Pasmo, or similar FeliCa apps
  - These apps provide a stable FeliCa IDm that doesn't change
  - Open the app before scanning
  - The script automatically detects and uses the stable IDm
- **Physical NFC cards** always have stable UIDs - recommended for simplicity
- **iPhone NFC** is not supported (Apple restricts background NFC access)

### UI Detection Issues

- Check saved UI dump: `~/sandbox/playground/ui_final.xml`
- Adjust `UI_FINAL_PATH` in `unlock_qrio.py` if needed
- Script falls back to coordinates (360, 684) if button not found

### Linux USB Permissions

Create udev rule for RC-S380:

```bash
# Create file: /etc/udev/rules.d/99-nfc.rules
SUBSYSTEM=="usb", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="06c3", MODE="0666"

# Reload rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

## Configuration Options

### Timing Configuration (`unlock_qrio.py`)

The unlock timing has been optimized for speed while maintaining reliability:

```python
SLEEP_AFTER_WAKE = 0.3      # Wait after waking device (default: 0.3s)
SLEEP_AFTER_SWIPE = 0.3     # Wait after unlock swipe (default: 0.3s)
SLEEP_AFTER_LAUNCH = 1.0    # Wait after launching app (default: 1.0s)
SLEEP_BETWEEN_DUMPS = 0.5   # Wait between UI dumps (default: 0.5s)
```

**Total unlock time: ~2.6 seconds** (from wake to tap)

You can adjust these values if needed:
- Decrease for faster unlocks (may be unstable)
- Increase for slower devices or more reliability

### Other Configuration

Key constants in `unlock_qrio.py`:
- `MAX_ATTEMPTS`: Maximum UI settling detection attempts (default: 10)
- `REQUIRED_STABLE`: Consecutive stable UI snapshots needed (default: 2)
- `UI_FINAL_PATH`: Where to save final UI dump

Key constants in `rfid_trigger.py`:
- `COOLDOWN_SECONDS`: Minimum time between unlocks (default: 5)
- `CONFIG_FILE`: Path to authorized cards config

## Development

### Using as a Library

```python
from unlock_qrio import unlock_qrio_lock

# Unlock with verbose output
unlock_qrio_lock(verbose=True)

# Unlock silently
success = unlock_qrio_lock(verbose=False)
if success:
    print("Unlocked!")
```

### Project Structure

```
unlock-qrio/
├── unlock_qrio.py          # Core unlock logic
├── unlock_qrio.sh          # Legacy bash script (deprecated)
├── rfid_trigger.py         # RFID trigger daemon
├── requirements.txt        # Python dependencies
├── README.md              # This file
├── CLAUDE.md              # Development guide
└── .gitignore
```

## License

This is a personal automation tool. Use at your own risk.

## Security Considerations

- **Physical Security**: Anyone with access to an authorized NFC card can unlock your door
- **Card Authorization**: Keep your authorized cards list secure
- **Network**: Ensure your Android device and computer are on a trusted network
- **ADB**: USB debugging enables powerful device access - keep your device secure

## Credits

- Uses [nfcpy](https://nfcpy.readthedocs.io/) for NFC reader communication
- Designed for Sony RC-S380 (PaSoRi) NFC reader
- Works with Qrio Smart Lock Android app
