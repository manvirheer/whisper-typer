"""Tests for VAD interface."""

import struct, math
import pytest
from whisper_voice_typing.vad import VAD

FRAME_SAMPLES = 1600  # 100ms at 16kHz (what the audio pipeline sends)


class TestRMSFallbackVAD:
    def setup_method(self):
        self.vad = VAD.__new__(VAD)
        self.vad._backend = "rms"
        self.vad._model = None
        self.vad._threshold = 0.5
        self.vad._rms_threshold = 500.0

    def _make_frame(self, amplitude: int = 0, frequency: float = 440.0) -> bytes:
        samples = []
        for i in range(FRAME_SAMPLES):
            value = int(amplitude * math.sin(2 * math.pi * frequency * i / 16000))
            samples.append(max(-32768, min(32767, value)))
        return struct.pack(f"<{FRAME_SAMPLES}h", *samples)

    def test_silence_is_not_speech(self):
        assert self.vad.is_speech(self._make_frame(amplitude=0)) is False

    def test_quiet_noise_is_not_speech(self):
        assert self.vad.is_speech(self._make_frame(amplitude=100)) is False

    def test_loud_signal_is_speech(self):
        assert self.vad.is_speech(self._make_frame(amplitude=5000)) is True

    def test_threshold_boundary(self):
        assert self.vad.is_speech(self._make_frame(amplitude=600)) is False   # RMS ~424
        assert self.vad.is_speech(self._make_frame(amplitude=800)) is True    # RMS ~566

    def test_empty_frame(self):
        assert self.vad.is_speech(b"") is False

    def test_single_sample(self):
        assert self.vad.is_speech(struct.pack("<h", 10000)) is True

    def test_reset_does_not_crash(self):
        self.vad.reset()


class TestVADInit:
    def test_falls_back_to_rms_when_torch_missing(self, monkeypatch):
        import builtins
        original_import = builtins.__import__
        def mock_import(name, *args, **kwargs):
            if name == "torch":
                raise ImportError("No module named 'torch'")
            return original_import(name, *args, **kwargs)
        monkeypatch.setattr(builtins, "__import__", mock_import)
        vad = VAD(threshold=0.5)
        assert vad._backend == "rms"

    def test_rms_fallback_still_detects_speech(self):
        vad = VAD.__new__(VAD)
        vad._backend = "rms"
        vad._model = None
        vad._threshold = 0.5
        vad._rms_threshold = 500.0

        loud = struct.pack(f"<{FRAME_SAMPLES}h", *([5000] * FRAME_SAMPLES))
        assert vad.is_speech(loud) is True

        silent = struct.pack(f"<{FRAME_SAMPLES}h", *([0] * FRAME_SAMPLES))
        assert vad.is_speech(silent) is False
