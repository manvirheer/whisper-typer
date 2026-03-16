import os, sys
from pathlib import Path
from dataclasses import dataclass, field


def _find_whisper_dir() -> Path:
    if d := os.environ.get("WHISPER_CPP_DIR"): return Path(d).expanduser()
    for candidate in [Path.home() / ".local/share/whisper.cpp", Path.home() / "whisper.cpp"]:
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

    def validate(self, tlog) -> None:
        errors = []
        if not self.whisper_executable.exists() or not self.server_binary.exists():
            errors.append("whisper.cpp not set up. Run: ./setup.sh")
        if not self.whisper_model.exists():
            errors.append(f"model not found: {self.whisper_model}. Run: ./setup.sh")

        try: import sounddevice  # noqa: F401
        except ImportError: errors.append("sounddevice not installed. Run: ./setup.sh")

        if errors:
            for e in errors: tlog.error(e)
            tlog.footer()
            sys.exit(1)
