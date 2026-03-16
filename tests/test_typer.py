"""Tests for text insertion logic."""

import subprocess
from unittest.mock import patch, MagicMock, call

import pytest
from whisper_voice_typing.typer import type_text


class TestTypeTextLinux:
    @patch("whisper_voice_typing.typer.is_macos", return_value=False)
    @patch("whisper_voice_typing.typer.subprocess.run")
    def test_calls_xdotool(self, mock_run, _):
        mock_run.return_value = MagicMock(returncode=0)
        assert type_text("hello") is True
        mock_run.assert_called_once_with(
            ["xdotool", "type", "--delay", "1", "--clearmodifiers", "--", "hello"],
            check=True, timeout=10,
        )

    @patch("whisper_voice_typing.typer.is_macos", return_value=False)
    @patch("whisper_voice_typing.typer.subprocess.run", side_effect=subprocess.CalledProcessError(1, "xdotool"))
    def test_xdotool_failure(self, mock_run, _):
        assert type_text("hello") is False


class TestTypeTextMacOSSubprocess:
    @patch("whisper_voice_typing.typer.is_macos", return_value=True)
    @patch("whisper_voice_typing.typer._HAS_PYOBJC", False)
    @patch("whisper_voice_typing.typer.subprocess.run")
    def test_pbcopy_osascript_flow(self, mock_run, _):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=b"old"),  # pbpaste
            MagicMock(returncode=0),                   # pbcopy set
            MagicMock(returncode=0, stderr=""),         # osascript
            MagicMock(returncode=0),                   # pbcopy restore
        ]
        assert type_text("hello") is True

    @patch("whisper_voice_typing.typer.is_macos", return_value=True)
    @patch("whisper_voice_typing.typer._HAS_PYOBJC", False)
    @patch("whisper_voice_typing.typer.subprocess.run")
    def test_accessibility_denied(self, mock_run, _):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=b"old"),
            MagicMock(returncode=0),
            MagicMock(returncode=1, stderr="not allowed assistive"),
            MagicMock(returncode=0),
        ]
        assert type_text("hello") is False

    @patch("whisper_voice_typing.typer.is_macos", return_value=True)
    @patch("whisper_voice_typing.typer._HAS_PYOBJC", False)
    @patch("whisper_voice_typing.typer.subprocess.run")
    def test_osascript_other_error(self, mock_run, _):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=b"old"),
            MagicMock(returncode=0),
            MagicMock(returncode=1, stderr="some other error"),
            MagicMock(returncode=0),
        ]
        assert type_text("hello") is False


class TestClipboardRestoration:
    @patch("whisper_voice_typing.typer.is_macos", return_value=True)
    @patch("whisper_voice_typing.typer._HAS_PYOBJC", False)
    @patch("whisper_voice_typing.typer.subprocess.run")
    def test_clipboard_restored_after_paste(self, mock_run, _):
        calls = []
        def track(*args, **kw):
            calls.append(args[0])
            if args[0][0] == "pbpaste": return MagicMock(returncode=0, stdout=b"saved")
            if args[0][0] == "osascript": return MagicMock(returncode=0, stderr="")
            return MagicMock(returncode=0)
        mock_run.side_effect = track
        type_text("new text")
        assert len([c for c in calls if c[0] == "pbcopy"]) == 2

    @patch("whisper_voice_typing.typer.is_macos", return_value=True)
    @patch("whisper_voice_typing.typer._HAS_PYOBJC", False)
    @patch("whisper_voice_typing.typer.subprocess.run")
    def test_no_restore_if_pbpaste_fails(self, mock_run, _):
        calls = []
        def track(*args, **kw):
            calls.append(args[0])
            if args[0][0] == "pbpaste": return MagicMock(returncode=1, stdout=b"")
            if args[0][0] == "osascript": return MagicMock(returncode=0, stderr="")
            return MagicMock(returncode=0)
        mock_run.side_effect = track
        type_text("new text")
        assert len([c for c in calls if c[0] == "pbcopy"]) == 1


class TestNativeMacOS:
    @patch("whisper_voice_typing.typer.is_macos", return_value=True)
    @patch("whisper_voice_typing.typer._HAS_PYOBJC", True)
    @patch("whisper_voice_typing.typer._send_cmd_v", return_value=True)
    @patch("whisper_voice_typing.typer.NSPasteboard")
    def test_native_paste_flow(self, mock_pb_cls, mock_cmd_v, _):
        pb = MagicMock()
        mock_pb_cls.generalPasteboard.return_value = pb
        pb.stringForType_.return_value = "old clipboard"
        pb.changeCount.side_effect = [42, 42]  # unchanged = restore

        assert type_text("hello") is True
        pb.clearContents.assert_called()
        pb.setString_forType_.assert_called()

    @patch("whisper_voice_typing.typer.is_macos", return_value=True)
    @patch("whisper_voice_typing.typer._HAS_PYOBJC", True)
    @patch("whisper_voice_typing.typer._send_cmd_v", return_value=False)
    @patch("whisper_voice_typing.typer.NSPasteboard")
    def test_native_cmd_v_failure(self, mock_pb_cls, mock_cmd_v, _):
        pb = MagicMock()
        mock_pb_cls.generalPasteboard.return_value = pb
        pb.stringForType_.return_value = "old"
        assert type_text("hello") is False

    @patch("whisper_voice_typing.typer.is_macos", return_value=True)
    @patch("whisper_voice_typing.typer._HAS_PYOBJC", True)
    @patch("whisper_voice_typing.typer._send_cmd_v", return_value=True)
    @patch("whisper_voice_typing.typer.NSPasteboard")
    def test_no_restore_if_clipboard_changed(self, mock_pb_cls, mock_cmd_v, _):
        pb = MagicMock()
        mock_pb_cls.generalPasteboard.return_value = pb
        pb.stringForType_.return_value = "old"
        pb.changeCount.side_effect = [42, 43]  # changed = don't restore

        type_text("hello")
        # clearContents called once for set, NOT again for restore
        assert pb.clearContents.call_count == 1

    @patch("whisper_voice_typing.typer.is_macos", return_value=True)
    @patch("whisper_voice_typing.typer._HAS_PYOBJC", True)
    @patch("whisper_voice_typing.typer._send_cmd_v", return_value=True)
    @patch("whisper_voice_typing.typer.NSPasteboard")
    def test_no_restore_if_old_was_none(self, mock_pb_cls, mock_cmd_v, _):
        pb = MagicMock()
        mock_pb_cls.generalPasteboard.return_value = pb
        pb.stringForType_.return_value = None  # empty clipboard
        pb.changeCount.side_effect = [42, 42]

        type_text("hello")
        assert pb.clearContents.call_count == 1  # no restore


class TestSendCmdV:
    @patch("whisper_voice_typing.typer.CGEventPost")
    @patch("whisper_voice_typing.typer.CGEventSetFlags")
    @patch("whisper_voice_typing.typer.CGEventCreateKeyboardEvent")
    def test_sends_key_down_and_up(self, mock_create, mock_flags, mock_post):
        mock_create.side_effect = [MagicMock(), MagicMock()]
        from whisper_voice_typing.typer import _send_cmd_v
        assert _send_cmd_v() is True
        assert mock_create.call_count == 2
        assert mock_post.call_count == 2

    @patch("whisper_voice_typing.typer.CGEventCreateKeyboardEvent", return_value=None)
    def test_returns_false_on_null_event(self, _):
        from whisper_voice_typing.typer import _send_cmd_v
        assert _send_cmd_v() is False
