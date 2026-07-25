"""Tests for unlock_qrio.py delegation/diagnostics and unlock_via_widget.py."""

import subprocess
import pytest

import unlock_qrio
import unlock_via_widget


LOCKED_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node text="" clickable="false" bounds="[0,0][720,1280]">
    <node text="Locked" clickable="false" bounds="[240,600][480,660]" />
  </node>
</hierarchy>"""

POPUP_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node text="Later" clickable="false" bounds="[0,0][720,100]" />
  <node text="Later" clickable="true" bounds="[100,200][300,260]" />
</hierarchy>"""

NO_STATE_XML = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node text="施錠" clickable="false" bounds="[240,600][480,660]" />
</hierarchy>"""


@pytest.fixture
def ui_dump(tmp_path, monkeypatch):
    """Point TMP_CURRENT at a temp file and return a writer for its contents."""
    dump = tmp_path / "ui_current.xml"
    monkeypatch.setattr(unlock_qrio, "TMP_CURRENT", str(dump))

    def write(xml):
        dump.write_text(xml)
        return dump

    return write


class TestUnlockQrioLock:
    """unlock_qrio_lock() must delegate to the widget tap."""

    def test_delegates_to_widget(self, monkeypatch):
        """Unlocking calls unlock_via_widget and returns its result."""
        calls = []

        def fake_widget(verbose=True):
            calls.append(verbose)
            return True

        monkeypatch.setattr(unlock_qrio, "check_device_connected", lambda: True)
        monkeypatch.setattr(unlock_qrio, "unlock_via_widget", fake_widget)

        assert unlock_qrio.unlock_qrio_lock() is True
        assert calls == [True]

    def test_forwards_verbose_false(self, monkeypatch):
        """verbose=False is passed through so daemon/API use stays silent."""
        calls = []

        def fake_widget(verbose=True):
            calls.append(verbose)
            return True

        monkeypatch.setattr(unlock_qrio, "check_device_connected", lambda: True)
        monkeypatch.setattr(unlock_qrio, "unlock_via_widget", fake_widget)

        unlock_qrio.unlock_qrio_lock(verbose=False)
        assert calls == [False]

    def test_propagates_failure(self, monkeypatch):
        """A failed widget tap surfaces as False."""
        monkeypatch.setattr(unlock_qrio, "check_device_connected", lambda: True)
        monkeypatch.setattr(unlock_qrio, "unlock_via_widget", lambda verbose=True: False)

        assert unlock_qrio.unlock_qrio_lock() is False

    def test_raises_without_device(self, monkeypatch):
        """No ADB device is an error, not a silent failure."""
        monkeypatch.setattr(unlock_qrio, "check_device_connected", lambda: False)

        with pytest.raises(RuntimeError, match="No ADB device connected"):
            unlock_qrio.unlock_qrio_lock()


class TestGetLockState:
    """Lock state is read from the pulled UI dump."""

    def test_reads_locked(self, ui_dump):
        """A 'Locked' node is reported as the state."""
        ui_dump(LOCKED_XML)
        assert unlock_qrio.get_lock_state() == "Locked"

    def test_unknown_state_returns_none(self, ui_dump):
        """Unrecognised state text (e.g. localised UI) returns None."""
        ui_dump(NO_STATE_XML)
        assert unlock_qrio.get_lock_state() is None

    def test_missing_dump_returns_none(self, tmp_path, monkeypatch):
        """A missing dump file returns None instead of raising."""
        monkeypatch.setattr(unlock_qrio, "TMP_CURRENT", str(tmp_path / "absent.xml"))
        assert unlock_qrio.get_lock_state() is None


class TestFindPopupButton:
    """Popup dismissal locates clickable buttons by text."""

    def test_returns_center_of_clickable_node(self, ui_dump):
        """The clickable 'Later' node's center is returned."""
        ui_dump(POPUP_XML)
        assert unlock_qrio.find_popup_button("Later") == (200, 230)

    def test_matches_case_insensitively(self, ui_dump):
        """Button text matching ignores case."""
        ui_dump(POPUP_XML)
        assert unlock_qrio.find_popup_button("later") == (200, 230)

    def test_returns_none_when_absent(self, ui_dump):
        """Missing button text returns None."""
        ui_dump(POPUP_XML)
        assert unlock_qrio.find_popup_button("Skip") is None


class TestGetButtonCenter:
    """Bounds parsing."""

    def test_parses_bounds(self):
        """Center is the midpoint of the bounds rectangle."""
        assert unlock_qrio.get_button_center("[100,200][300,260]") == (200, 230)

    def test_rejects_malformed_bounds(self):
        """Unparseable bounds return None."""
        assert unlock_qrio.get_button_center("not-bounds") is None


class TestUnlockViaWidget:
    """The widget tap itself."""

    @pytest.fixture
    def adb_calls(self, monkeypatch):
        """Capture ADB invocations instead of running them."""
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(unlock_via_widget.subprocess, "run", fake_run)
        monkeypatch.setattr(unlock_via_widget.time, "sleep", lambda _: None)
        return calls

    def test_taps_widget_coordinates(self, adb_calls):
        """The final ADB call taps the configured widget position."""
        assert unlock_via_widget.unlock_via_widget(verbose=False) is True
        assert adb_calls[-1] == [
            "adb", "shell", "input", "tap",
            str(unlock_via_widget.WIDGET_X), str(unlock_via_widget.WIDGET_Y)
        ]

    def test_verbose_false_is_silent(self, adb_calls, capsys):
        """Silent mode prints nothing, so daemon callers control their own logging."""
        unlock_via_widget.unlock_via_widget(verbose=False)
        assert capsys.readouterr().out == ""

    def test_verbose_true_reports_progress(self, adb_calls, capsys):
        """Default mode reports what it is doing."""
        unlock_via_widget.unlock_via_widget()
        assert "Tapping widget" in capsys.readouterr().out

    def test_failed_adb_returns_false(self, monkeypatch, capsys):
        """An ADB failure is reported as False."""
        def failing_run(cmd, **kwargs):
            raise subprocess.CalledProcessError(1, cmd, stderr="device offline")

        monkeypatch.setattr(unlock_via_widget.subprocess, "run", failing_run)
        monkeypatch.setattr(unlock_via_widget.time, "sleep", lambda _: None)

        assert unlock_via_widget.unlock_via_widget(verbose=False) is False
        assert capsys.readouterr().out == ""
