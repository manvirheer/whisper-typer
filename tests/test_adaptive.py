"""Tests for adaptive silence timeout."""

from collections import deque
from whisper_voice_typing.app import WhisperVoiceTyping


class TestAdaptiveSilence:
    def setup_method(self):
        self.app = WhisperVoiceTyping.__new__(WhisperVoiceTyping)
        from whisper_voice_typing.config import Config
        self.app.config = Config()

    def test_no_history_returns_default(self):
        result = self.app._adapt_silence(deque(), frame_ms=32)
        assert result == self.app.config.vad_silence_ms // 32

    def test_fast_talker_gets_shorter_timeout(self):
        # average pause of 0.5s -> target = 300ms -> clamped to 800ms min
        pauses = deque([0.4, 0.5, 0.6])
        result = self.app._adapt_silence(pauses, frame_ms=32)
        assert result == 800 // 32  # hits minimum

    def test_slow_talker_gets_longer_timeout(self):
        # average pause of 3s -> target = 1800ms
        pauses = deque([2.5, 3.0, 3.5])
        result = self.app._adapt_silence(pauses, frame_ms=32)
        assert result == 1800 // 32

    def test_very_slow_caps_at_max(self):
        # average pause of 8s -> target = 4800ms -> clamped to 2500ms max
        pauses = deque([7.0, 8.0, 9.0])
        result = self.app._adapt_silence(pauses, frame_ms=32)
        assert result == 2500 // 32

    def test_adapts_to_recent_pattern(self):
        # mix of fast and slow, recent ones are fast
        pauses = deque([3.0, 3.0, 1.0, 1.0, 1.0, 1.0], maxlen=8)
        result = self.app._adapt_silence(pauses, frame_ms=32)
        avg = sum(pauses) / len(pauses)  # ~1.67s
        target = int(avg * 1000 * 0.6)   # ~1000ms
        assert result == target // 32
