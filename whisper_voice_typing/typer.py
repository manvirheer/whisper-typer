"""Text insertion: NSPasteboard + CGEvent (macOS) or xdotool (Linux)."""

import time, subprocess, logging
from .utils import is_macos

log = logging.getLogger("whisper_voice_typing")

_HAS_PYOBJC = False
if is_macos():
    try:
        from AppKit import NSPasteboard, NSPasteboardTypeString
        from Quartz import (
            CGEventCreateKeyboardEvent, CGEventSetFlags,
            CGEventPost, kCGHIDEventTap, kCGEventFlagMaskCommand,
        )
        _HAS_PYOBJC = True
    except ImportError:
        log.warning("PyObjC not available, using subprocess fallback")


def type_text(text: str) -> bool:
    try:
        if is_macos():
            return _type_macos_native(text) if _HAS_PYOBJC else _type_macos_subprocess(text)
        return _type_linux(text)
    except Exception as e:
        log.exception(f"Failed to type: {e}")
        return False


def _type_macos_native(text: str) -> bool:
    pb = NSPasteboard.generalPasteboard()
    old_contents = pb.stringForType_(NSPasteboardTypeString)

    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)
    our_change_count = pb.changeCount()

    if not _send_cmd_v():
        return False

    time.sleep(0.1)
    if pb.changeCount() == our_change_count and old_contents is not None:
        pb.clearContents()
        pb.setString_forType_(old_contents, NSPasteboardTypeString)
    return True


def _send_cmd_v() -> bool:
    try:
        # key code 9 = 'v'
        key_down = CGEventCreateKeyboardEvent(None, 9, True)
        key_up = CGEventCreateKeyboardEvent(None, 9, False)
        if key_down is None or key_up is None:
            log.error("CGEvent creation failed - check Accessibility permissions")
            return False
        CGEventSetFlags(key_down, kCGEventFlagMaskCommand)
        CGEventSetFlags(key_up, kCGEventFlagMaskCommand)
        CGEventPost(kCGHIDEventTap, key_down)
        CGEventPost(kCGHIDEventTap, key_up)
        return True
    except Exception as e:
        log.error(f"CGEvent failed: {e}")
        return False


def _type_macos_subprocess(text: str) -> bool:
    saved = None
    try:
        r = subprocess.run(["pbpaste"], capture_output=True, timeout=2)
        if r.returncode == 0: saved = r.stdout
    except Exception: pass

    subprocess.run(["pbcopy"], input=text.encode(), check=True, timeout=5)
    result = subprocess.run(
        ["osascript", "-e", 'tell application "System Events" to keystroke "v" using command down'],
        capture_output=True, text=True, timeout=10,
    )

    if saved is not None:
        time.sleep(0.1)
        try: subprocess.run(["pbcopy"], input=saved, timeout=2)
        except Exception: pass

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not allowed" in stderr or "1002" in stderr:
            log.error("Accessibility permission denied - System Settings > Privacy & Security > Accessibility")
        else:
            log.error(f"osascript failed: {stderr}")
        return False
    return True


def _type_linux(text: str) -> bool:
    subprocess.run(["xdotool", "type", "--delay", "1", "--clearmodifiers", "--", text], check=True, timeout=10)
    return True
