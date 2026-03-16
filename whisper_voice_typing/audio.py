"""
Audio capture: sounddevice + ring buffer + frame queue.

  sounddevice callback --> ring buffer (30.5s, for pre-roll)
                       +-> frame queue (for VAD, each frame exactly once)

  Ring buffer pre-roll on VAD trigger:
  [...old audio...][500ms pre-roll][VAD HERE][...speech...]
                    ^               ^
                    save starts     detection
"""

import queue, time, tempfile, shutil, wave, subprocess, threading
from pathlib import Path
from .utils import log, tlog, is_macos


class RingBuffer:
    """Thread-safe circular buffer for raw PCM audio."""

    def __init__(self, capacity_seconds: float, sample_rate: int = 16000, bytes_per_sample: int = 2):
        self._capacity = int(capacity_seconds * sample_rate * bytes_per_sample)
        self._buffer = bytearray(self._capacity)
        self._write_pos = 0
        self._total_written = 0
        self._lock = threading.Lock()

    @property
    def capacity_bytes(self) -> int:
        return self._capacity

    def write(self, data: bytes) -> None:
        n = len(data)
        with self._lock:
            if n >= self._capacity:
                self._buffer[:] = data[-self._capacity:]
                self._write_pos = 0
                self._total_written += n
                return
            end = self._write_pos + n
            if end <= self._capacity:
                self._buffer[self._write_pos:end] = data
            else:
                first = self._capacity - self._write_pos
                self._buffer[self._write_pos:] = data[:first]
                self._buffer[:n - first] = data[first:]
            self._write_pos = end % self._capacity
            self._total_written += n

    def read_last(self, num_bytes: int) -> bytes:
        with self._lock:
            available = min(num_bytes, self._total_written, self._capacity)
            if available == 0:
                return b""
            start = (self._write_pos - available) % self._capacity
            if start < self._write_pos:
                return bytes(self._buffer[start:self._write_pos])
            return bytes(self._buffer[start:]) + bytes(self._buffer[:self._write_pos])

    def read_all(self) -> bytes:
        return self.read_last(self._capacity)

    def clear(self) -> None:
        with self._lock:
            self._write_pos = 0
            self._total_written = 0


class AudioPipeline:
    def __init__(self, config):
        self.config = config
        self._stream = None
        self._ring_buffer = RingBuffer(
            capacity_seconds=config.max_recording_duration + (config.pre_roll_ms / 1000.0),
            sample_rate=config.sample_rate,
        )
        self._frame_queue: queue.Queue[bytes] = queue.Queue(maxsize=100)
        self._recording_start: float | None = None
        self._speech_buffer = bytearray()
        self._pre_roll_bytes = int(config.pre_roll_ms / 1000.0 * config.sample_rate * 2)
        self.temp_dir: Path | None = None

    def setup_temp_dir(self) -> None:
        base = Path("/dev/shm") if not is_macos() and Path("/dev/shm").exists() else Path("/tmp")
        self.temp_dir = Path(tempfile.mkdtemp(prefix="whisper_voice.", dir=base))

    def cleanup_temp_dir(self) -> None:
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def start(self) -> None:
        import sounddevice as sd
        device = None
        if self.config.headphone_mic and self.config.headphone_mic != "default":
            device = self.config.headphone_mic
        self._stream = sd.RawInputStream(
            samplerate=self.config.sample_rate, channels=self.config.channels,
            dtype="int16", blocksize=int(self.config.sample_rate * 0.1),
            device=device, callback=self._audio_callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            try: self._stream.stop(); self._stream.close()
            except Exception: pass
            self._stream = None

    def is_active(self) -> bool:
        return self._stream is not None and self._stream.active

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            log.warning(f"Audio status: {status}")
        data = bytes(indata)
        self._ring_buffer.write(data)
        try: self._frame_queue.put_nowait(data)
        except queue.Full: pass

    def next_frame(self, timeout: float = 0.2) -> bytes | None:
        try: return self._frame_queue.get(timeout=timeout)
        except queue.Empty: return None

    def begin_recording(self) -> None:
        self._recording_start = time.time()
        self._speech_buffer = bytearray(self._ring_buffer.read_last(self._pre_roll_bytes))

    def accumulate(self, frame: bytes) -> None:
        self._speech_buffer.extend(frame)

    def recording_duration(self) -> float:
        return time.time() - self._recording_start if self._recording_start else 0.0

    def save_recording(self) -> Path | None:
        if not self._speech_buffer or not self.temp_dir:
            return None
        if len(self._speech_buffer) < self.config.min_file_size:
            tlog.warn(f"Too small ({len(self._speech_buffer)}B), discarding")
            self._speech_buffer.clear()
            self._recording_start = None
            return None

        audio_file = self.temp_dir / f"{time.time_ns()}.wav"
        try:
            with wave.open(str(audio_file), 'wb') as wf:
                wf.setnchannels(self.config.channels)
                wf.setsampwidth(self.config.bit_depth // 8)
                wf.setframerate(self.config.sample_rate)
                wf.writeframes(bytes(self._speech_buffer))
            tlog.info(f"Recorded {len(self._speech_buffer)} bytes ({self.recording_duration():.1f}s)")
        except OSError as e:
            log.error(f"Failed to save recording: {e}")
            self._speech_buffer.clear()
            self._recording_start = None
            return None

        self._speech_buffer.clear()
        self._recording_start = None
        return audio_file

    def discard_recording(self) -> None:
        self._speech_buffer.clear()
        self._recording_start = None

    def restart_stream(self) -> bool:
        tlog.info("Restarting audio stream...")
        self.stop()
        try:
            time.sleep(0.5)
            self.start()
            return True
        except Exception as e:
            log.error(f"Failed to restart: {e}")
            return False


# --- Legacy path (Linux / fallback) ---

class LegacyAudioProcessor:
    def __init__(self, config, server):
        self.config, self.server = config, server
        self.temp_dir: Path | None = None
        self._rec_fails = 0

    def setup_temp_dir(self) -> None:
        base = Path("/dev/shm") if not is_macos() and Path("/dev/shm").exists() else Path("/tmp")
        self.temp_dir = Path(tempfile.mkdtemp(prefix="whisper_voice.", dir=base))

    def cleanup_temp_dir(self) -> None:
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _cleanup_stale(self) -> None:
        if not self.temp_dir or not self.temp_dir.exists(): return
        now = time.time()
        for f in self.temp_dir.glob("*.wav"):
            try:
                if now - f.stat().st_mtime > 60: f.unlink()
            except OSError: pass

    def record_audio(self) -> Path | None:
        self._cleanup_stale()
        audio_file = self.temp_dir / f"{time.time_ns()}.wav"
        timeout = self.config.max_recording_duration + 10
        return self._record_macos(audio_file, timeout) if is_macos() else self._record_linux(audio_file, timeout)

    def _record_macos(self, audio_file: Path, timeout: int) -> Path | None:
        device = f":{self.config.headphone_mic}" if (self.config.headphone_mic and self.config.headphone_mic != "default") else ":default"
        ffmpeg_cmd = ["ffmpeg", "-nostdin", "-f", "avfoundation", "-i", device,
                      "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le", "-flush_packets", "1", "-f", "s16le", "-loglevel", "error", "pipe:1"]
        sox_cmd = ["sox", "-q", "-t", "raw", "-r", "16000", "-e", "signed-integer", "-b", "16", "-c", "1", "-", str(audio_file),
                   "silence", "1", str(self.config.silence_start_duration), self.config.silence_start_threshold,
                   "1", str(self.config.silence_end_duration), self.config.silence_end_threshold,
                   "trim", "0", str(self.config.max_recording_duration), "pad", "0.3", "0.3"]
        ffmpeg_proc, sox_proc = None, None
        try:
            ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            sox_proc = subprocess.Popen(sox_cmd, stdin=ffmpeg_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            ffmpeg_proc.stdout.close()
            sox_proc.wait(timeout=timeout)
            ffmpeg_proc.terminate()
            try: ffmpeg_proc.wait(timeout=2)
            except subprocess.TimeoutExpired: ffmpeg_proc.kill(); ffmpeg_proc.wait()
            if sox_proc.returncode != 0:
                self._rec_fails += 1
                if self._rec_fails >= 3: tlog.warn(f"Recording failed {self._rec_fails}x")
                audio_file.unlink(missing_ok=True)
                return None
            return self._check_audio(audio_file)
        except subprocess.TimeoutExpired:
            self._rec_fails += 1
            if sox_proc: sox_proc.kill(); sox_proc.wait()
            if ffmpeg_proc: ffmpeg_proc.kill(); ffmpeg_proc.wait()
            if self._rec_fails >= 3: tlog.warn(f"No audio for {self._rec_fails} cycles")
            audio_file.unlink(missing_ok=True)
            return None
        except Exception as e:
            self._rec_fails += 1
            log.exception(f"Recording error: {e}")
            if sox_proc and sox_proc.poll() is None: sox_proc.kill()
            if ffmpeg_proc and ffmpeg_proc.poll() is None: ffmpeg_proc.kill()
            audio_file.unlink(missing_ok=True)
            return None

    def _record_linux(self, audio_file: Path, timeout: int) -> Path | None:
        cmd = ["rec"]
        if self.config.headphone_mic and self.config.headphone_mic != "default":
            cmd.extend(["-t", "pulseaudio", self.config.headphone_mic])
        cmd.extend(["-q", str(audio_file), "silence",
                    "1", str(self.config.silence_start_duration), self.config.silence_start_threshold,
                    "1", str(self.config.silence_end_duration), self.config.silence_end_threshold,
                    "trim", "0", str(self.config.max_recording_duration), "pad", "0.3", "0.3"])
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=timeout)
            if result.returncode != 0:
                self._rec_fails += 1
                if self._rec_fails >= 3:
                    tlog.warn(f"Recording failed {self._rec_fails}x: {result.stderr.decode(errors='replace')[:120]}")
                audio_file.unlink(missing_ok=True)
                return None
            return self._check_audio(audio_file)
        except subprocess.TimeoutExpired:
            self._rec_fails += 1
            if self._rec_fails >= 3: tlog.warn(f"No audio for {self._rec_fails} cycles")
            audio_file.unlink(missing_ok=True)
            return None
        except Exception as e:
            self._rec_fails += 1
            log.exception(f"Recording error: {e}")
            audio_file.unlink(missing_ok=True)
            return None

    def _check_audio(self, audio_file: Path) -> Path | None:
        if not audio_file.exists(): return None
        size = audio_file.stat().st_size
        if size >= self.config.min_file_size:
            self._rec_fails = 0
            tlog.info(f"Recorded {size} bytes")
            return audio_file
        tlog.warn(f"Too small ({size}B), discarding")
        audio_file.unlink()
        return None

    def process_audio(self, audio_file: Path) -> bool:
        from .typer import type_text
        text = self.server.transcribe(audio_file)
        return type_text(text) if text else False
