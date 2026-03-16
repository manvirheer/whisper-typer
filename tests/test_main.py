"""Tests for CLI entry point and LaunchAgent management."""

import sys, plistlib
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class TestCLIParsing:
    def test_no_args_runs_app(self):
        with patch("whisper_voice_typing.__main__.WhisperVoiceTyping") as mock_app:
            sys.argv = ["wv"]
            from whisper_voice_typing.__main__ import main
            main()
            mock_app.return_value.run.assert_called_once()

    def test_install_calls_install(self):
        with patch("whisper_voice_typing.__main__._install_launchagent") as mock:
            sys.argv = ["wv", "install"]
            from whisper_voice_typing.__main__ import main
            main()
            mock.assert_called_once()

    def test_uninstall_calls_uninstall(self):
        with patch("whisper_voice_typing.__main__._uninstall_launchagent") as mock:
            sys.argv = ["wv", "uninstall"]
            from whisper_voice_typing.__main__ import main
            main()
            mock.assert_called_once()


class TestLaunchAgent:
    @patch("whisper_voice_typing.__main__.shutil.which", return_value="/usr/local/bin/wv")
    def test_install_creates_plist(self, mock_which, tmp_path):
        from whisper_voice_typing.__main__ import _install_launchagent
        from whisper_voice_typing.config import Config

        config = Config()
        config.launchagent_dir = tmp_path
        config.log_dir = tmp_path / "logs"

        with patch("whisper_voice_typing.__main__.Config", return_value=config):
            _install_launchagent()

        plist_path = tmp_path / f"{config.launchagent_label}.plist"
        assert plist_path.exists()

        with open(plist_path, "rb") as f:
            plist = plistlib.load(f)
        assert plist["Label"] == "com.whisper-typer"
        assert plist["ProgramArguments"] == ["/usr/local/bin/wv"]
        assert plist["RunAtLoad"] is True

    @patch("whisper_voice_typing.__main__.shutil.which", return_value=None)
    def test_install_exits_if_wv_not_found(self, mock_which):
        from whisper_voice_typing.__main__ import _install_launchagent
        with pytest.raises(SystemExit):
            _install_launchagent()

    def test_uninstall_removes_plist(self, tmp_path):
        from whisper_voice_typing.__main__ import _uninstall_launchagent
        from whisper_voice_typing.config import Config

        config = Config()
        config.launchagent_dir = tmp_path
        plist_path = tmp_path / f"{config.launchagent_label}.plist"
        plist_path.write_bytes(b"fake plist")

        with patch("whisper_voice_typing.__main__.Config", return_value=config), \
             patch("subprocess.run"):
            _uninstall_launchagent()

        assert not plist_path.exists()

    def test_uninstall_no_plist_is_noop(self, tmp_path, capsys):
        from whisper_voice_typing.__main__ import _uninstall_launchagent
        from whisper_voice_typing.config import Config

        config = Config()
        config.launchagent_dir = tmp_path

        with patch("whisper_voice_typing.__main__.Config", return_value=config):
            _uninstall_launchagent()

        assert "No LaunchAgent" in capsys.readouterr().out
