"""Configuration management for Whisper Voice Typing"""

import shutil
from pathlib import Path
from dataclasses import dataclass


@dataclass
class Config:
    """Configuration for Whisper Voice Typing"""

    # Audio device - Leave empty for default, or specify like "bluez_input.AC:BF:71:CF:17:EF"
    # Find with: pactl list short sources
    headphone_mic: str = ""

    # Whisper.cpp paths
    whisper_dir: Path = Path.home() / "personal" / "whisper.cpp"
    whisper_executable: Path = whisper_dir / "build/bin/whisper-cli"
    whisper_model: Path = whisper_dir / "models/ggml-large-v3.bin"

    # Audio parameters (optimized for Whisper)
    sample_rate: int = 16000
    channels: int = 1
    bit_depth: int = 16

    # Server configuration
    server_host: str = "127.0.0.1"
    server_port: int = 8080
    server_binary: Path = whisper_dir / "build/bin/whisper-server"
    server_pid_file: Path = Path("/tmp/whisper_server.pid")

    # Recording parameters
    # Wait 0.2s of audio above 2% volume to start recording (less aggressive)
    silence_start_duration: float = 0.2
    silence_start_threshold: str = "2%"
    # Stop after 2.0s of silence below 2% volume (give more time for pauses)
    silence_end_duration: float = 2.0
    silence_end_threshold: str = "2%"
    # Maximum recording duration (30 seconds)
    max_recording_duration: int = 30
    # Minimum file size: 8KB = ~0.25 seconds of audio (lower threshold)
    min_file_size: int = 8192

    # Performance settings
    thread_count: int = 4

    # Timing
    post_processing_delay: float = 1.0  # Wait after typing to avoid re-recording
    no_audio_delay: float = 0.1  # Brief pause when no audio detected

    def validate(self, tlog) -> None:
        """Validate configuration and check dependencies"""
        errors = []

        # Check required executables
        if not self.whisper_executable.exists():
            errors.append(f"Whisper executable not found: {self.whisper_executable}")
        if not self.server_binary.exists():
            errors.append(f"Whisper server not found: {self.server_binary}")
        if not self.whisper_model.exists():
            errors.append(f"Whisper model not found: {self.whisper_model}")

        # Check required commands
        for cmd in ['rec', 'xdotool', 'curl', 'jq']:
            if not shutil.which(cmd):
                errors.append(f"Required command not found: {cmd}")

        if errors:
            for error in errors:
                tlog.error(error)
            tlog.footer()
            import sys
            sys.exit(1)
