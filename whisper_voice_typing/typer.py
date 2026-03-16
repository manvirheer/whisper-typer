"""
Text insertion via NSPasteboard + CGEvent (macOS) or xdotool (Linux).

On macOS, uses PyObjC to:
1. Save current clipboard contents (with changeCount tracking)
2. Set clipboard to transcribed text
3. Simulate Cmd+V via CGEvent
4. Restore clipboard if no other app touched it

Falls back to subprocess (pbcopy/osascript) if PyObjC is unavailable.
"""

import time, subprocess, logging

from .utils import is_macos

log = logging.getLogger("whisper_voice_typing")

_HAS_PYOBJC = False
if is_macos():
    try:
        from AppKit import NSPasteboard, NSPasteboardTypeString  # type: ignore
        from Quartz import (  # type: ignore
            CGEventCreateKeyboardEvent,
            CGEventSetFlags,
            CGEventPost,
            kCGHIDEventTap,
            kCGEventFlagMaskCommand,
        )
        _HAS_PYOBJC = True
    except ImportError:
        log.warning("PyObjC not available, falling back to subprocess for text insertion")


def type_text(text: str) -> bool:
    """Type text into the currently focused application."""
    try:
        if is_macos():
            if _HAS_PYOBJC:
                return _type_macos_native(text)
            return _type_macos_subprocess(text)
        return _type_linux(text)
    except Exception as e:
        log.exception(f"Failed to type: {e}")
        return False


def _type_macos_native(text: str) -> bool:
    """Paste text using NSPasteboard + CGEvent Cmd+V."""
    pb = NSPasteboard.generalPasteboard()

    # save clipboard state
    old_contents = pb.stringForType_(NSPasteboardTypeString)

    # set clipboard to our text
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)

    # capture change count AFTER we set the clipboard
    our_change_count = pb.changeCount()

    # simulate Cmd+V (key code 9 = 'v')
    success = _send_cmd_v()

    if not success:
        return False

    # restore clipboard if no other app touched it since we set it
    time.sleep(0.1)
    if pb.changeCount() == our_change_count and old_contents is not None:
        pb.clearContents()
        pb.setString_forType_(old_contents, NSPasteboardTypeString)

    return True


def _send_cmd_v() -> bool:
    """Send Cmd+V keystroke via CGEvent."""
    try:
        # key code 9 = 'v' on macOS
        key_down = CGEventCreateKeyboardEvent(None, 9, True)
        key_up = CGEventCreateKeyboardEvent(None, 9, False)

        if key_down is None or key_up is None:
            log.error("Failed to create CGEvent - check Accessibility permissions")
            return False

        CGEventSetFlags(key_down, kCGEventFlagMaskCommand)
        CGEventSetFlags(key_up, kCGEventFlagMaskCommand)

        CGEventPost(kCGHIDEventTap, key_down)
        CGEventPost(kCGHIDEventTap, key_up)
        return True
    except Exception as e:
        error_str = str(e)
        if "not allowed" in error_str or "1002" in error_str:
            log.error("Accessibility permission denied - System Settings > Privacy & Security > Accessibility")
        else:
            log.error(f"CGEvent failed: {e}")
        return False


def _type_macos_subprocess(text: str) -> bool:
    """Fallback: paste text using pbcopy + osascript."""
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
    """Type text using xdotool."""
    subprocess.run(
        ["xdotool", "type", "--delay", "1", "--clearmodifiers", "--", text],
        check=True, timeout=10,
    )
    return True
