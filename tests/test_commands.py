"""Tests for voice command parsing and execution."""

import time
from unittest.mock import patch, MagicMock

import pytest


class TestParseCommand:
    def test_trailing_command_enter(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("hello command enter")
        assert text == "hello"
        assert keycode == 36

    def test_case_insensitive(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("hello Command Enter")
        assert text == "hello"
        assert keycode == 36

    def test_trailing_period(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("hello command enter.")
        assert text == "hello"
        assert keycode == 36

    def test_multiple_trailing_punctuation(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("hello command enter!!!")
        assert text == "hello"
        assert keycode == 36

    def test_no_command(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("hello world")
        assert text == "hello world"
        assert keycode is None

    def test_command_not_at_end(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("hello command enter goodbye")
        assert text == "hello command enter goodbye"
        assert keycode is None

    def test_command_only(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("command enter")
        assert text == ""
        assert keycode == 36

    def test_preserves_original_casing(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("Hello World command enter")
        assert text == "Hello World"
        assert keycode == 36

    def test_strips_leading_whitespace_from_result(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("  command enter")
        assert text == ""
        assert keycode == 36

    def test_command_mid_sentence(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("I used the command enter key")
        assert text == "I used the command enter key"
        assert keycode is None

    def test_semicolon_stripped(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("hello command enter;")
        assert text == "hello"
        assert keycode == 36

    def test_empty_string(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("")
        assert text == ""
        assert keycode is None


class TestExecuteCommand:
    @patch("whisper_voice_typing.commands.send_key", return_value=True)
    def test_executes_keypress(self, mock_send):
        from whisper_voice_typing.commands import execute_command
        assert execute_command(36, 0) is True
        mock_send.assert_called_once_with(36)

    @patch("whisper_voice_typing.commands.send_key", return_value=False)
    def test_returns_false_on_failure(self, mock_send):
        from whisper_voice_typing.commands import execute_command
        assert execute_command(36, 0) is False

    @patch("whisper_voice_typing.commands.send_key", return_value=True)
    @patch("whisper_voice_typing.commands.time.sleep")
    def test_delays_before_keypress(self, mock_sleep, mock_send):
        from whisper_voice_typing.commands import execute_command
        execute_command(36, 300)
        mock_sleep.assert_called_once_with(0.3)

    @patch("whisper_voice_typing.commands.send_key", return_value=True)
    @patch("whisper_voice_typing.commands.time.sleep")
    def test_no_delay_when_zero(self, mock_sleep, mock_send):
        from whisper_voice_typing.commands import execute_command
        execute_command(36, 0)
        mock_sleep.assert_not_called()
