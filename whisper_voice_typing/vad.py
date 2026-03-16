"""Voice Activity Detection: Silero VAD (ONNX) with RMS energy fallback."""

import logging, struct, math

log = logging.getLogger("whisper_voice_typing")

# 512 samples at 16kHz = 32ms, Silero's native chunk size
FRAME_SAMPLES = 512
FRAME_BYTES = FRAME_SAMPLES * 2


class VAD:
    def __init__(self, threshold: float = 0.5):
        self._threshold = threshold
        self._backend = "silero"
        self._model = None
        self._rms_threshold = 500.0

        try:
            from silero_vad import load_silero_vad
            self._model = load_silero_vad(onnx=True)
            log.info("VAD: Silero loaded (ONNX Runtime)")
        except Exception as e:
            log.warning(f"VAD: Silero failed ({e}), using RMS fallback")
            self._backend = "rms"

    def is_speech(self, frame: bytes, sample_rate: int = 16000) -> bool:
        if self._backend == "silero":
            return self._silero_detect(frame, sample_rate)
        return self._rms_detect(frame)

    def _silero_detect(self, frame: bytes, sample_rate: int) -> bool:
        try:
            import torch
            samples = struct.unpack(f"<{len(frame) // 2}h", frame)
            tensor = torch.FloatTensor(samples) / 32768.0
            return self._model(tensor, sample_rate).item() >= self._threshold
        except Exception as e:
            log.warning(f"VAD: Silero error ({e}), switching to RMS")
            self._backend = "rms"
            return self._rms_detect(frame)

    def _rms_detect(self, frame: bytes) -> bool:
        if len(frame) < 2:
            return False
        samples = struct.unpack(f"<{len(frame) // 2}h", frame)
        return math.sqrt(sum(s * s for s in samples) / len(samples)) >= self._rms_threshold

    def reset(self) -> None:
        if self._backend == "silero" and self._model is not None:
            try: self._model.reset_states()
            except Exception: pass
