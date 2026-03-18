# Voice Command System + Recording Limit Increase

**Date:** 2026-03-17
**Status:** Draft

## Summary

Add an extensible voice command system to whisper-typer. The trigger phrase is "command" followed by an action name (e.g., "command enter"). When detected at the end of a transcription, the action text is stripped and the corresponding keypress is simulated after the typed text lands. Also increase max recording duration from 30s to 45s.

## Requirements

1. **"command enter"** — When the user ends their speech with "command enter", the app types the preceding text and then simulates pressing the Enter key.
2. **Must be trailing** — If the user says anything after "command enter" in the same utterance, the entire transcription is treated as plain text (no command fires).
3. **Delay before keypress** — A configurable delay between pasting text and pressing Enter, so the paste has time to land in the target app.
4. **Fuzzy matching** — Case-insensitive matching, trailing punctuation stripped. Handles "Command Enter.", "command enter!", etc.
5. **Extensible** — Adding new commands (e.g., "command tab") should require only adding one entry to a registry.
6. **Max recording duration** — Increase from 30s to 45s.

## Design

### Modified file: `whisper_voice_typing/typer.py`

Extract a shared `send_key(keycode: int, flags: int = 0) -> bool` helper from the existing CGEvent infrastructure. This avoids duplicating the PyObjC import checks and subprocess fallback that already live in `typer.py`.

- `_send_cmd_v()` is refactored to call `send_key(9, kCGEventFlagMaskCommand)` internally.
- `send_key` handles both native (CGEvent) and subprocess fallback (`osascript -e 'tell application "System Events" to key code {keycode}'`).
- No modifier flags by default (plain keypress). When flags are provided (e.g., `kCGEventFlagMaskCommand`), they are applied via `CGEventSetFlags`.

### New file: `whisper_voice_typing/commands.py`

#### Command Registry

```python
COMMANDS = {
    "enter": 36,  # macOS keycode for Return
}
```

A dict mapping command names (lowercase) to macOS virtual keycodes. Adding a new command is one line.

#### `parse_command(text: str) -> tuple[str, int | None]`

1. Strip all trailing punctuation characters (`.!?,;:`) from the transcribed text. Multiple trailing characters are stripped (e.g., "command enter!!!" or "command enter...").
2. Create a lowercased copy for matching purposes.
3. Check if the lowercased copy ends with `"command {name}"` for any name in `COMMANDS`.
4. If match: slice the **original-cased** text (not the lowercased copy) to extract the portion before "command {name}". Return `(original_text_before_command.strip(), keycode)`. Strip both sides — leading whitespace in typed output would be a bug. This preserves the user's original casing in the typed output.
5. If the remaining text is empty (user only said "command enter"): return `("", keycode)`.
6. No match: return `(original_text, None)` — the unmodified input.

#### `execute_command(keycode: int, delay_ms: int) -> bool`

1. Sleep for `delay_ms` milliseconds (lets the paste operation complete in the target app).
2. Call `typer.send_key(keycode)` (the shared helper in `typer.py`).
3. Log the result: `tlog.info("Command executed: {name}")` on success, `tlog.error("Command failed: {name}")` on failure.
4. Return `True` on success, `False` on failure.

### Modified file: `whisper_voice_typing/config.py`

Three changes:

1. `max_recording_duration` default changed from `30` to `45`, with env var override:
   ```python
   max_recording_duration: int = field(
       default_factory=lambda: int(os.environ.get("WHISPER_MAX_RECORDING_DURATION", "45"))
   )
   ```
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
    tlog.info(f"Typed: {text[:60]}...")
    ui_queue.put(TranscriptionResult(text))
```

**New flow:**
```
text = server.transcribe(audio_file)
if text:
    cleaned_text, keycode = parse_command(text)
    if cleaned_text:
        type_text(cleaned_text)
        tlog.info(f"Typed: {cleaned_text[:60]}...")
    if keycode is not None:
        tlog.info(f"Voice command detected: keycode={keycode}")
        delay = self.config.command_delay_ms if cleaned_text else 0
        if not execute_command(keycode, delay):
            tlog.error("Failed to execute voice command")
    # UI history shows cleaned text. When cleaned_text is empty (user said only
    # "command enter"), we intentionally show the raw text so the history isn't blank.
    ui_queue.put(TranscriptionResult(cleaned_text if cleaned_text else text))
```

Key behaviors:
- "hey check this out command enter" -> types "hey check this out", waits 300ms, presses Enter. UI history shows "hey check this out".
- "hey check this out" -> types "hey check this out", no keypress
- "command enter" -> presses Enter immediately (no delay, nothing to paste). UI history shows original text.
- "I said command enter and then left" -> types full text verbatim (command not at end)
- "please send the email command enter and then close it" -> types full text verbatim (command not at end, trailing words after it)

### Files NOT modified

- `menubar.py` — unchanged
- `state.py` — unchanged
- `vad.py` — unchanged
- `audio.py` — unchanged

## Edge Cases

| Input | Result |
|-------|--------|
| "hello command enter" | Types "hello", presses Enter |
| "hello command enter." | Types "hello", presses Enter (punctuation stripped) |
| "hello command enter!!!" | Types "hello", presses Enter (multiple punctuation stripped) |
| "hello Command Enter" | Types "hello", presses Enter (case-insensitive) |
| "hello command enter goodbye" | Types full text verbatim (command not at end) |
| "command enter" | Presses Enter only (no text typed, no delay) |
| "" (empty transcription) | No action (existing behavior) |
| "I used the command enter key" | Types full text verbatim (command not at end) |
| "send the email command enter and close it" | Types full text verbatim (command not at end) |

## Configuration

| Setting | Default | Env Var | Description |
|---------|---------|---------|-------------|
| `command_delay_ms` | 300 | `WHISPER_COMMAND_DELAY_MS` | Delay in ms between paste and keypress |
| `max_recording_duration` | 45 | `WHISPER_MAX_RECORDING_DURATION` | Max recording length in seconds |

## Notes

- The ~800ms total deaf window (300ms command delay + 500ms TYPING state sleep) is acceptable — the user expects a brief pause after sending a message.
- The `send_key` helper in `typer.py` uses `osascript -e 'tell application "System Events" to key code {keycode}'` as the subprocess fallback, which supports arbitrary keycodes — same virtual keycode space as CGEvent.
- **Limitation:** The osascript fallback does not currently translate modifier flags. For the current "enter" command (no modifiers) this is fine. If a future command needs modifiers (e.g., Shift+Tab), the fallback would need to be extended to emit `using {shift down}` etc.
