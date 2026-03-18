"""Text insertion: NSPasteboard + CGEvent (native) or pbcopy+osascript (fallback)."""

import time, subprocess, logging

log = logging.getLogger("whisper_voice_typing")

_HAS_PYOBJC = False
NSPasteboard = NSPasteboardTypeString = None
CGEventCreateKeyboardEvent = CGEventSetFlags = CGEventPost = None
kCGHIDEventTap = kCGEventFlagMaskCommand = None
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
        return _type_native(text) if _HAS_PYOBJC else _type_subprocess(text)
    except Exception as e:
        log.exception(f"Failed to type: {e}")
        return False


def _type_native(text: str) -> bool:
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


def send_key(keycode: int, flags: int = 0) -> bool:
    try:
        return _send_key_native(keycode, flags) if _HAS_PYOBJC else _send_key_subprocess(keycode)
    except Exception as e:
        log.error(f"send_key failed: {e}")
        return False


def _send_key_native(keycode: int, flags: int = 0) -> bool:
    key_down = CGEventCreateKeyboardEvent(None, keycode, True)
    key_up = CGEventCreateKeyboardEvent(None, keycode, False)
    if key_down is None or key_up is None:
        log.error("CGEvent creation failed - check Accessibility permissions")
        return False
    CGEventSetFlags(key_down, flags)
    CGEventSetFlags(key_up, flags)
    CGEventPost(kCGHIDEventTap, key_down)
    CGEventPost(kCGHIDEventTap, key_up)
    return True


def _send_key_subprocess(keycode: int) -> bool:
    result = subprocess.run(
        ["osascript", "-e", f'tell application "System Events" to key code {keycode}'],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not allowed" in stderr or "1002" in stderr:
            log.error("Accessibility permission denied - System Settings > Privacy & Security > Accessibility")
        else:
            log.error(f"osascript key code failed: {stderr}")
        return False
    return True


def _send_cmd_v() -> bool:
    return send_key(9, kCGEventFlagMaskCommand if _HAS_PYOBJC else 0)


def _type_subprocess(text: str) -> bool:
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
