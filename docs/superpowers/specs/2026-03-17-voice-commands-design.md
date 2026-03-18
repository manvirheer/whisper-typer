# Voice Command System + Recording Limit Increase

**Date:** 2026-03-17
**Status:** Draft

## Summary

Add an extensible voice command system to whisper-typer. The trigger phrase is "command" followed by an action name (e.g., "command enter"). When detected at the end of a transcription, the action text is stripped and the corresponding keypress is simulated after the typed text lands. Also increase max recording duration from 30s to 45s.

## Requirements

1. **"command enter"** — When the user ends their speech with "command enter", the app types the preceding text and then simulates pressing the Enter key.
2. **Must be trailing** — If the user says anything after "command enter" in the same utterance, the entire transcription is treated as plain text (no command fires).
3. **Delay before keypress** — A configurable delay between pasting text and pressing Enter, so the paste has time to land in the target app.
4. **Fuzzy matching** — Case-insensitive matching, trailing punctuation stripped (`. ! ? ,`). Handles "Command Enter.", "command enter!", etc.
5. **Extensible** — Adding new commands (e.g., "command tab") should require only adding one entry to a registry.
6. **Max recording duration** — Increase from 30s to 45s.

## Design

### New file: `whisper_voice_typing/commands.py`

#### Command Registry

```python
COMMANDS = {
    "enter": 36,  # macOS keycode for Return
}
```

A dict mapping command names (lowercase) to macOS virtual keycodes. Adding a new command is one line.

#### `parse_command(text: str) -> tuple[str, int | None]`

1. Strip trailing punctuation (`. ! ? ,`) from the transcribed text.
2. Lowercase the text for matching.
3. Check if it ends with `"command {name}"` for any name in `COMMANDS`.
4. If match: return `(text_before_command.rstrip(), keycode)`.
5. If the remaining text is empty (user only said "command enter"): return `("", keycode)`.
6. No match: return `(original_text, None)`.

#### `send_key(keycode: int, delay_ms: int) -> bool`

1. Sleep for `delay_ms` milliseconds (lets the paste operation complete).
2. Create key-down and key-up `CGEvent` for the given keycode (no modifier flags — plain Enter).
3. Post both events via `CGEventPost(kCGHIDEventTap, ...)`.
4. Subprocess fallback: use `osascript` to send the keystroke if PyObjC is unavailable.
5. Return `True` on success, `False` on failure.

### Modified file: `whisper_voice_typing/config.py`

Two changes:

1. `max_recording_duration: int = 45` (was `30`)
2. New field:
   ```python
   command_delay_ms: int = field(
       default_factory=lambda: int(os.environ.get("WHISPER_COMMAND_DELAY_MS", "300"))
   )
   ```

### Modified file: `whisper_voice_typing/app.py`

In `_do_transcribe`, after transcription succeeds (around line 307):

**Current flow:**
```
text = server.transcribe(audio_file)
if text:
    type_text(text)
```

**New flow:**
```
text = server.transcribe(audio_file)
if text:
    cleaned_text, keycode = parse_command(text)
    if cleaned_text:
        type_text(cleaned_text)
    if keycode is not None:
        delay = self.config.command_delay_ms if cleaned_text else 0
        send_key(keycode, delay)
```

Key behaviors:
- "hey check this out command enter" -> types "hey check this out", waits 300ms, presses Enter
- "hey check this out" -> types "hey check this out", no keypress
- "command enter" -> presses Enter immediately (no delay, nothing to paste)
- "I said command enter and then left" -> types full text verbatim (command not at end)

### Files NOT modified

- `typer.py` — unchanged, `send_key` lives in `commands.py` with its own CGEvent usage
- `menubar.py` — unchanged
- `state.py` — unchanged
- `vad.py` — unchanged
- `audio.py` — unchanged

## Edge Cases

| Input | Result |
|-------|--------|
| "hello command enter" | Types "hello", presses Enter |
| "hello command enter." | Types "hello", presses Enter (punctuation stripped) |
| "hello Command Enter" | Types "hello", presses Enter (case-insensitive) |
| "hello command enter goodbye" | Types full text verbatim (command not at end) |
| "command enter" | Presses Enter only (no text typed, no delay) |
| "" (empty transcription) | No action (existing behavior) |
| "I used the command enter key" | Types full text verbatim (command not at end) |

## Configuration

| Setting | Default | Env Var | Description |
|---------|---------|---------|-------------|
| `command_delay_ms` | 300 | `WHISPER_COMMAND_DELAY_MS` | Delay in ms between paste and keypress |
| `max_recording_duration` | 45 | — | Max recording length in seconds |
