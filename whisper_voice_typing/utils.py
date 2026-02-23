import os, platform, logging
from datetime import datetime

def is_macos() -> bool: return platform.system() == "Darwin"

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("whisper_voice_typing")

class TableLogger:
    def __init__(self): self.header_printed = False

    def _header(self):
        if not self.header_printed:
            print("─" * 80)
            print(f"{'TIME':<10} │ {'LEVEL':<8} │ {'MESSAGE':<57}")
            print("─" * 80)
            self.header_printed = True

    def _fmt(self, level: str, msg: str):
        self._header()
        print(f"{datetime.now().strftime('%H:%M:%S'):<10} │ {level:<8} │ {msg}")

    def info(self, msg: str): self._fmt("INFO", msg)
    def success(self, msg: str): self._fmt("SUCCESS", msg)
    def warn(self, msg: str): self._fmt("WARN", msg)
    def error(self, msg: str): self._fmt("ERROR", msg)
    def status(self, msg: str): self._fmt("STATUS", msg)
    def footer(self): print("─" * 80)

tlog = TableLogger()

def setup_gpu_environment(config) -> None:
    os.environ["OMP_NUM_THREADS"] = str(config.thread_count)
