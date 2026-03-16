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

    # audio
    sample_rate: int = 16000
    channels: int = 1
    bit_depth: int = 16

    # whisper server
    server_host: str = "127.0.0.1"
    server_port: int = 8080
    server_pid_file: Path = Path("/tmp/whisper_server.pid")

    # sox silence detection (legacy)
    silence_start_duration: float = 0.05
    silence_start_threshold: str = "1.5%"
    silence_end_duration: float = 2.0
    silence_end_threshold: str = "1%"

    # recording
    max_recording_duration: int = 30
    min_file_size: int = 8192

    # VAD
    vad_threshold: float = 0.5
    vad_confirmation_ms: int = 96         # ~3 frames at 32ms each
    vad_silence_ms: int = 1200            # initial silence timeout, adapts at runtime
    vad_silence_min_ms: int = 800         # fastest adaptive timeout
    vad_silence_max_ms: int = 2500        # slowest adaptive timeout
    pre_roll_ms: int = 500

    # menu bar
    menu_update_interval: float = 0.1
    transcription_history_size: int = 5

    # general
    thread_count: int = field(default_factory=lambda: min(os.cpu_count() or 4, 8))
    post_processing_delay: float = 1.0
    no_audio_delay: float = 0.1

    # LaunchAgent
    launchagent_label: str = "com.whisper-typer"
    launchagent_dir: Path = field(default_factory=lambda: Path.home() / "Library/LaunchAgents")
    log_dir: Path = field(default_factory=lambda: Path.home() / ".local/share/whisper-typer/logs")

    def __post_init__(self):
        self.whisper_executable = self.whisper_dir / "build/bin/whisper-cli"
        model_env = os.environ.get("WHISPER_MODEL")
        self.whisper_model = Path(model_env) if model_env else self.whisper_dir / "models/ggml-large-v3-turbo.bin"
        self.server_binary = self.whisper_dir / "build/bin/whisper-server"

    @property
    def launchagent_plist(self) -> Path:
        return self.launchagent_dir / f"{self.launchagent_label}.plist"

    def validate(self, tlog, use_new_pipeline: bool = True) -> None:
        errors = []
        if not self.whisper_executable.exists(): errors.append(f"whisper-cli not found: {self.whisper_executable}")
        if not self.server_binary.exists(): errors.append(f"whisper-server not found: {self.server_binary}")
        if not self.whisper_model.exists(): errors.append(f"model not found: {self.whisper_model}")

        if use_new_pipeline and is_macos():
            try: import sounddevice  # noqa: F401
            except ImportError: errors.append("sounddevice not installed: pip install whisper-typer[macos]")
        else:
            for cmd in (['rec', 'ffmpeg', 'osascript'] if is_macos() else ['rec', 'xdotool']):
                if not shutil.which(cmd): errors.append(f"command not found: {cmd}")

        if errors:
            for e in errors: tlog.error(e)
            tlog.footer()
            sys.exit(1)
