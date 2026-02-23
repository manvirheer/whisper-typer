import os, sys, signal, time
from pathlib import Path

from .config import Config
from .server import WhisperServer
from .audio import AudioProcessor
from .utils import log, tlog, setup_gpu_environment

class WhisperVoiceTyping:
    def __init__(self):
        self.config = Config()
        self.server = WhisperServer(self.config)
        self.processor = AudioProcessor(self.config, self.server)
        self.running = False
        self.pid_file = Path("/tmp/whisper_voice_typing.pid")

    def _check_single_instance(self) -> None:
        if self.pid_file.exists():
            try:
                pid = int(self.pid_file.read_text().strip())
                try:
                    os.kill(pid, 0)
                    tlog.error(f"Already running (PID {pid}). Kill it: kill {pid}")
                    tlog.footer()
                    sys.exit(1)
                except OSError:
                    self.pid_file.unlink()
            except Exception:
                self.pid_file.unlink()
        self.pid_file.write_text(str(os.getpid()))

    def _cleanup(self, signum=None, frame=None) -> None:
        if not self.running: return
        self.running = False
        print()
        tlog.info("Exiting whisper-typer")
        tlog.footer()
        self.server.stop()
        self.processor.cleanup_temp_dir()
        self.pid_file.unlink(missing_ok=True)
        time.sleep(0.2)
        sys.exit(0)

    def run(self) -> None:
        self.config.validate(tlog)
        self._check_single_instance()
        signal.signal(signal.SIGINT, self._cleanup)
        signal.signal(signal.SIGTERM, self._cleanup)
        setup_gpu_environment(self.config)
        self.processor.setup_temp_dir()

        if not self.server.is_running(): self.server.start()

        tlog.info("whisper-typer activated")
        tlog.info(f"Threads: {self.config.thread_count}")
        if self.config.headphone_mic and self.config.headphone_mic != "default":
            tlog.info(f"Mic: {self.config.headphone_mic}")
        tlog.info("Listening... (Ctrl+C to exit)")

        self.running = True
        errors = 0
        while self.running:
            try:
                tlog.status("Listening...")
                audio_file = self.processor.record_audio()
                if audio_file:
                    tlog.status("Processing...")
                    if self.processor.process_audio(audio_file):
                        errors = 0
                        tlog.status("Done, waiting...")
                        time.sleep(self.config.post_processing_delay)
                    audio_file.unlink(missing_ok=True)
                else:
                    time.sleep(self.config.no_audio_delay)
            except KeyboardInterrupt:
                break
            except Exception as e:
                errors += 1
                log.exception(f"Main loop error: {e}")
                if errors >= 10:
                    tlog.error("Too many errors, restarting server...")
                    self.server.stop()
                    time.sleep(2)
                    self.server.start()
                    errors = 0
                else:
                    time.sleep(1)
