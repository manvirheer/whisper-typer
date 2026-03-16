import os, sys, logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from pathlib import Path



def _setup_logging() -> logging.Logger:
    logger = logging.getLogger("whisper_voice_typing")
    logger.setLevel(logging.DEBUG)

    if hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        logger.addHandler(sh)
    else:
        log_dir = Path.home() / ".local/share/whisper-typer/logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(log_dir / "whisper-typer.log", maxBytes=5_000_000, backupCount=2)
        fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
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

    def info(self, msg): self._fmt("INFO", msg)
    def success(self, msg): self._fmt("SUCCESS", msg)
    def warn(self, msg): self._fmt("WARN", msg)
    def error(self, msg): self._fmt("ERROR", msg)
    def status(self, msg): self._fmt("STATUS", msg)
    def footer(self): print("-" * 80)


tlog = TableLogger()


def setup_gpu_environment(config) -> None:
    os.environ["OMP_NUM_THREADS"] = str(config.thread_count)
