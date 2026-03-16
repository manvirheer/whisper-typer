"""
Voice Activity Detection with Silero VAD (ONNX Runtime) and RMS energy fallback.

Interface: is_speech(frame) -> bool
Both backends implement the same contract so the consumer doesn't
know or care which is active.
"""

import logging
import struct
import math

log = logging.getLogger("whisper_voice_typing")

# frame size for 100ms at 16kHz 16-bit mono
FRAME_SAMPLES = 1600  # 16000 * 0.1
FRAME_BYTES = FRAME_SAMPLES * 2  # 16-bit = 2 bytes per sample


class VAD:
    def __init__(self, threshold: float = 0.5):
        self._threshold = threshold
        self._backend = "silero"
        self._model = None
        self._rms_threshold = 500.0  # fallback RMS threshold for speech

        # silero ONNX internal state
        self._h = None
        self._c = None
        self._sr = None

        try:
            self._init_silero()
            log.info("VAD: Silero loaded (ONNX Runtime)")
        except Exception as e:
            log.warning(f"VAD: Silero failed ({e}), falling back to RMS energy detection")
            self._backend = "rms"

    def _init_silero(self) -> None:
        from silero_vad import load_silero_vad  # type: ignore
        self._model = load_silero_vad(onnx=True)

    def is_speech(self, frame: bytes, sample_rate: int = 16000) -> bool:
        """Returns True if the audio frame contains speech."""
        if self._backend == "silero":
            return self._silero_detect(frame, sample_rate)
        return self._rms_detect(frame)

    def _silero_detect(self, frame: bytes, sample_rate: int) -> bool:
        try:
            import torch
            # convert raw PCM bytes to float tensor
            samples = struct.unpack(f"<{len(frame) // 2}h", frame)
            audio_tensor = torch.FloatTensor(samples) / 32768.0
            confidence = self._model(audio_tensor, sample_rate).item()
            return confidence >= self._threshold
        except Exception as e:
            log.warning(f"VAD: Silero inference error ({e}), falling back to RMS")
            self._backend = "rms"
            return self._rms_detect(frame)

    def _rms_detect(self, frame: bytes) -> bool:
        """Simple energy-based VAD using RMS amplitude."""
        if len(frame) < 2:
            return False
        samples = struct.unpack(f"<{len(frame) // 2}h", frame)
        rms = math.sqrt(sum(s * s for s in samples) / len(samples))
        return rms >= self._rms_threshold

    def reset(self) -> None:
        """Reset internal state between utterances."""
        if self._backend == "silero" and self._model is not None:
            try:
                self._model.reset_states()
            except Exception:
                pass
