#!/usr/bin/env python3
"""
RFID-triggered unlock for Qrio Smart Lock.
Uses Sony RC-S380 NFC reader to detect authorized cards and trigger unlock.
"""

import sys
import time
import json
import signal
import syslog
import threading
from pathlib import Path
from typing import Set, Optional
from datetime import datetime
import argparse

try:
    import nfc
except ImportError:
    print("❌ Error: nfcpy library not installed.")
    print("Install it with: pip install nfcpy")
    sys.exit(1)

from unlock_qrio import unlock_qrio_lock


# Configuration
CONFIG_FILE = Path.home() / ".config/qrio/authorized_cards.json"
COOLDOWN_SECONDS = 5  # Prevent rapid repeated unlocks


class AuthorizedCards:
    """Manages the list of authorized NFC card IDs."""

    def __init__(self, config_file: Path):
        self.config_file = config_file
        self.cards: Set[str] = set()
        self.load()

    def load(self):
        """Load authorized card IDs from config file."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    self.cards = set(data.get('authorized_cards', []))
                print(f"✅ Loaded {len(self.cards)} authorized card(s)")
            except Exception as e:
                print(f"⚠️  Warning: Could not load config: {e}")
                self.cards = set()
        else:
            print(f"ℹ️  No config file found at {self.config_file}")
            print("   Create one or use --add-card to authorize cards")

    def save(self):
        """Save authorized card IDs to config file."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, 'w') as f:
            json.dump({'authorized_cards': list(self.cards)}, f, indent=2)
        print(f"💾 Saved {len(self.cards)} authorized card(s)")

    def add(self, card_id: str):
        """Add a card ID to the authorized list."""
        self.cards.add(card_id)
        self.save()
        print(f"✅ Added card: {card_id}")

    def remove(self, card_id: str):
        """Remove a card ID from the authorized list."""
        if card_id in self.cards:
            self.cards.remove(card_id)
            self.save()
            print(f"✅ Removed card: {card_id}")
        else:
            print(f"⚠️  Card not found: {card_id}")

    def is_authorized(self, card_id: str) -> bool:
        """Check if a card ID is authorized."""
        return card_id in self.cards

    def list_cards(self):
        """Print all authorized cards."""
        if self.cards:
            print(f"\nAuthorized cards ({len(self.cards)}):")
            for card_id in sorted(self.cards):
                print(f"  - {card_id}")
        else:
            print("No authorized cards.")


def card_id_to_string(tag) -> str:
    """Convert NFC tag to a readable string ID."""
    # For FeliCa cards (like Suica), use IDm instead of identifier
    # IDm is stable for FeliCa cards, while identifier may change
    if hasattr(tag, 'idm') and tag.idm:
        return tag.idm.hex().upper()
    # For other tags, use the tag identifier
    return tag.identifier.hex().upper()


def scan_card(clf) -> Optional[str]:
    """
    Scan for an NFC card and return its ID.

    Args:
        clf: The NFC reader instance.

    Returns:
        Card ID as a hex string, or None if no card detected.
    """
    tag = clf.connect(rdwr={'on-connect': lambda tag: False})  # Just detect, don't hold
    if tag:
        return card_id_to_string(tag)
    return None


def connect_to_reader():
    """
    Connect to the NFC reader.
    Returns ContactlessFrontend instance or None on failure.
    """
    try:
        clf = nfc.ContactlessFrontend('usb')
        print(f"✅ Connected to NFC reader: {clf.device}")
        syslog.syslog(syslog.LOG_INFO, f"Connected to NFC reader: {clf.device}")
        return clf
    except Exception as e:
        error_msg = f"Could not connect to NFC reader: {e}"
        print(f"❌ Error: {error_msg}")
        syslog.syslog(syslog.LOG_ERR, error_msg)
        return None


def run_daemon(auth_cards: AuthorizedCards):
    """
    Run the RFID trigger daemon.
    Continuously monitors for NFC cards and triggers unlock for authorized ones.
    Handles IOError from clf.connect() by reconnecting.
    """
    # Initialize syslog
    syslog.openlog('qrio-rfid', syslog.LOG_PID, syslog.LOG_DAEMON)
    syslog.syslog(syslog.LOG_INFO, "Qrio RFID Trigger Daemon started")

    print("🔓 Qrio RFID Trigger Daemon")
    print("=" * 52)
    print(f"Monitoring for NFC cards (cooldown: {COOLDOWN_SECONDS}s)...")
    print("Press Ctrl+C to stop\n")

    last_unlock_time = 0
    stop_flag = {'stop': False}

    def signal_handler(sig, frame):
        """Handle Ctrl+C gracefully."""
        stop_flag['stop'] = True

    signal.signal(signal.SIGINT, signal_handler)

    # Initial connection with retry logic to prevent systemd restart loop
    INITIAL_RETRY_DELAY = 10  # seconds between retries
    clf = None
    retry_count = 0
    while not stop_flag['stop'] and not clf:
        clf = connect_to_reader()
        if not clf:
            retry_count += 1
            if retry_count == 1:
                print("\nTroubleshooting:")
                print("  1. Make sure the Sony RC-S380 is connected via USB")
                print("  2. Check USB permissions (you may need to run as root or add udev rules)")
                print("  3. Run 'python3 -m nfc' to test the connection")
            print(f"\n⏳ Retrying in {INITIAL_RETRY_DELAY}s... (attempt {retry_count})")
            syslog.syslog(syslog.LOG_WARNING, f"Initial connection failed, retrying in {INITIAL_RETRY_DELAY}s (attempt {retry_count})")
            time.sleep(INITIAL_RETRY_DELAY)

    if stop_flag['stop']:
        print("\n👋 Stopped during initial connection")
        syslog.syslog(syslog.LOG_INFO, "Daemon stopped during initial connection")
        return

    print()  # Blank line after connection message
    last_activity = [time.time()]  # Reset by terminate_callback or when clf.connect() returns
    WATCHDOG_TIMEOUT = 10  # Trigger if no activity for 10s while in clf.connect()
    in_connect = [False]  # True while inside clf.connect()
    needs_reconnect = [False]  # Flag to signal watchdog triggered reconnect

    def terminate_callback():
        """Called by nfcpy between polling iterations."""
        last_activity[0] = time.time()  # Reset watchdog timer
        return stop_flag['stop']

    def watchdog():
        """
        Watchdog thread that monitors clf.connect() for stuck state.
        Triggers only if terminate_callback stops being called (no activity for 10s).
        """
        while not stop_flag['stop']:
            time.sleep(1)
            if in_connect[0]:
                elapsed = time.time() - last_activity[0]
                if elapsed > WATCHDOG_TIMEOUT:
                    print(f"⚠️  Watchdog: no activity for {int(elapsed)}s, forcing reconnect...")
                    syslog.syslog(syslog.LOG_WARNING, f"Watchdog triggered: no activity for {int(elapsed)}s")
                    needs_reconnect[0] = True
                    try:
                        clf.close()  # This should cause clf.connect() to return with IOError
                    except Exception:
                        pass
                    # Keep watchdog running

    watchdog_thread = threading.Thread(target=watchdog, daemon=True)
    watchdog_thread.start()

    try:
        while not stop_flag['stop']:
            # Check if watchdog triggered reconnect
            if needs_reconnect[0]:
                needs_reconnect[0] = False
                clf = connect_to_reader()
                if not clf:
                    print("❌ Reconnection failed, retrying in 5s...")
                    time.sleep(5)
                    clf = connect_to_reader()
                    if not clf:
                        print("❌ Reconnection failed, exiting")
                        break
                print()

            # Poll for NFC cards
            last_activity[0] = time.time()
            in_connect[0] = True
            tag = clf.connect(rdwr={
                'targets': ['212F', '424F', '106A', '106B'],
                'on-connect': lambda tag: False
            }, terminate=terminate_callback)
            in_connect[0] = False

            # Handle IOError (returns False)
            if tag is False:
                print("⚠️  IOError detected - reconnecting to NFC reader...")
                syslog.syslog(syslog.LOG_WARNING, "IOError from clf.connect(), attempting reconnection")
                try:
                    clf.close()
                except Exception:
                    pass
                time.sleep(1)  # Brief delay before reconnect
                clf = connect_to_reader()
                if not clf:
                    print("❌ Reconnection failed, retrying in 5s...")
                    syslog.syslog(syslog.LOG_ERR, "Reconnection failed, retrying in 5s")
                    time.sleep(5)
                    clf = connect_to_reader()
                    if not clf:
                        print("❌ Reconnection failed again, exiting")
                        syslog.syslog(syslog.LOG_ERR, "Reconnection failed after retry, exiting")
                        break
                print()  # Blank line after reconnection
                continue

            if tag:
                card_id = card_id_to_string(tag)
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                if auth_cards.is_authorized(card_id):
                    # Check cooldown
                    current_time = time.time()
                    if current_time - last_unlock_time >= COOLDOWN_SECONDS:
                        print(f"[{timestamp}] ✅ Authorized card: {card_id}")
                        print("🔓 Triggering unlock...")
                        syslog.syslog(syslog.LOG_INFO, f"Authorized card detected: {card_id}")

                        try:
                            success = unlock_qrio_lock(verbose=False)
                            if success:
                                print("✅ Unlock successful!\n")
                                syslog.syslog(syslog.LOG_INFO, f"Unlock successful for card: {card_id}")
                                last_unlock_time = current_time
                            else:
                                print("❌ Unlock failed!\n")
                                syslog.syslog(syslog.LOG_WARNING, f"Unlock failed for card: {card_id}")
                        except Exception as e:
                            error_msg = f"Error during unlock for card {card_id}: {e}"
                            print(f"❌ Error during unlock: {e}\n")
                            syslog.syslog(syslog.LOG_ERR, error_msg)
                    else:
                        remaining = int(COOLDOWN_SECONDS - (current_time - last_unlock_time))
                        print(f"[{timestamp}] ⏳ Card detected but in cooldown ({remaining}s remaining)")
                        syslog.syslog(syslog.LOG_INFO, f"Authorized card in cooldown: {card_id} ({remaining}s remaining)")
                else:
                    print(f"[{timestamp}] ⚠️  Unauthorized card: {card_id}")
                    print(f"   Use '--add-card {card_id}' to authorize\n")
                    syslog.syslog(syslog.LOG_WARNING, f"Unauthorized card detected: {card_id}")

            time.sleep(0.1)  # Small delay to prevent CPU spinning

    except KeyboardInterrupt:
        pass
    finally:
        if stop_flag['stop']:
            print("\n\n👋 Daemon stopped")
            syslog.syslog(syslog.LOG_INFO, "Qrio RFID Trigger Daemon stopped")
        if clf:
            try:
                clf.close()
            except Exception:
                pass
        syslog.closelog()


def scan_mode():
    """Scan and display card IDs without triggering unlock."""
    print("🔍 NFC Card Scanner")
    print("=" * 52)
    print("Place a card on the reader to see its ID")
    print("Press Ctrl+C to stop\n")

    stop_flag = {'stop': False}

    def signal_handler(sig, frame):
        """Handle Ctrl+C gracefully."""
        stop_flag['stop'] = True

    signal.signal(signal.SIGINT, signal_handler)

    try:
        clf = nfc.ContactlessFrontend('usb')
        print(f"✅ Connected to NFC reader: {clf.device}\n")
    except Exception as e:
        print(f"❌ Error: Could not connect to NFC reader: {e}")
        sys.exit(1)

    try:
        print("Waiting for NFC cards...\n")
        last_card_id = None

        while not stop_flag['stop']:
            # Poll for all NFC types simultaneously
            # The card_id_to_string() function will prefer FeliCa IDm when available
            tag = clf.connect(rdwr={
                'targets': ['212F', '424F', '106A', '106B'],
                'on-connect': lambda tag: False
            }, terminate=lambda: stop_flag['stop'])

            if tag:
                card_id = card_id_to_string(tag)

                # Only print if it's a different card (prevents spam from same card)
                if card_id != last_card_id:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    print(f"[{timestamp}] Card detected: {card_id}")
                    print(f"   Type: {tag.type}")

                    # Debug: Show all available tag attributes
                    print(f"   Identifier (UID): {tag.identifier.hex().upper()}")

                    # FeliCa specific data (for Suica, etc.)
                    if hasattr(tag, 'idm') and tag.idm:
                        print(f"   IDm (FeliCa stable ID): {tag.idm.hex().upper()}")
                        print(f"   → Using IDm as card ID (stable)")
                    else:
                        print(f"   → Using UID as card ID (may be random)")

                    if hasattr(tag, 'pmm') and tag.pmm:
                        print(f"   PMM: {tag.pmm.hex().upper()}")
                    if hasattr(tag, 'sys') and tag.sys:
                        print(f"   System Code: {tag.sys}")

                    # NDEF data
                    if hasattr(tag, 'ndef'):
                        print(f"   NDEF: {tag.ndef}")

                    print(f"   To authorize: ./rfid_trigger.py --add-card {card_id}\n")
                    last_card_id = card_id
            else:
                # No card detected, clear the last card
                last_card_id = None

            time.sleep(0.1)

    except KeyboardInterrupt:
        pass
    finally:
        if stop_flag['stop']:
            print("\n\n👋 Scanner stopped")
        clf.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="RFID-triggered unlock for Qrio Smart Lock (Sony RC-S380)"
    )
    parser.add_argument(
        '--daemon',
        action='store_true',
        help='Run as daemon to monitor for authorized cards'
    )
    parser.add_argument(
        '--scan',
        action='store_true',
        help='Scan mode: display card IDs without triggering unlock'
    )
    parser.add_argument(
        '--add-card',
        metavar='CARD_ID',
        help='Add a card ID to the authorized list'
    )
    parser.add_argument(
        '--remove-card',
        metavar='CARD_ID',
        help='Remove a card ID from the authorized list'
    )
    parser.add_argument(
        '--list-cards',
        action='store_true',
        help='List all authorized cards'
    )
    parser.add_argument(
        '--config',
        type=Path,
        default=CONFIG_FILE,
        help=f'Config file path (default: {CONFIG_FILE})'
    )

    args = parser.parse_args()

    # Load authorized cards
    auth_cards = AuthorizedCards(args.config)

    # Handle card management commands
    if args.add_card:
        auth_cards.add(args.add_card.upper())
        return

    if args.remove_card:
        auth_cards.remove(args.remove_card.upper())
        return

    if args.list_cards:
        auth_cards.list_cards()
        return

    # Run scan mode
    if args.scan:
        scan_mode()
        return

    # Run daemon mode
    if args.daemon:
        run_daemon(auth_cards)
        return

    # No command specified, show help
    parser.print_help()


if __name__ == "__main__":
    main()
