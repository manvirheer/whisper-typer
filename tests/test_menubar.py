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
