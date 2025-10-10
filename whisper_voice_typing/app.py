"""Main application logic"""

import os
import sys
import signal
import time
from pathlib import Path

from .config import Config
from .server import WhisperServer
from .audio import AudioProcessor
from .utils import log, tlog, setup_gpu_environment


class WhisperVoiceTyping:
    """Main application class"""

    def __init__(self):
        self.config = Config()
        self.server = WhisperServer(self.config)
        self.processor = AudioProcessor(self.config, self.server)
        self.running = False
        self.script_pid_file = Path("/tmp/whisper_voice_typing.pid")

    def check_single_instance(self) -> None:
        """Ensure only one instance is running"""
        if self.script_pid_file.exists():
            try:
                pid = int(self.script_pid_file.read_text().strip())
                try:
                    os.kill(pid, 0)
                    tlog.error(f"Whisper Voice Typing is already running (PID: {pid})")
                    tlog.info(f"Kill it first with: kill {pid}")
                    tlog.footer()
                    sys.exit(1)
                except OSError:
                    # Stale PID file
                    self.script_pid_file.unlink()
            except Exception:
                self.script_pid_file.unlink()

        # Write our PID
        self.script_pid_file.write_text(str(os.getpid()))

    def cleanup(self, signum=None, frame=None) -> None:
        """Cleanup and exit"""
        if not self.running:
            return

        self.running = False
        print()
        tlog.info("Exiting Whisper Voice Typing")
        tlog.footer()

        log.debug("Cleaning up...")
        self.server.stop()
        self.processor.cleanup_temp_dir()
        self.script_pid_file.unlink(missing_ok=True)

        time.sleep(0.2)
        sys.exit(0)

    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown"""
        signal.signal(signal.SIGINT, self.cleanup)
        signal.signal(signal.SIGTERM, self.cleanup)

    def run(self) -> None:
        """Main application loop"""
        # Validate configuration
        self.config.validate(tlog)

        # Check single instance
        self.check_single_instance()

        # Setup signal handlers
        self.setup_signal_handlers()

        # Setup GPU environment
        setup_gpu_environment(self.config)

        # Setup temp directory
        self.processor.setup_temp_dir()

        # Start server
        if not self.server.is_running():
            self.server.start()

        # Display configuration info
        tlog.info("Whisper Voice Typing activated")
        if self.config.headphone_mic and self.config.headphone_mic != "default":
            tlog.info(f"Using mic: {self.config.headphone_mic}")
        tlog.info("Listening... (Press Ctrl+C to exit)")

        self.running = True

        # Main loop
        while self.running:
            try:
                tlog.status("Listening...")

                # Record audio
                audio_file = self.processor.record_audio()

                if audio_file:
                    tlog.status("Audio recorded, processing...")
                    success = self.processor.process_audio(audio_file)

                    # Cleanup audio file
                    audio_file.unlink(missing_ok=True)

                    if success:
                        tlog.status("Processing complete, waiting before next recording...")
                        time.sleep(self.config.post_processing_delay)
                else:
                    # No audio detected, brief pause
                    time.sleep(self.config.no_audio_delay)

            except Exception as e:
                log.exception(f"Error in main loop: {e}")
                time.sleep(1)
