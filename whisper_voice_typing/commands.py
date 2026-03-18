"""Voice command parsing and execution."""

import time, logging
from .typer import send_key

log = logging.getLogger("whisper_voice_typing")

COMMANDS = {
    "enter": 36,  # macOS keycode for Return
}

_TRAILING_PUNCT = ".!?,;:"


def parse_command(text: str) -> tuple[str, int | None]:
    stripped = text.rstrip(_TRAILING_PUNCT)
    lowered = stripped.lower()
    for name, keycode in COMMANDS.items():
        suffix = f"command {name}"
        if lowered.endswith(suffix):
            before = stripped[: len(stripped) - len(suffix)].strip()
            return (before, keycode)
    return (text, None)


def execute_command(keycode: int, delay_ms: int) -> bool:
    if delay_ms > 0:
        time.sleep(delay_ms / 1000)
    name = next((n for n, k in COMMANDS.items() if k == keycode), str(keycode))
    if send_key(keycode):
        log.info(f"Command executed: {name}")
        return True
    log.error(f"Command failed: {name}")
    return False
