"""Tests for WhisperServer transcription logic."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

from whisper_voice_typing.server import WhisperServer
from whisper_voice_typing.config import Config


class TestTranscribeViaServer:
    def setup_method(self):
        self.config = Config()
        self.server = WhisperServer(self.config)

    def _call(self, mock_post, audio_path="/tmp/test.wav"):
        with patch("builtins.open", mock_open(read_data=b"fake audio")):
            return self.server._transcribe_via_server(Path(audio_path))

    @patch("whisper_voice_typing.server.requests.post")
    def test_successful_transcription(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "hello world"}
        mock_post.return_value = mock_resp

        result = self._call(mock_post)
        assert result == "hello world"
        assert self.server._transcribe_fails == 0

    @patch("whisper_voice_typing.server.requests.post")
    def test_blank_audio_returns_none(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "[BLANK_AUDIO]"}
        mock_post.return_value = mock_resp

        result = self._call(mock_post)
        assert result is None

    @patch("whisper_voice_typing.server.requests.post")
    def test_empty_text_returns_none(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": ""}
        mock_post.return_value = mock_resp

        result = self._call(mock_post)
        assert result is None

    @patch("whisper_voice_typing.server.requests.post")
    def test_http_error_increments_fails(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_post.return_value = mock_resp

        result = self._call(mock_post)
        assert result is None
        assert self.server._transcribe_fails == 1

    @patch("whisper_voice_typing.server.requests.post")
    def test_json_decode_error_handled(self, mock_post):
        """JSONDecodeError should be caught, not crash."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("No JSON object could be decoded")
        mock_resp.text = "not json"
        mock_post.return_value = mock_resp

        result = self._call(mock_post)
        assert result is None
        assert self.server._transcribe_fails == 1

    @patch("whisper_voice_typing.server.requests.post")
    def test_connection_error_handled(self, mock_post):
        import requests
        mock_post.side_effect = requests.ConnectionError("refused")

        result = self._call(mock_post)
        assert result is None
        assert self.server._transcribe_fails == 1

    @patch("whisper_voice_typing.server.requests.post")
    def test_timeout_handled(self, mock_post):
        import requests
        mock_post.side_effect = requests.Timeout("timed out")

        result = self._call(mock_post)
        assert result is None
        assert self.server._transcribe_fails == 1

    def test_exponential_backoff_increases(self):
        self.server._backoff_delay = 1.0
        self.server._backoff_delay = min(self.server._backoff_delay * 2, self.server._max_backoff)
        assert self.server._backoff_delay == 2.0
        self.server._backoff_delay = min(self.server._backoff_delay * 2, self.server._max_backoff)
        assert self.server._backoff_delay == 4.0

    def test_backoff_caps_at_max(self):
        self.server._backoff_delay = 16.0
        self.server._backoff_delay = min(self.server._backoff_delay * 2, self.server._max_backoff)
        assert self.server._backoff_delay == self.server._max_backoff

    @patch("whisper_voice_typing.server.requests.post")
    def test_success_resets_fail_counter(self, mock_post):
        self.server._transcribe_fails = 2
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "hello"}
        mock_post.return_value = mock_resp

        result = self._call(mock_post)
        assert result == "hello"
        assert self.server._transcribe_fails == 0

    @patch("whisper_voice_typing.server.requests.post")
    def test_whitespace_only_text_returns_none(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "   \n  "}
        mock_post.return_value = mock_resp

        result = self._call(mock_post)
        assert result is None
