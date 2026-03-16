"""Tests for VAD interface."""

import struct, math
import pytest
from whisper_voice_typing.vad import VAD, FRAME_SAMPLES, FRAME_BYTES


class TestConstants:
    def test_frame_samples_matches_silero(self):
        assert FRAME_SAMPLES == 512

    def test_frame_bytes_is_double_samples(self):
        assert FRAME_BYTES == FRAME_SAMPLES * 2


class TestRMSFallbackVAD:
    def setup_method(self):
        self.vad = VAD.__new__(VAD)
        self.vad._backend = "rms"
        self.vad._model = None
        self.vad._threshold = 0.5
        self.vad._rms_threshold = 500.0

    def _make_frame(self, amplitude: int = 0, frequency: float = 440.0, n_samples: int = FRAME_SAMPLES) -> bytes:
        samples = [int(amplitude * math.sin(2 * math.pi * frequency * i / 16000)) for i in range(n_samples)]
        samples = [max(-32768, min(32767, s)) for s in samples]
        return struct.pack(f"<{n_samples}h", *samples)

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

    def test_single_byte(self):
        assert self.vad.is_speech(b"\x00") is False

    def test_single_sample(self):
        assert self.vad.is_speech(struct.pack("<h", 10000)) is True

    def test_large_frame(self):
        assert self.vad.is_speech(self._make_frame(amplitude=5000, n_samples=1600)) is True

    def test_reset_does_not_crash(self):
        self.vad.reset()


class TestVADInit:
    def test_falls_back_to_rms_when_silero_missing(self, monkeypatch):
        import builtins
        original = builtins.__import__
        def fail(name, *a, **kw):
            if name == "silero_vad": raise ImportError("no silero")
            return original(name, *a, **kw)
        monkeypatch.setattr(builtins, "__import__", fail)
        vad = VAD(threshold=0.5)
        assert vad._backend == "rms"

    def test_falls_back_to_rms_when_torch_missing(self, monkeypatch):
        import builtins
        original = builtins.__import__
        def fail(name, *a, **kw):
            if name == "torch": raise ImportError("no torch")
            return original(name, *a, **kw)
        monkeypatch.setattr(builtins, "__import__", fail)

        # create a VAD that's "silero" but will fail on first inference
        vad = VAD.__new__(VAD)
        vad._backend = "silero"
        vad._model = None
        vad._threshold = 0.5
        vad._rms_threshold = 500.0

        frame = struct.pack(f"<{FRAME_SAMPLES}h", *([5000] * FRAME_SAMPLES))
        # should fall back to RMS on torch import error
        result = vad.is_speech(frame)
        assert vad._backend == "rms"

    def test_rms_fallback_detects_speech(self):
        vad = VAD.__new__(VAD)
        vad._backend = "rms"
        vad._model = None
        vad._threshold = 0.5
        vad._rms_threshold = 500.0
        assert vad.is_speech(struct.pack(f"<{FRAME_SAMPLES}h", *([5000] * FRAME_SAMPLES))) is True
        assert vad.is_speech(struct.pack(f"<{FRAME_SAMPLES}h", *([0] * FRAME_SAMPLES))) is False

    def test_custom_threshold(self):
        vad = VAD.__new__(VAD)
        vad._backend = "rms"
        vad._model = None
        vad._threshold = 0.5
        vad._rms_threshold = 10000.0  # very high threshold
        # even loud signal is below this
        assert vad.is_speech(struct.pack(f"<{FRAME_SAMPLES}h", *([5000] * FRAME_SAMPLES))) is False


class TestSileroVAD:
    def test_silero_loads(self):
        """Verify Silero actually loads on this machine."""
        vad = VAD()
        assert vad._backend == "silero"
        assert vad._model is not None

    def test_silero_processes_native_frame(self):
        """512-sample frame should not cause errors."""
        vad = VAD()
        frame = struct.pack(f"<{FRAME_SAMPLES}h", *([0] * FRAME_SAMPLES))
        result = vad.is_speech(frame, 16000)
        assert isinstance(result, bool)
        assert vad._backend == "silero"  # didn't fall back

    def test_silero_reset(self):
        vad = VAD()
        vad.reset()
        assert vad._backend == "silero"
