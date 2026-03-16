"""Tests for menu bar state logic (no rumps required)."""

import queue
from collections import deque

import pytest

from whisper_voice_typing.state import State


class TestStateIconMapping:
    """Test that every state has an icon and title mapping."""

    def test_all_states_have_icons(self):
        from whisper_voice_typing.menubar import _ICONS
        for state in State:
            assert state in _ICONS, f"{state.name} missing from _ICONS"

    def test_all_states_have_titles(self):
        from whisper_voice_typing.menubar import _TITLES
        for state in State:
            assert state in _TITLES, f"{state.name} missing from _TITLES"


class TestStateUpdate:
    def test_state_update_fields(self):
        from whisper_voice_typing.menubar import StateUpdate
        update = StateUpdate(State.RECORDING, detail="test", duration=5.0)
        assert update.state == State.RECORDING
        assert update.detail == "test"
        assert update.duration == 5.0


class TestTranscriptionResult:
    def test_transcription_result(self):
        from whisper_voice_typing.menubar import TranscriptionResult
        result = TranscriptionResult("hello world")
        assert result.text == "hello world"


class TestTranscriptionHistory:
    """Test the deque-based transcription history."""

    def test_history_max_size(self):
        history: deque[str] = deque(maxlen=5)
        for i in range(10):
            history.appendleft(f"text {i}")
        assert len(history) == 5
        assert history[0] == "text 9"

    def test_history_ordering(self):
        history: deque[str] = deque(maxlen=5)
        history.appendleft("first")
        history.appendleft("second")
        history.appendleft("third")
        assert list(history) == ["third", "second", "first"]

    def test_truncation_for_display(self):
        text = "a" * 100
        display = text if len(text) <= 50 else text[:47] + "..."
        assert len(display) == 50
        assert display.endswith("...")


class TestListInputDevices:
    def test_returns_list_when_sounddevice_unavailable(self):
        from whisper_voice_typing.menubar import _list_input_devices
        # Should return empty list gracefully if sounddevice not installed
        result = _list_input_devices()
        assert isinstance(result, list)

    def test_returns_devices_with_expected_keys(self):
        """If sounddevice is available, devices should have index/name/is_default."""
        from whisper_voice_typing.menubar import _list_input_devices
        from unittest.mock import patch, MagicMock

        mock_devices = [
            {'name': 'MacBook Pro Microphone', 'max_input_channels': 1, 'max_output_channels': 0},
            {'name': 'External Headset', 'max_input_channels': 1, 'max_output_channels': 2},
            {'name': 'Speakers', 'max_input_channels': 0, 'max_output_channels': 2},
        ]
        mock_sd = MagicMock()
        mock_sd.query_devices.return_value = mock_devices
        mock_sd.default.device = (0, 1)

        with patch.dict('sys.modules', {'sounddevice': mock_sd}):
            result = _list_input_devices()

        assert len(result) == 2  # only input devices
        assert result[0]['name'] == 'MacBook Pro Microphone'
        assert result[0]['is_default'] is True
        assert result[1]['name'] == 'External Headset'
        assert result[1]['is_default'] is False


