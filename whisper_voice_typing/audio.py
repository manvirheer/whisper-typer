"""Audio recording and transcription"""

import time
import tempfile
import shutil
import subprocess
from pathlib import Path
from typing import Optional
import requests

from .utils import log, tlog


class AudioProcessor:
    """Handles audio recording and transcription"""

    def __init__(self, config, server):
        self.config = config
        self.server = server
        self.temp_dir: Optional[Path] = None

    def setup_temp_dir(self) -> None:
        """Create secure temporary directory for audio files"""
        # Prefer /dev/shm (RAM) for speed
        base_dir = Path("/dev/shm") if Path("/dev/shm").exists() else Path("/tmp")

        self.temp_dir = Path(tempfile.mkdtemp(prefix="whisper_voice.", dir=base_dir))
        log.debug(f"Created temp directory: {self.temp_dir}")

    def cleanup_temp_dir(self) -> None:
        """Remove temporary directory"""
        if self.temp_dir and self.temp_dir.exists():
            log.debug(f"Cleaning up temp directory: {self.temp_dir}")
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def record_audio(self) -> Optional[Path]:
        """Record audio with silence detection. Returns path to audio file or None."""
        audio_file = self.temp_dir / f"{time.time_ns()}.wav"

        # Build rec command
        cmd = ["rec"]
        if self.config.headphone_mic:
            if self.config.headphone_mic != "default":
                cmd.extend(["-t", "pulseaudio", self.config.headphone_mic])

        cmd.extend([
            "-q",  # Quiet mode
            str(audio_file),
            "silence",
            "1", str(self.config.silence_start_duration), self.config.silence_start_threshold,
            "1", str(self.config.silence_end_duration), self.config.silence_end_threshold,
            "trim", "0", str(self.config.max_recording_duration)
        ])

        log.debug(f"Recording command: {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=40)

            if result.returncode != 0:
                log.debug(f"Recording failed with exit code {result.returncode}")
                audio_file.unlink(missing_ok=True)
                return None

            # Check file size
            if audio_file.exists():
                file_size = audio_file.stat().st_size
                log.debug(f"Recorded {file_size} bytes")

                if file_size >= self.config.min_file_size:
                    tlog.info(f"Recorded {file_size} bytes")
                    return audio_file
                else:
                    tlog.warn(f"Recording too small ({file_size} bytes < {self.config.min_file_size} bytes), discarding")
                    log.debug(f"File too small ({file_size} < {self.config.min_file_size}), discarding")
                    audio_file.unlink()
                    return None

            return None

        except subprocess.TimeoutExpired:
            log.debug("Recording timeout")
            audio_file.unlink(missing_ok=True)
            return None
        except Exception as e:
            log.exception(f"Recording error: {e}")
            audio_file.unlink(missing_ok=True)
            return None

    def transcribe_via_server(self, audio_file: Path) -> Optional[str]:
        """Transcribe audio using whisper server. Returns text or None."""
        log.debug(f"Transcribing via server: {audio_file}")
        start_time = time.time()

        try:
            with open(audio_file, 'rb') as f:
                files = {'file': f}
                response = requests.post(
                    f"http://{self.config.server_host}:{self.config.server_port}/inference",
                    files=files,
                    timeout=10
                )

            duration_ms = int((time.time() - start_time) * 1000)
            log.debug(f"Server response: HTTP {response.status_code} in {duration_ms}ms")

            if response.status_code == 200:
                data = response.json()
                text = data.get('text', '').strip()
                log.debug(f"Transcribed text: '{text}'")
                if text and text != "[BLANK_AUDIO]":
                    return text
                else:
                    tlog.warn("Server returned blank/empty audio")
                    return None
            else:
                tlog.warn(f"Server returned HTTP {response.status_code}")
                log.debug(f"Server returned error: {response.status_code}")
                return None

        except Exception as e:
            log.debug(f"Server transcription failed: {e}")
            return None

    def transcribe_direct(self, audio_file: Path) -> Optional[str]:
        """Transcribe audio directly using whisper CLI. Returns text or None."""
        log.debug(f"Transcribing directly: {audio_file}")
        start_time = time.time()

        cmd = [
            str(self.config.whisper_executable),
            "-m", str(self.config.whisper_model),
            "-f", str(audio_file),
            "-t", str(self.config.thread_count),
            "--no-timestamps",
            "--no-prints"
        ]

        log.debug(f"Direct command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if result.returncode == 0:
                text = result.stdout.strip()
                log.debug(f"Transcribed text in {duration_ms}ms: '{text}'")
                if text and text != "[BLANK_AUDIO]":
                    return text
                else:
                    tlog.warn("Whisper returned blank/empty audio")
                    return None
            else:
                tlog.warn(f"Whisper failed with exit code {result.returncode}")
                log.debug(f"Direct transcription failed with exit code {result.returncode}")
                return None

        except Exception as e:
            log.exception(f"Direct transcription error: {e}")
            return None

    def process_audio(self, audio_file: Path) -> bool:
        """Process audio file and type the result. Returns True if successful."""
        start_time = time.time()

        # Try server mode first
        text = None
        mode = "server"

        if not self.server.is_running():
            tlog.info("Server not running, starting...")
            if not self.server.start():
                tlog.warn("Server failed, using direct mode")
                mode = "direct"

        if mode == "server":
            text = self.transcribe_via_server(audio_file)
            if text is None:
                tlog.warn("Server request failed, falling back to direct mode")
                mode = "direct"
                text = self.transcribe_direct(audio_file)
        else:
            text = self.transcribe_direct(audio_file)

        if text:
            duration_ms = int((time.time() - start_time) * 1000)
            tlog.success(f"Transcribed in {duration_ms}ms via {mode}")

            # Type the text
            try:
                subprocess.run(
                    ["xdotool", "type", "--delay", "1", "--clearmodifiers", "--", text],
                    check=True,
                    timeout=10
                )
                return True
            except Exception as e:
                log.exception(f"Failed to type text: {e}")
                return False

        return False
