"""Tests for ring buffer and audio pipeline mechanics."""

import struct
import wave
import tempfile
from pathlib import Path

import pytest

from whisper_voice_typing.audio import RingBuffer


class TestRingBuffer:
    def test_write_and_read_simple(self):
        buf = RingBuffer(capacity_seconds=1.0, sample_rate=16000)
        data = b"\x01\x02" * 100
        buf.write(data)
        result = buf.read_last(200)
        assert result == data

    def test_read_last_less_than_written(self):
        buf = RingBuffer(capacity_seconds=1.0, sample_rate=16000)
        data = b"\xAA" * 500
        buf.write(data)
        result = buf.read_last(100)
        assert result == b"\xAA" * 100

    def test_circular_overflow(self):
        """When writing more than capacity, oldest data is overwritten."""
        buf = RingBuffer(capacity_seconds=0.01, sample_rate=16000)  # ~320 bytes
        capacity = buf.capacity_bytes

        # write 2x capacity
        data = bytes(range(256)) * ((capacity * 2) // 256 + 1)
        data = data[:capacity * 2]
        buf.write(data)

        result = buf.read_last(capacity)
        assert len(result) == capacity
        # should contain the last `capacity` bytes of data
        assert result == data[-capacity:]

    def test_read_last_more_than_available(self):
        buf = RingBuffer(capacity_seconds=1.0, sample_rate=16000)
        data = b"\x42" * 50
        buf.write(data)
        result = buf.read_last(1000)
        assert result == data

    def test_read_empty_buffer(self):
        buf = RingBuffer(capacity_seconds=1.0, sample_rate=16000)
        result = buf.read_last(100)
        assert result == b""

    def test_clear(self):
        buf = RingBuffer(capacity_seconds=1.0, sample_rate=16000)
        buf.write(b"\x01" * 100)
        buf.clear()
        result = buf.read_last(100)
        assert result == b""

    def test_read_all(self):
        buf = RingBuffer(capacity_seconds=0.01, sample_rate=16000)
        capacity = buf.capacity_bytes
        data = b"\xFF" * capacity
        buf.write(data)
        result = buf.read_all()
        assert len(result) == capacity

    def test_wrap_around_read(self):
        """Test reading when data wraps around the circular boundary."""
        buf = RingBuffer(capacity_seconds=0.01, sample_rate=16000)
        capacity = buf.capacity_bytes

        # write 75% of capacity
        first_write = b"\xAA" * (capacity * 3 // 4)
        buf.write(first_write)

        # write another 50% - this wraps around
        second_write = b"\xBB" * (capacity // 2)
        buf.write(second_write)

        # last `capacity` bytes should be: tail of first + all of second
        result = buf.read_last(capacity)
        expected_first_part = first_write[-(capacity - len(second_write)):]
        expected = expected_first_part + second_write
        assert result == expected

    def test_multiple_small_writes(self):
        buf = RingBuffer(capacity_seconds=1.0, sample_rate=16000)
        for i in range(10):
            buf.write(bytes([i]) * 100)
        result = buf.read_last(1000)
        assert len(result) == 1000

    def test_pre_roll_capture(self):
        """Simulate the pre-roll: write audio, then read last 500ms."""
        buf = RingBuffer(capacity_seconds=31.0, sample_rate=16000)
        pre_roll_bytes = int(0.5 * 16000 * 2)  # 500ms at 16kHz 16-bit

        # write 2 seconds of audio
        two_seconds = b"\x42" * (2 * 16000 * 2)
        buf.write(two_seconds)

        # read last 500ms (pre-roll)
        pre_roll = buf.read_last(pre_roll_bytes)
        assert len(pre_roll) == pre_roll_bytes

    def test_data_larger_than_capacity(self):
        """Writing data larger than buffer capacity keeps only the tail."""
        buf = RingBuffer(capacity_seconds=0.01, sample_rate=16000)
        capacity = buf.capacity_bytes

        big_data = b"\xCC" * (capacity * 3)
        buf.write(big_data)

        result = buf.read_all()
        assert len(result) == capacity
        assert result == b"\xCC" * capacity


def _generate_wav(path: Path, duration_s: float = 1.0, frequency: float = 440.0, amplitude: int = 10000):
    """Generate a sine wave WAV file for testing."""
    import math
    sample_rate = 16000
    n_samples = int(sample_rate * duration_s)
    samples = []
    for i in range(n_samples):
        value = int(amplitude * math.sin(2 * math.pi * frequency * i / sample_rate))
        samples.append(max(-32768, min(32767, value)))

    with wave.open(str(path), 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return path


def _generate_silence(path: Path, duration_s: float = 1.0):
    """Generate a silent WAV file."""
    return _generate_wav(path, duration_s=duration_s, amplitude=0)


class TestAudioPipelineIntegration:
    """Integration tests for save_recording mechanics (no sounddevice needed)."""

    def test_save_recording_produces_valid_wav(self):
        """Manually populate speech buffer and verify saved WAV is valid."""
        from whisper_voice_typing.audio import AudioPipeline
        from whisper_voice_typing.config import Config

        config = Config()
        pipeline = AudioPipeline(config)
        pipeline.temp_dir = Path(tempfile.mkdtemp())

        try:
            # simulate: begin_recording populates speech buffer with pre-roll
            # then accumulate adds more data
            pipeline._recording_start = 0.0
            # 1 second of fake audio (16000 samples * 2 bytes)
            pipeline._speech_buffer = bytearray(b"\x42" * 32000)

            wav_path = pipeline.save_recording()
            assert wav_path is not None
            assert wav_path.exists()
            assert wav_path.suffix == ".wav"

            # verify it's a valid WAV
            with wave.open(str(wav_path), 'rb') as wf:
                assert wf.getnchannels() == 1
                assert wf.getsampwidth() == 2
                assert wf.getframerate() == 16000
                assert wf.getnframes() == 16000

            wav_path.unlink()
        finally:
            import shutil
            shutil.rmtree(pipeline.temp_dir, ignore_errors=True)

    def test_save_recording_discards_small(self):
        """Audio smaller than min_file_size is discarded."""
        from whisper_voice_typing.audio import AudioPipeline
        from whisper_voice_typing.config import Config

        config = Config()
        pipeline = AudioPipeline(config)
        pipeline.temp_dir = Path(tempfile.mkdtemp())

        try:
            pipeline._recording_start = 0.0
            pipeline._speech_buffer = bytearray(b"\x42" * 100)  # way below min_file_size

            wav_path = pipeline.save_recording()
            assert wav_path is None
        finally:
            import shutil
            shutil.rmtree(pipeline.temp_dir, ignore_errors=True)

    def test_discard_recording_clears_buffer(self):
        from whisper_voice_typing.audio import AudioPipeline
        from whisper_voice_typing.config import Config

        config = Config()
        pipeline = AudioPipeline(config)
        pipeline._recording_start = 0.0
        pipeline._speech_buffer = bytearray(b"\x42" * 32000)

        pipeline.discard_recording()
        assert len(pipeline._speech_buffer) == 0
        assert pipeline._recording_start is None
