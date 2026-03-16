"""Tests for the app controller logic."""

import queue
from collections import deque
from unittest.mock import patch, MagicMock

import pytest

from whisper_voice_typing.app import WhisperVoiceTyping
from whisper_voice_typing.state import State


class TestProcessCommands:
    def setup_method(self):
        self.app = WhisperVoiceTyping.__new__(WhisperVoiceTyping)
        from whisper_voice_typing.config import Config
        from whisper_voice_typing.state import StateMachine
        from whisper_voice_typing.server import WhisperServer
        self.app.config = Config()
        self.app.state_machine = StateMachine()
        self.app.server = WhisperServer(self.app.config)
        self.app._ui_queue = queue.Queue()
        self.app._command_queue = queue.Queue()
        self.app._audio = MagicMock()
        self.app._vad = MagicMock()
        self.app._type_text = MagicMock(return_value=True)
        self.app.running = True

    def test_start_transitions_to_listening(self):
        self.app._audio.is_active.return_value = True
        self.app.server.is_running = MagicMock(return_value=True)
        self.app._command_queue.put("start")
        self.app._process_commands()
        assert self.app.state_machine.state == State.LISTENING

    def test_stop_transitions_to_idle(self):
        self.app.state_machine.transition(State.LISTENING)
        self.app._command_queue.put("stop")
        self.app._process_commands()
        assert self.app.state_machine.state == State.IDLE
        self.app._audio.stop.assert_called()

    def test_pause_transitions_to_paused(self):
        self.app.state_machine.transition(State.LISTENING)
        self.app._command_queue.put("pause")
        self.app._process_commands()
        assert self.app.state_machine.state == State.PAUSED

    def test_resume_transitions_to_listening(self):
        self.app.state_machine.transition(State.LISTENING)
        self.app.state_machine.transition(State.PAUSED)
        self.app._audio.is_active.return_value = True
        self.app._command_queue.put("resume")
        self.app._process_commands()
        assert self.app.state_machine.state == State.LISTENING

    def test_force_transcribe_from_recording(self):
        self.app.state_machine.transition(State.LISTENING)
        self.app.state_machine.transition(State.DETECTED)
        self.app.state_machine.transition(State.RECORDING)
        self.app._audio.save_recording.return_value = None
        self.app._command_queue.put("force_transcribe")
        self.app._process_commands()
        # should have tried to transcribe (saved -> None -> back to listening)
        assert self.app.state_machine.state == State.LISTENING

    def test_force_transcribe_ignored_when_idle(self):
        self.app._command_queue.put("force_transcribe")
        self.app._process_commands()
        assert self.app.state_machine.state == State.IDLE

    def test_quit_stops_running(self):
        self.app._command_queue.put("quit")
        self.app._process_commands()
        assert self.app.running is False

    def test_start_error_shows_error_state(self):
        self.app._audio.is_active.return_value = False
        self.app._audio.start.side_effect = Exception("mic fail")
        self.app._command_queue.put("start")
        self.app._process_commands()
        # should have put an error update on the queue
        updates = []
        while not self.app._ui_queue.empty():
            updates.append(self.app._ui_queue.get())
        assert any(u.state == State.ERROR for u in updates if hasattr(u, 'state'))


class TestDoTranscribe:
    def setup_method(self):
        self.app = WhisperVoiceTyping.__new__(WhisperVoiceTyping)
        from whisper_voice_typing.config import Config
        from whisper_voice_typing.state import StateMachine
        from whisper_voice_typing.server import WhisperServer
        self.app.config = Config()
        self.app.state_machine = StateMachine()
        self.app.server = WhisperServer(self.app.config)
        self.app._ui_queue = queue.Queue()
        self.app._command_queue = queue.Queue()
        self.app._audio = MagicMock()
        self.app._vad = MagicMock()
        self.app._type_text = MagicMock(return_value=True)
        self.app.running = True
        # get to RECORDING state
        self.app.state_machine.transition(State.LISTENING)
        self.app.state_machine.transition(State.DETECTED)
        self.app.state_machine.transition(State.RECORDING)

    def test_no_audio_goes_back_to_listening(self):
        self.app._audio.save_recording.return_value = None
        self.app._do_transcribe()
        assert self.app.state_machine.state == State.LISTENING

    def test_successful_transcription_types_text(self):
        from pathlib import Path
        audio_file = MagicMock(spec=Path)
        self.app._audio.save_recording.return_value = audio_file
        self.app.server.transcribe = MagicMock(return_value="hello world")
        self.app._do_transcribe()
        self.app._type_text.assert_called_with("hello world")

    def test_blank_transcription_goes_to_listening(self):
        from pathlib import Path
        audio_file = MagicMock(spec=Path)
        self.app._audio.save_recording.return_value = audio_file
        self.app.server.transcribe = MagicMock(return_value=None)
        self.app._do_transcribe()
        assert self.app.state_machine.state == State.LISTENING


class TestCheckSingleInstance:
    def test_writes_pid_file(self, tmp_path):
        app = WhisperVoiceTyping.__new__(WhisperVoiceTyping)
        app.pid_file = tmp_path / "test.pid"
        app._check_single_instance()
        assert app.pid_file.exists()
        import os
        assert int(app.pid_file.read_text()) == os.getpid()

    def test_removes_stale_pid_file(self, tmp_path):
        app = WhisperVoiceTyping.__new__(WhisperVoiceTyping)
        app.pid_file = tmp_path / "test.pid"
        app.pid_file.write_text("99999999")  # nonexistent PID
        app._check_single_instance()  # should clean up and continue
        import os
        assert int(app.pid_file.read_text()) == os.getpid()
