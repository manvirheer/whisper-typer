"""Tests for text insertion logic."""

import subprocess
from unittest.mock import patch, MagicMock

import pytest

from whisper_voice_typing.typer import type_text


class TestTypeTextLinux:
    """Test the Linux xdotool path."""

    @patch("whisper_voice_typing.typer.is_macos", return_value=False)
    @patch("whisper_voice_typing.typer.subprocess.run")
    def test_calls_xdotool(self, mock_run, mock_platform):
        mock_run.return_value = MagicMock(returncode=0)
        result = type_text("hello")
        assert result is True
        mock_run.assert_called_once_with(
            ["xdotool", "type", "--delay", "1", "--clearmodifiers", "--", "hello"],
            check=True, timeout=10,
        )

    @patch("whisper_voice_typing.typer.is_macos", return_value=False)
    @patch("whisper_voice_typing.typer.subprocess.run")
    def test_xdotool_failure_returns_false(self, mock_run, mock_platform):
        mock_run.side_effect = subprocess.CalledProcessError(1, "xdotool")
        result = type_text("hello")
        assert result is False


class TestTypeTextMacOSSubprocess:
    """Test the macOS subprocess fallback path."""

    @patch("whisper_voice_typing.typer.is_macos", return_value=True)
    @patch("whisper_voice_typing.typer._HAS_PYOBJC", False)
    @patch("whisper_voice_typing.typer.subprocess.run")
    def test_uses_pbcopy_osascript(self, mock_run, mock_platform):
        # pbpaste returns old clipboard
        # pbcopy succeeds
        # osascript succeeds
        # pbcopy restores
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=b"old"),  # pbpaste
            MagicMock(returncode=0),  # pbcopy (set text)
            MagicMock(returncode=0, stderr=""),  # osascript
            MagicMock(returncode=0),  # pbcopy (restore)
        ]
        result = type_text("hello")
        assert result is True

    @patch("whisper_voice_typing.typer.is_macos", return_value=True)
    @patch("whisper_voice_typing.typer._HAS_PYOBJC", False)
    @patch("whisper_voice_typing.typer.subprocess.run")
    def test_osascript_accessibility_denied(self, mock_run, mock_platform):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=b"old"),  # pbpaste
            MagicMock(returncode=0),  # pbcopy
            MagicMock(returncode=1, stderr="not allowed assistive"),  # osascript denied
            MagicMock(returncode=0),  # pbcopy restore
        ]
        result = type_text("hello")
        assert result is False


class TestClipboardRestoration:
    """Test clipboard save/restore logic."""

    @patch("whisper_voice_typing.typer.is_macos", return_value=True)
    @patch("whisper_voice_typing.typer._HAS_PYOBJC", False)
    @patch("whisper_voice_typing.typer.subprocess.run")
    def test_clipboard_restored_after_paste(self, mock_run, mock_platform):
        calls = []
        def track_call(*args, **kwargs):
            calls.append(args[0] if args else kwargs.get('args'))
            if args[0][0] == "pbpaste":
                return MagicMock(returncode=0, stdout=b"saved clipboard")
            if args[0][0] == "osascript":
                return MagicMock(returncode=0, stderr="")
            return MagicMock(returncode=0)

        mock_run.side_effect = track_call
        type_text("new text")

        # verify pbcopy was called twice: once to set, once to restore
        pbcopy_calls = [c for c in calls if c[0] == "pbcopy"]
        assert len(pbcopy_calls) == 2

    @patch("whisper_voice_typing.typer.is_macos", return_value=True)
    @patch("whisper_voice_typing.typer._HAS_PYOBJC", False)
    @patch("whisper_voice_typing.typer.subprocess.run")
    def test_no_restore_if_pbpaste_fails(self, mock_run, mock_platform):
        calls = []
        def track_call(*args, **kwargs):
            calls.append(args[0])
            if args[0][0] == "pbpaste":
                return MagicMock(returncode=1, stdout=b"")  # pbpaste fails
            if args[0][0] == "osascript":
                return MagicMock(returncode=0, stderr="")
            return MagicMock(returncode=0)

        mock_run.side_effect = track_call
        type_text("new text")

        # should NOT call pbcopy a second time to restore
        pbcopy_calls = [c for c in calls if c[0] == "pbcopy"]
        assert len(pbcopy_calls) == 1  # only the set call
