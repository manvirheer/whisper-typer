import os, signal, time, subprocess
import requests

from .utils import log, tlog

class WhisperServer:
    def __init__(self, config):
        self.config = config
        self.process: subprocess.Popen | None = None

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
