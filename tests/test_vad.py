"""Tests for VAD interface."""

import struct
import math

import pytest

from whisper_voice_typing.vad import VAD, FRAME_SAMPLES, FRAME_BYTES


class TestRMSFallbackVAD:
    """Test the RMS energy-based fallback VAD directly."""

    def setup_method(self):
        self.vad = VAD.__new__(VAD)
        self.vad._backend = "rms"
        self.vad._model = None
        self.vad._threshold = 0.5
        self.vad._rms_threshold = 500.0

    def _make_frame(self, amplitude: int = 0, frequency: float = 440.0) -> bytes:
        """Generate a 100ms audio frame."""
        samples = []
        for i in range(FRAME_SAMPLES):
            value = int(amplitude * math.sin(2 * math.pi * frequency * i / 16000))
            samples.append(max(-32768, min(32767, value)))
        return struct.pack(f"<{FRAME_SAMPLES}h", *samples)

    def test_silence_is_not_speech(self):
        frame = self._make_frame(amplitude=0)
        assert self.vad.is_speech(frame) is False

    def test_quiet_noise_is_not_speech(self):
        frame = self._make_frame(amplitude=100)
        assert self.vad.is_speech(frame) is False

    def test_loud_signal_is_speech(self):
        frame = self._make_frame(amplitude=5000)
        assert self.vad.is_speech(frame) is True

    def test_threshold_boundary(self):
        # just below threshold
        frame_quiet = self._make_frame(amplitude=600)
        # just above threshold (RMS of sine = amplitude / sqrt(2) ~ 0.707)
        frame_loud = self._make_frame(amplitude=800)
        # 600 * 0.707 = ~424 (below 500 threshold)
        assert self.vad.is_speech(frame_quiet) is False
        # 800 * 0.707 = ~566 (above 500 threshold)
        assert self.vad.is_speech(frame_loud) is True

    def test_empty_frame(self):
        assert self.vad.is_speech(b"") is False

    def test_single_sample(self):
        frame = struct.pack("<h", 10000)
        assert self.vad.is_speech(frame) is True

    def test_reset_does_not_crash(self):
        self.vad.reset()  # should be a no-op for RMS


class TestVADInit:
    """Test VAD initialization and fallback behavior."""

    def test_falls_back_to_rms_when_torch_missing(self, monkeypatch):
        """When torch is not available, VAD should fall back to RMS."""
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
        """After fallback, VAD should still detect speech via RMS."""
        vad = VAD.__new__(VAD)
        vad._backend = "rms"
        vad._model = None
        vad._threshold = 0.5
        vad._rms_threshold = 500.0

        # loud signal
        samples = [5000] * FRAME_SAMPLES
        frame = struct.pack(f"<{FRAME_SAMPLES}h", *samples)
        assert vad.is_speech(frame) is True

        # silence
        samples = [0] * FRAME_SAMPLES
        frame = struct.pack(f"<{FRAME_SAMPLES}h", *samples)
        assert vad.is_speech(frame) is False
