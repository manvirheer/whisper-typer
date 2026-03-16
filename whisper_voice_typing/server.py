import os, signal, time, subprocess
from pathlib import Path
import requests

from .utils import log, tlog


class WhisperServer:
    def __init__(self, config):
        self.config = config
        self.process: subprocess.Popen | None = None
        self._transcribe_fails = 0
        self._backoff_delay = 1.0
        self._max_backoff = 30.0

    def is_running(self) -> bool:
        if not self.config.server_pid_file.exists(): return False
        try:
            pid = int(self.config.server_pid_file.read_text().strip())
            try: os.kill(pid, 0)
            except OSError:
                self.config.server_pid_file.unlink(missing_ok=True)
                return False
            requests.get(f"http://{self.config.server_host}:{self.config.server_port}", timeout=2)
            return True
        except Exception:
            return False

    def start(self) -> bool:
        tlog.info("Starting whisper server...")
        cmd = [
            str(self.config.server_binary),
            "-m", str(self.config.whisper_model),
            "-t", str(self.config.thread_count),
            "--no-timestamps",
            "--host", self.config.server_host,
            "--port", str(self.config.server_port),
            "--convert", "--flash-attn",
        ]
        try:
            self.process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            self.config.server_pid_file.write_text(str(self.process.pid))
            for _ in range(50):
                try:
                    requests.get(f"http://{self.config.server_host}:{self.config.server_port}", timeout=1)
                    tlog.success(f"Whisper server ready at :{self.config.server_port}")
                    self._backoff_delay = 1.0
                    return True
                except requests.RequestException:
                    time.sleep(0.2)
            tlog.error("Server start timed out")
            return False
        except Exception as e:
            tlog.error(f"Server start failed: {e}")
            return False

    def stop(self) -> None:
        if not self.config.server_pid_file.exists(): return
        try:
            pid = int(self.config.server_pid_file.read_text().strip())
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(1)
                try: os.kill(pid, 0); os.kill(pid, signal.SIGKILL)
                except OSError: pass
            except OSError: pass
        except Exception: pass
        self.config.server_pid_file.unlink(missing_ok=True)

    def transcribe(self, audio_file: Path) -> str | None:
        start = time.time()

        if self._transcribe_fails >= 3:
            tlog.warn(f"Multiple failures, restarting server (backoff {self._backoff_delay:.0f}s)...")
            self.stop()
            self._transcribe_fails = 0
            time.sleep(self._backoff_delay)
            self._backoff_delay = min(self._backoff_delay * 2, self._max_backoff)

        text, mode = None, "server"
        if not self.is_running():
            tlog.info("Server not running, starting...")
            if not self.start():
                tlog.warn("Server failed, using direct mode")
                mode = "direct"

        if mode == "server":
            text = self._transcribe_via_server(audio_file)
            if text is None:
                tlog.warn("Server failed, falling back to direct mode")
                mode = "direct"
                text = self._transcribe_direct(audio_file)
        else:
            text = self._transcribe_direct(audio_file)

        if text:
            tlog.success(f"Transcribed in {int((time.time() - start) * 1000)}ms via {mode}")
            self._backoff_delay = 1.0
        return text

    def _transcribe_via_server(self, audio_file: Path) -> str | None:
        try:
            with open(audio_file, 'rb') as f:
                resp = requests.post(
                    f"http://{self.config.server_host}:{self.config.server_port}/inference",
                    files={'file': f}, timeout=10,
                )
            if resp.status_code == 200:
                try:
                    text = resp.json().get('text', '').strip()
                except (ValueError, requests.exceptions.JSONDecodeError):
                    self._transcribe_fails += 1
                    log.warning(f"Server returned invalid JSON: {resp.text[:200]}")
                    return None
                if text and text != "[BLANK_AUDIO]":
                    self._transcribe_fails = 0
                    return text
                tlog.warn("Server returned blank audio")
                return None
            self._transcribe_fails += 1
            tlog.warn(f"Server HTTP {resp.status_code}")
            return None
        except requests.RequestException as e:
            self._transcribe_fails += 1
            log.warning(f"Server request failed: {e}")
            return None

    def _transcribe_direct(self, audio_file: Path) -> str | None:
        cmd = [str(self.config.whisper_executable), "-m", str(self.config.whisper_model),
               "-f", str(audio_file), "-t", str(self.config.thread_count),
               "--no-timestamps", "--no-prints", "--flash-attn"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                text = result.stdout.strip()
                if text and text != "[BLANK_AUDIO]": return text
                tlog.warn("Whisper returned blank audio")
                return None
            tlog.warn(f"Whisper exit code {result.returncode}")
            return None
        except Exception as e:
            log.exception(f"Direct transcription error: {e}")
            return None
