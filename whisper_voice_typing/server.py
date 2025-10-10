"""Whisper server management"""

import os
import signal
import time
import subprocess
from typing import Optional
import requests

from .utils import log, tlog


class WhisperServer:
    """Manages the whisper-server process"""

    def __init__(self, config):
        self.config = config
        self.process: Optional[subprocess.Popen] = None

    def is_running(self) -> bool:
        """Check if server is running and responsive"""
        # Check PID file
        if not self.config.server_pid_file.exists():
            log.debug("Server PID file not found")
            return False

        try:
            pid = int(self.config.server_pid_file.read_text().strip())
            log.debug(f"Server PID from file: {pid}")

            # Check if process exists
            try:
                os.kill(pid, 0)
            except OSError:
                log.debug(f"Process {pid} not running")
                self.config.server_pid_file.unlink(missing_ok=True)
                return False

            # Check if server is responsive
            try:
                response = requests.get(
                    f"http://{self.config.server_host}:{self.config.server_port}",
                    timeout=2
                )
                log.debug(f"Server health check: HTTP {response.status_code}")
                return True
            except requests.RequestException as e:
                log.debug(f"Server not responsive: {e}")
                return False

        except Exception as e:
            log.debug(f"Error checking server status: {e}")
            return False

    def start(self) -> bool:
        """Start the whisper server"""
        tlog.info("Starting Whisper server...")

        cmd = [
            str(self.config.server_binary),
            "-m", str(self.config.whisper_model),
            "-t", str(self.config.thread_count),
            "--no-timestamps",
            "--host", self.config.server_host,
            "--port", str(self.config.server_port),
            "--convert",
        ]

        log.debug(f"Starting server: {' '.join(cmd)}")

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )

            # Write PID file
            self.config.server_pid_file.write_text(str(self.process.pid))
            log.debug(f"Server started with PID {self.process.pid}")

            # Wait for server to be ready (max 10 seconds)
            for _ in range(50):
                try:
                    response = requests.get(
                        f"http://{self.config.server_host}:{self.config.server_port}",
                        timeout=1
                    )
                    tlog.success(f"Whisper server ready at http://{self.config.server_host}:{self.config.server_port}")
                    return True
                except requests.RequestException:
                    time.sleep(0.2)

            tlog.error("Failed to start Whisper server (timeout)")
            return False

        except Exception as e:
            tlog.error(f"Failed to start Whisper server: {e}")
            log.exception("Server start failed")
            return False

    def stop(self) -> None:
        """Stop the whisper server"""
        log.debug("Stopping whisper server")

        if self.config.server_pid_file.exists():
            try:
                pid = int(self.config.server_pid_file.read_text().strip())
                log.debug(f"Killing server PID {pid}")

                try:
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(1)

                    # Force kill if still running
                    try:
                        os.kill(pid, 0)
                        log.debug(f"Force killing PID {pid}")
                        os.kill(pid, signal.SIGKILL)
                    except OSError:
                        pass

                except OSError:
                    pass

            except Exception as e:
                log.debug(f"Error stopping server: {e}")

            self.config.server_pid_file.unlink(missing_ok=True)
