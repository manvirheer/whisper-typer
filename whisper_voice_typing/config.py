import os, shutil, sys
from pathlib import Path
from dataclasses import dataclass, field

from .utils import is_macos

def _find_whisper_dir() -> Path:
    if d := os.environ.get("WHISPER_CPP_DIR"): return Path(d).expanduser()
    for candidate in [Path.home() / ".local/share/whisper.cpp", Path.home() / "whisper.cpp", Path.home() / "personal/whisper.cpp"]:
        if candidate.exists(): return candidate
    return Path.home() / ".local/share/whisper.cpp"

@dataclass
class Config:
    whisper_dir: Path = field(default_factory=_find_whisper_dir)
    headphone_mic: str = field(default_factory=lambda: os.environ.get("WHISPER_MIC", ""))

    whisper_executable: Path = field(init=False)
    whisper_model: Path = field(init=False)
    server_binary: Path = field(init=False)

    sample_rate: int = 16000
    channels: int = 1
    bit_depth: int = 16

    server_host: str = "127.0.0.1"
    server_port: int = 8080
    server_pid_file: Path = Path("/tmp/whisper_server.pid")

    silence_start_duration: float = 0.05   # fast trigger to avoid clipping speech onset
    silence_start_threshold: str = "1.5%"
    silence_end_duration: float = 2.0
    silence_end_threshold: str = "1%"      # low so quiet trailing words aren't cut
    max_recording_duration: int = 30
    min_file_size: int = 8192              # ~0.25s of audio

    thread_count: int = field(default_factory=lambda: min(os.cpu_count() or 4, 8))
    post_processing_delay: float = 1.0
    no_audio_delay: float = 0.1

    def __post_init__(self):
        self.whisper_executable = self.whisper_dir / "build/bin/whisper-cli"
        model_env = os.environ.get("WHISPER_MODEL")
        self.whisper_model = Path(model_env) if model_env else self.whisper_dir / "models/ggml-large-v3-turbo.bin"
        self.server_binary = self.whisper_dir / "build/bin/whisper-server"

    def validate(self, tlog) -> None:
        errors = []
        if not self.whisper_executable.exists(): errors.append(f"whisper-cli not found: {self.whisper_executable}")
        if not self.server_binary.exists(): errors.append(f"whisper-server not found: {self.server_binary}")
        if not self.whisper_model.exists(): errors.append(f"model not found: {self.whisper_model}")

        required = ['rec', 'ffmpeg', 'osascript', 'curl'] if is_macos() else ['rec', 'xdotool', 'curl', 'jq']
        for cmd in required:
            if not shutil.which(cmd): errors.append(f"command not found: {cmd}")

        if errors:
            for e in errors: tlog.error(e)
            tlog.footer()
            sys.exit(1)
