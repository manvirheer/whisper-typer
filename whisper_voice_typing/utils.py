import os, sys, platform, logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path

def is_macos() -> bool: return platform.system() == "Darwin"

def _setup_logging() -> logging.Logger:
    """Configure logging: file handler for background mode, stream for terminal."""
    logger = logging.getLogger("whisper_voice_typing")
    logger.setLevel(logging.DEBUG)

    # always add a stream handler if stdout is a tty
    if hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
        fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    else:
        # background mode: log to file
        log_dir = Path.home() / ".local/share/whisper-typer/logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        fh = RotatingFileHandler(log_dir / "whisper-typer.log", maxBytes=5_000_000, backupCount=2)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger

log = _setup_logging()

class TableLogger:
    def __init__(self): self.header_printed = False

    def _header(self):
        if not self.header_printed:
            print("-" * 80)
            print(f"{'TIME':<10} | {'LEVEL':<8} | {'MESSAGE':<57}")
            print("-" * 80)
            self.header_printed = True

    def _fmt(self, level: str, msg: str):
        self._header()
        print(f"{datetime.now().strftime('%H:%M:%S'):<10} | {level:<8} | {msg}")

    def info(self, msg: str): self._fmt("INFO", msg)
    def success(self, msg: str): self._fmt("SUCCESS", msg)
    def warn(self, msg: str): self._fmt("WARN", msg)
    def error(self, msg: str): self._fmt("ERROR", msg)
    def status(self, msg: str): self._fmt("STATUS", msg)
    def footer(self): print("-" * 80)

tlog = TableLogger()

def setup_gpu_environment(config) -> None:
    os.environ["OMP_NUM_THREADS"] = str(config.thread_count)
