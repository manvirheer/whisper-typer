"""Utility functions for logging and environment setup"""

import os
import logging
from datetime import datetime


# Logger setup for debug logs
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("whisper_voice_typing")


class TableLogger:
    """Formats log messages in a clean table format"""

    def __init__(self):
        self.header_printed = False

    def _print_header(self):
        """Print table header"""
        if not self.header_printed:
            print("─" * 80)
            print(f"{'TIME':<10} │ {'LEVEL':<8} │ {'MESSAGE':<57}")
            print("─" * 80)
            self.header_printed = True

    def _format_message(self, level: str, message: str) -> str:
        """Format a log message with timestamp and level"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        return f"{timestamp:<10} │ {level:<8} │ {message}"

    def info(self, message: str):
        """Log info message"""
        self._print_header()
        print(self._format_message("INFO", message))

    def success(self, message: str):
        """Log success message"""
        self._print_header()
        print(self._format_message("SUCCESS", message))

    def warn(self, message: str):
        """Log warning message"""
        self._print_header()
        print(self._format_message("WARN", message))

    def error(self, message: str):
        """Log error message"""
        self._print_header()
        print(self._format_message("ERROR", message))

    def status(self, message: str):
        """Log status message"""
        self._print_header()
        print(self._format_message("STATUS", message))

    def footer(self):
        """Print table footer"""
        print("─" * 80)


# Global table logger instance
tlog = TableLogger()


def setup_gpu_environment(config) -> None:
    """Setup minimal environment variables - let whisper.cpp handle GPU automatically"""
    log.debug("Setting up environment variables")

    # Only set CPU thread count - whisper.cpp will auto-detect and use GPU
    os.environ["OMP_NUM_THREADS"] = str(config.thread_count)
    log.debug(f"  OMP_NUM_THREADS={config.thread_count}")
