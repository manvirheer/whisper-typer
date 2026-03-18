"""Tests for configuration."""

import os
from pathlib import Path
from unittest.mock import patch

from whisper_voice_typing.config import Config, _find_whisper_dir


class TestFindWhisperDir:
    def test_env_var_overrides(self, monkeypatch):
        monkeypatch.setenv("WHISPER_CPP_DIR", "/custom/path")
        assert _find_whisper_dir() == Path("/custom/path")

    def test_defaults_to_local_share(self, tmp_path, monkeypatch):
        monkeypatch.delenv("WHISPER_CPP_DIR", raising=False)
        # none of the candidates exist, so falls through to default
        with patch("whisper_voice_typing.config.Path.home", return_value=tmp_path):
            result = _find_whisper_dir()
            assert result == tmp_path / ".local/share/whisper.cpp"

    def test_finds_existing_dir(self, tmp_path, monkeypatch):
        monkeypatch.delenv("WHISPER_CPP_DIR", raising=False)
        whisper_dir = tmp_path / ".local/share/whisper.cpp"
        whisper_dir.mkdir(parents=True)
        with patch("whisper_voice_typing.config.Path.home", return_value=tmp_path):
            assert _find_whisper_dir() == whisper_dir


class TestConfig:
    def test_default_values(self):
        config = Config()
        assert config.sample_rate == 16000
        assert config.channels == 1
        assert config.vad_threshold == 0.5
        assert config.vad_confirmation_ms == 96
        assert config.vad_silence_ms == 1200
        assert config.vad_silence_min_ms == 800
        assert config.vad_silence_max_ms == 2500
        assert config.pre_roll_ms == 500
        assert config.max_recording_duration == 45
        assert config.transcription_history_size == 5

    def test_model_env_override(self, monkeypatch):
        monkeypatch.setenv("WHISPER_MODEL", "/custom/model.bin")
        config = Config()
        assert config.whisper_model == Path("/custom/model.bin")

    def test_launchagent_plist_path(self):
        config = Config()
        assert config.launchagent_plist.name == "com.whisper-typer.plist"

    def test_thread_count_bounded(self):
        config = Config()
        assert 1 <= config.thread_count <= 8

    def test_max_recording_duration_default(self, monkeypatch):
        monkeypatch.delenv("WHISPER_MAX_RECORDING_DURATION", raising=False)
        config = Config()
        assert config.max_recording_duration == 45

    def test_max_recording_duration_env_override(self, monkeypatch):
        monkeypatch.setenv("WHISPER_MAX_RECORDING_DURATION", "60")
        config = Config()
        assert config.max_recording_duration == 60

    def test_command_delay_ms_default(self, monkeypatch):
        monkeypatch.delenv("WHISPER_COMMAND_DELAY_MS", raising=False)
        config = Config()
        assert config.command_delay_ms == 300

    def test_command_delay_ms_env_override(self, monkeypatch):
        monkeypatch.setenv("WHISPER_COMMAND_DELAY_MS", "500")
        config = Config()
        assert config.command_delay_ms == 500


class TestValidation:
    def test_validation_exits_on_missing_binary(self, tmp_path):
        config = Config()
        config.whisper_executable = tmp_path / "nonexistent"
        config.server_binary = tmp_path / "nonexistent2"
        config.whisper_model = tmp_path / "nonexistent3"

        from whisper_voice_typing.utils import TableLogger
        tlog = TableLogger()

        import pytest
        with pytest.raises(SystemExit):
            config.validate(tlog)

    def test_validation_checks_sounddevice(self, tmp_path, monkeypatch):
        config = Config()
        # make binaries "exist"
        for f in [config.whisper_executable, config.server_binary, config.whisper_model]:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.touch()

        # sounddevice import fails
        import builtins
        original = builtins.__import__
        def fail_sd(name, *a, **kw):
            if name == "sounddevice": raise ImportError
            return original(name, *a, **kw)

        from whisper_voice_typing.utils import TableLogger
        tlog = TableLogger()

        monkeypatch.setattr(builtins, "__import__", fail_sd)
        import pytest
        with pytest.raises(SystemExit):
            config.validate(tlog)
