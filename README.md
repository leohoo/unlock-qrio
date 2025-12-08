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

   # Or with a name for easier identification
   ./rfid_trigger.py --add-card CARD_ID_HERE --name "Wei's Phone"
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

6. **Update a card's name:**
   ```bash
   # Re-add with new name to update
   ./rfid_trigger.py --add-card CARD_ID_HERE --name "New Name"
   ```

### Configuration

Authorized cards are stored in: `~/.config/qrio/authorized_cards.json`

You can also specify a custom config file:
```bash
./rfid_trigger.py --config /path/to/config.json --daemon
```

### Running as a Service (Systemd)

To run the RFID trigger daemon automatically on system startup, create a systemd service.

#### Option 1: Using Virtual Environment (Recommended)

If you're using `uv` or `venv`, use the Python interpreter from your virtual environment:

**Create service file** (`/etc/systemd/system/qrio-rfid.service`):
```ini
[Unit]
Description=Qrio RFID Trigger Daemon
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/unlock-qrio
# Use the Python from your virtual environment
ExecStart=/home/YOUR_USERNAME/unlock-qrio/.venv/bin/python3 /home/YOUR_USERNAME/unlock-qrio/rfid_trigger.py --daemon
Restart=always
RestartSec=10

# Optional: Set up proper logging
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Setup steps:**
```bash
# 1. Create virtual environment (if not already done)
cd /home/YOUR_USERNAME/unlock-qrio
python3 -m venv .venv
# or with uv:
# uv venv

# 2. Install dependencies in venv
source .venv/bin/activate
pip install -r requirements.txt
# or with uv:
# uv pip install -r requirements.txt
deactivate

# 3. Create the service file
sudo nano /etc/systemd/system/qrio-rfid.service
# (paste the content above, update YOUR_USERNAME)

# 4. Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable qrio-rfid
sudo systemctl start qrio-rfid

# 5. Check status
sudo systemctl status qrio-rfid

# 6. View logs
sudo journalctl -u qrio-rfid -f
```

#### Option 2: Using System Python

If you installed dependencies system-wide:

```ini
[Unit]
Description=Qrio RFID Trigger Daemon
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/unlock-qrio
ExecStart=/usr/bin/python3 /home/YOUR_USERNAME/unlock-qrio/rfid_trigger.py --daemon
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### Useful Commands

```bash
# Start service
sudo systemctl start qrio-rfid

# Stop service
sudo systemctl stop qrio-rfid

# Restart service
sudo systemctl restart qrio-rfid

# Check status
sudo systemctl status qrio-rfid

# View logs (live)
sudo journalctl -u qrio-rfid -f

# View recent logs
sudo journalctl -u qrio-rfid -n 50

# Disable autostart
sudo systemctl disable qrio-rfid
```

#### Viewing Logs

The daemon logs all events to syslog, whether running as a service or manually.

**When running as a systemd service:**
```bash
# View systemd service logs (includes both console and syslog output)
sudo journalctl -u qrio-rfid -f

# View only syslog entries
sudo tail -f /var/log/syslog | grep qrio-rfid
```

**When running manually** (e.g., `./rfid_trigger.py --daemon`):
```bash
# View syslog in real-time (in another terminal)
sudo tail -f /var/log/syslog | grep qrio-rfid

# View recent syslog entries
sudo grep qrio-rfid /var/log/syslog | tail -20
```

Note: Console output appears in your terminal when running manually, **and** simultaneously logs to syslog.

**Events logged to syslog:**
- Daemon start/stop
- NFC reader connection
- Authorized card detection (with card ID)
- Unauthorized card detection (with card ID)
- Unlock success/failure
- Cooldown events
- Errors and warnings

**Example syslog output:**
```
Nov 24 10:30:15 raspberrypi qrio-rfid[1234]: Qrio RFID Trigger Daemon started
Nov 24 10:30:15 raspberrypi qrio-rfid[1234]: Connected to NFC reader: usb:054c:06c3
Nov 24 10:35:22 raspberrypi qrio-rfid[1234]: Authorized card detected: 01234567890ABCDEF
Nov 24 10:35:23 raspberrypi qrio-rfid[1234]: Unlock successful for card: 01234567890ABCDEF
Nov 24 10:35:28 raspberrypi qrio-rfid[1234]: Authorized card in cooldown: 01234567890ABCDEF (2s remaining)
Nov 24 10:40:10 raspberrypi qrio-rfid[1234]: Unauthorized card detected: FEDCBA0987654321
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

### Linux/Raspberry Pi USB Permissions

If you get `[Errno 19] No such device` error, you need to set up USB permissions.

**Quick test (run as root):**
```bash
sudo python3 rfid_trigger.py --scan
```

**Permanent fix (recommended):**

1. Copy the included udev rules file:
   ```bash
   sudo cp 99-nfc-rc-s380.rules /etc/udev/rules.d/
   ```

2. Add your user to the `plugdev` group:
   ```bash
   sudo usermod -a -G plugdev $USER
   ```

3. Reload udev rules:
   ```bash
   sudo udevadm control --reload-rules
   sudo udevadm trigger
   ```

4. **Reboot or replug the USB device** for changes to take effect

5. Test without sudo:
   ```bash
   python3 rfid_trigger.py --scan
   ```

**Manual setup (if you don't have the rules file):**
```bash
# Create file: /etc/udev/rules.d/99-nfc-rc-s380.rules
sudo bash -c 'cat > /etc/udev/rules.d/99-nfc-rc-s380.rules << EOF
# Sony RC-S380 NFC Reader
SUBSYSTEM=="usb", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="06c3", MODE="0666", GROUP="plugdev"
EOF'

# Then follow steps 2-5 above
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

### Setup

```bash
# Install production dependencies only
pip install -r requirements.txt

# Install development dependencies (includes pytest)
pip install -r requirements-dev.txt
```

### Running Tests

```bash
pytest test_rfid_trigger.py -v
```

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
├── test_rfid_trigger.py    # Tests for rfid_trigger.py
├── requirements.txt        # Production dependencies
├── requirements-dev.txt    # Development dependencies
├── README.md               # This file
├── CLAUDE.md               # Development guide
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
