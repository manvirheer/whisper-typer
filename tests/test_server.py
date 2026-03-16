"""Tests for WhisperServer."""

import time
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

import pytest
import requests

from whisper_voice_typing.server import WhisperServer
from whisper_voice_typing.config import Config


class TestTranscribeViaServer:
    def setup_method(self):
        self.config = Config()
        self.server = WhisperServer(self.config)

    def _call(self, mock_post):
        with patch("builtins.open", mock_open(read_data=b"fake audio")):
            return self.server._transcribe_via_server(Path("/tmp/test.wav"))

    @patch("whisper_voice_typing.server.requests.post")
    def test_successful_transcription(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"text": "hello world"})
        assert self._call(mock_post) == "hello world"
        assert self.server._transcribe_fails == 0

    @patch("whisper_voice_typing.server.requests.post")
    def test_blank_audio_returns_none(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"text": "[BLANK_AUDIO]"})
        assert self._call(mock_post) is None

    @patch("whisper_voice_typing.server.requests.post")
    def test_empty_text_returns_none(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"text": ""})
        assert self._call(mock_post) is None

    @patch("whisper_voice_typing.server.requests.post")
    def test_whitespace_only_returns_none(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"text": "   \n  "})
        assert self._call(mock_post) is None

    @patch("whisper_voice_typing.server.requests.post")
    def test_http_error_increments_fails(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500)
        assert self._call(mock_post) is None
        assert self.server._transcribe_fails == 1

    @patch("whisper_voice_typing.server.requests.post")
    def test_json_decode_error_handled(self, mock_post):
        resp = MagicMock(status_code=200, text="not json")
        resp.json.side_effect = ValueError("bad json")
        mock_post.return_value = resp
        assert self._call(mock_post) is None
        assert self.server._transcribe_fails == 1

    @patch("whisper_voice_typing.server.requests.post")
    def test_connection_error(self, mock_post):
        mock_post.side_effect = requests.ConnectionError("refused")
        assert self._call(mock_post) is None
        assert self.server._transcribe_fails == 1

    @patch("whisper_voice_typing.server.requests.post")
    def test_timeout_error(self, mock_post):
        mock_post.side_effect = requests.Timeout("timed out")
        assert self._call(mock_post) is None
        assert self.server._transcribe_fails == 1

    @patch("whisper_voice_typing.server.requests.post")
    def test_success_resets_fail_counter(self, mock_post):
        self.server._transcribe_fails = 2
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"text": "hello"})
        assert self._call(mock_post) == "hello"
        assert self.server._transcribe_fails == 0


class TestTranscribeDirect:
    def setup_method(self):
        self.config = Config()
        self.server = WhisperServer(self.config)

    @patch("whisper_voice_typing.server.subprocess.run")
    def test_successful_direct(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="hello world")
        result = self.server._transcribe_direct(Path("/tmp/test.wav"))
        assert result == "hello world"

    @patch("whisper_voice_typing.server.subprocess.run")
    def test_blank_audio_direct(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="[BLANK_AUDIO]")
        assert self.server._transcribe_direct(Path("/tmp/test.wav")) is None

    @patch("whisper_voice_typing.server.subprocess.run")
    def test_nonzero_exit(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        assert self.server._transcribe_direct(Path("/tmp/test.wav")) is None

    @patch("whisper_voice_typing.server.subprocess.run")
    def test_exception_handled(self, mock_run):
        mock_run.side_effect = Exception("crash")
        assert self.server._transcribe_direct(Path("/tmp/test.wav")) is None


class TestTranscribeFullFlow:
    def setup_method(self):
        self.config = Config()
        self.server = WhisperServer(self.config)

    @patch.object(WhisperServer, "is_running", return_value=True)
    @patch.object(WhisperServer, "_transcribe_via_server", return_value="hello")
    def test_uses_server_when_running(self, mock_transcribe, mock_running):
        result = self.server.transcribe(Path("/tmp/test.wav"))
        assert result == "hello"

    @patch.object(WhisperServer, "is_running", return_value=True)
    @patch.object(WhisperServer, "_transcribe_via_server", return_value=None)
    @patch.object(WhisperServer, "_transcribe_direct", return_value="fallback")
    def test_falls_back_to_direct(self, mock_direct, mock_server, mock_running):
        result = self.server.transcribe(Path("/tmp/test.wav"))
        assert result == "fallback"

    @patch.object(WhisperServer, "is_running", return_value=False)
    @patch.object(WhisperServer, "start", return_value=False)
    @patch.object(WhisperServer, "_transcribe_direct", return_value="direct")
    def test_direct_when_server_wont_start(self, mock_direct, mock_start, mock_running):
        result = self.server.transcribe(Path("/tmp/test.wav"))
        assert result == "direct"

    @patch.object(WhisperServer, "stop")
    @patch.object(WhisperServer, "is_running", return_value=True)
    @patch.object(WhisperServer, "_transcribe_via_server", return_value="ok")
    def test_backoff_restarts_server_after_3_fails(self, mock_transcribe, mock_running, mock_stop):
        self.server._transcribe_fails = 3
        with patch("whisper_voice_typing.server.time.sleep"):
            result = self.server.transcribe(Path("/tmp/test.wav"))
        mock_stop.assert_called_once()
        # backoff doubled to 2.0 during restart, then reset to 1.0 on success
        assert result == "ok"


class TestExponentialBackoff:
    def test_doubles_each_time(self):
        server = WhisperServer(Config())
        server._backoff_delay = 1.0
        for expected in [2.0, 4.0, 8.0, 16.0, 30.0, 30.0]:
            server._backoff_delay = min(server._backoff_delay * 2, server._max_backoff)
            assert server._backoff_delay == expected

    def test_success_resets_backoff(self):
        server = WhisperServer(Config())
        server._backoff_delay = 16.0
        server._backoff_delay = 1.0
        assert server._backoff_delay == 1.0


class TestIsRunning:
    def setup_method(self):
        self.server = WhisperServer(Config())

    def test_no_pid_file(self, tmp_path):
        self.server.config.server_pid_file = tmp_path / "nonexistent.pid"
        assert self.server.is_running() is False

    @patch("whisper_voice_typing.server.os.kill")
    @patch("whisper_voice_typing.server.requests.get")
    def test_running_pid_and_healthy(self, mock_get, mock_kill, tmp_path):
        pid_file = tmp_path / "server.pid"
        pid_file.write_text("12345")
        self.server.config.server_pid_file = pid_file
        mock_kill.return_value = None  # process exists
        mock_get.return_value = MagicMock(status_code=200)
        assert self.server.is_running() is True

    @patch("whisper_voice_typing.server.os.kill", side_effect=OSError)
    def test_stale_pid_cleaned_up(self, mock_kill, tmp_path):
        pid_file = tmp_path / "server.pid"
        pid_file.write_text("99999")
        self.server.config.server_pid_file = pid_file
        assert self.server.is_running() is False
        assert not pid_file.exists()
