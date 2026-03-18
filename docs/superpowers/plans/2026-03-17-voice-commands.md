# Voice Command System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an extensible voice command system that detects trailing "command {action}" phrases in transcriptions, types the preceding text, and simulates the corresponding keypress. Also increase max recording duration to 45s.

**Architecture:** New `commands.py` module handles parsing and execution. Shared `send_key` helper extracted into `typer.py` to avoid CGEvent duplication. `app.py`'s `_do_transcribe` calls `parse_command` then conditionally `execute_command`.

**Tech Stack:** Python 3.12+, PyObjC (CGEvent/Quartz), pytest

**Spec:** `docs/superpowers/specs/2026-03-17-voice-commands-design.md`

---

### Task 1: Extract `send_key` helper in `typer.py`

**Files:**
- Modify: `whisper_voice_typing/typer.py:48-62`
- Test: `tests/test_typer.py`

- [ ] **Step 1: Write failing test for `send_key` with no flags (plain keypress)**

Add to `tests/test_typer.py`:

```python
class TestSendKey:
    @patch("whisper_voice_typing.typer.CGEventPost")
    @patch("whisper_voice_typing.typer.CGEventSetFlags")
    @patch("whisper_voice_typing.typer.CGEventCreateKeyboardEvent")
    def test_send_key_no_flags(self, mock_create, mock_flags, mock_post):
        mock_create.side_effect = [MagicMock(), MagicMock()]
        from whisper_voice_typing.typer import send_key
        assert send_key(36) is True
        assert mock_create.call_count == 2
        mock_create.assert_any_call(None, 36, True)
        mock_create.assert_any_call(None, 36, False)
        assert mock_post.call_count == 2
        mock_flags.assert_not_called()

    @patch("whisper_voice_typing.typer.CGEventPost")
    @patch("whisper_voice_typing.typer.CGEventSetFlags")
    @patch("whisper_voice_typing.typer.CGEventCreateKeyboardEvent")
    def test_send_key_with_flags(self, mock_create, mock_flags, mock_post):
        mock_create.side_effect = [MagicMock(), MagicMock()]
        from whisper_voice_typing.typer import send_key
        assert send_key(9, 0x100000) is True
        assert mock_flags.call_count == 2
        assert mock_post.call_count == 2

    @patch("whisper_voice_typing.typer.CGEventCreateKeyboardEvent", return_value=None)
    def test_send_key_returns_false_on_null_event(self, _):
        from whisper_voice_typing.typer import send_key
        assert send_key(36) is False

    @patch("whisper_voice_typing.typer._HAS_PYOBJC", False)
    @patch("whisper_voice_typing.typer.subprocess.run")
    def test_send_key_subprocess_fallback(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        from whisper_voice_typing.typer import send_key
        assert send_key(36) is True
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "key code 36" in cmd[-1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/manvir/personal/whisper-typer && python -m pytest tests/test_typer.py::TestSendKey -v`
Expected: FAIL — `send_key` does not exist yet.

- [ ] **Step 3: Implement `send_key` and refactor `_send_cmd_v`**

In `whisper_voice_typing/typer.py`, replace `_send_cmd_v` (lines 48-62) with:

```python
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
    if flags:
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
```

Note: `_send_cmd_v` still exists as a thin wrapper so the rest of `typer.py` doesn't change. When `_HAS_PYOBJC` is False, `_send_cmd_v` calls `send_key(9, 0)` which hits the subprocess fallback — but `_type_subprocess` already handles Cmd+V via its own osascript call (line 73-76), so `_send_cmd_v` is only called from `_type_native`. This means the `flags=0` fallback in `_send_cmd_v` is fine — it's a dead path (native path always has PyObjC).

- [ ] **Step 4: Run all typer tests to verify nothing broke**

Run: `cd /Users/manvir/personal/whisper-typer && python -m pytest tests/test_typer.py -v`
Expected: ALL PASS (new `TestSendKey` tests + existing tests).

- [ ] **Step 5: Commit**

```bash
git add whisper_voice_typing/typer.py tests/test_typer.py
git commit -m "refactor: extract send_key helper in typer.py"
```

---

### Task 2: Update `config.py`

**Files:**
- Modify: `whisper_voice_typing/config.py:32`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing tests for new config fields**

Add to `tests/test_config.py` in `TestConfig`:

```python
def test_max_recording_duration_default(self, monkeypatch):
    monkeypatch.delenv("WHISPER_MAX_RECORDING_DURATION", raising=False)
    config = Config()
    assert config.max_recording_duration == 45

def test_max_recording_duration_env_override(self, monkeypatch):
    monkeypatch.setenv("WHISPER_MAX_RECORDING_DURATION", "60")
    config = Config()
    assert config.max_recording_duration == 60

def test_command_delay_ms_default(self, monkeypatch):
    monkeypatch.delenv("WHISPER_COMMAND_DELAY_MS", raising=False)
    config = Config()
    assert config.command_delay_ms == 300

def test_command_delay_ms_env_override(self, monkeypatch):
    monkeypatch.setenv("WHISPER_COMMAND_DELAY_MS", "500")
    config = Config()
    assert config.command_delay_ms == 500
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/manvir/personal/whisper-typer && python -m pytest tests/test_config.py::TestConfig::test_max_recording_duration_default tests/test_config.py::TestConfig::test_command_delay_ms_default -v`
Expected: FAIL — `max_recording_duration` is 30, `command_delay_ms` doesn't exist.

- [ ] **Step 3: Update config.py**

In `whisper_voice_typing/config.py`, replace line 32:

```python
    max_recording_duration: int = 30
```

with:

```python
    max_recording_duration: int = field(
        default_factory=lambda: int(os.environ.get("WHISPER_MAX_RECORDING_DURATION", "45"))
    )
```

Add after `min_file_size` (line 33), in the `# recording` section:

```python
    command_delay_ms: int = field(
        default_factory=lambda: int(os.environ.get("WHISPER_COMMAND_DELAY_MS", "300"))
    )
```

- [ ] **Step 4: Fix existing test that asserts `max_recording_duration == 30`**

In `tests/test_config.py`, line 41, change:

```python
assert config.max_recording_duration == 30
```

to:

```python
assert config.max_recording_duration == 45
```

- [ ] **Step 5: Run all config tests**

Run: `cd /Users/manvir/personal/whisper-typer && python -m pytest tests/test_config.py -v`
Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add whisper_voice_typing/config.py tests/test_config.py
git commit -m "feat: add command_delay_ms config, increase max_recording_duration to 45s"
```

---

### Task 3: Create `commands.py`

**Files:**
- Create: `whisper_voice_typing/commands.py`
- Create: `tests/test_commands.py`

- [ ] **Step 1: Write failing tests for `parse_command`**

Create `tests/test_commands.py`:

```python
"""Tests for voice command parsing and execution."""

import time
from unittest.mock import patch, MagicMock

import pytest


class TestParseCommand:
    def test_trailing_command_enter(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("hello command enter")
        assert text == "hello"
        assert keycode == 36

    def test_case_insensitive(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("hello Command Enter")
        assert text == "hello"
        assert keycode == 36

    def test_trailing_period(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("hello command enter.")
        assert text == "hello"
        assert keycode == 36

    def test_multiple_trailing_punctuation(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("hello command enter!!!")
        assert text == "hello"
        assert keycode == 36

    def test_no_command(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("hello world")
        assert text == "hello world"
        assert keycode is None

    def test_command_not_at_end(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("hello command enter goodbye")
        assert text == "hello command enter goodbye"
        assert keycode is None

    def test_command_only(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("command enter")
        assert text == ""
        assert keycode == 36

    def test_preserves_original_casing(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("Hello World command enter")
        assert text == "Hello World"
        assert keycode == 36

    def test_strips_leading_whitespace_from_result(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("  command enter")
        assert text == ""
        assert keycode == 36

    def test_command_mid_sentence(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("I used the command enter key")
        assert text == "I used the command enter key"
        assert keycode is None

    def test_semicolon_stripped(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("hello command enter;")
        assert text == "hello"
        assert keycode == 36

    def test_empty_string(self):
        from whisper_voice_typing.commands import parse_command
        text, keycode = parse_command("")
        assert text == ""
        assert keycode is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/manvir/personal/whisper-typer && python -m pytest tests/test_commands.py::TestParseCommand -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement `commands.py` with `parse_command`**

Create `whisper_voice_typing/commands.py`:

```python
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
```

- [ ] **Step 4: Run parse_command tests**

Run: `cd /Users/manvir/personal/whisper-typer && python -m pytest tests/test_commands.py::TestParseCommand -v`
Expected: ALL PASS.

- [ ] **Step 5: Write failing tests for `execute_command`**

Add to `tests/test_commands.py`:

```python
class TestExecuteCommand:
    @patch("whisper_voice_typing.commands.send_key", return_value=True)
    def test_executes_keypress(self, mock_send):
        from whisper_voice_typing.commands import execute_command
        assert execute_command(36, 0) is True
        mock_send.assert_called_once_with(36)

    @patch("whisper_voice_typing.commands.send_key", return_value=False)
    def test_returns_false_on_failure(self, mock_send):
        from whisper_voice_typing.commands import execute_command
        assert execute_command(36, 0) is False

    @patch("whisper_voice_typing.commands.send_key", return_value=True)
    @patch("whisper_voice_typing.commands.time.sleep")
    def test_delays_before_keypress(self, mock_sleep, mock_send):
        from whisper_voice_typing.commands import execute_command
        execute_command(36, 300)
        mock_sleep.assert_called_once_with(0.3)

    @patch("whisper_voice_typing.commands.send_key", return_value=True)
    @patch("whisper_voice_typing.commands.time.sleep")
    def test_no_delay_when_zero(self, mock_sleep, mock_send):
        from whisper_voice_typing.commands import execute_command
        execute_command(36, 0)
        mock_sleep.assert_not_called()
```

- [ ] **Step 6: Run all command tests**

Run: `cd /Users/manvir/personal/whisper-typer && python -m pytest tests/test_commands.py -v`
Expected: ALL PASS.

- [ ] **Step 7: Commit**

```bash
git add whisper_voice_typing/commands.py tests/test_commands.py
git commit -m "feat: add voice command parsing and execution module"
```

---

### Task 4: Integrate into `app.py`

**Files:**
- Modify: `whisper_voice_typing/app.py:290-326`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write failing test for command integration**

Add to `tests/test_app.py` in `TestDoTranscribe`:

```python
@patch("whisper_voice_typing.app.execute_command", return_value=True)
@patch("whisper_voice_typing.app.parse_command", return_value=("hello", 36))
def test_transcription_with_voice_command(self, mock_parse, mock_exec):
    from pathlib import Path
    audio_file = MagicMock(spec=Path)
    self.app._audio.save_recording.return_value = audio_file
    self.app.server.transcribe = MagicMock(return_value="hello command enter")
    self.app._do_transcribe()
    mock_parse.assert_called_once_with("hello command enter")
    self.app._type_text.assert_called_with("hello")
    mock_exec.assert_called_once_with(36, self.app.config.command_delay_ms)

@patch("whisper_voice_typing.app.execute_command")
@patch("whisper_voice_typing.app.parse_command", return_value=("hello world", None))
def test_transcription_without_command(self, mock_parse, mock_exec):
    from pathlib import Path
    audio_file = MagicMock(spec=Path)
    self.app._audio.save_recording.return_value = audio_file
    self.app.server.transcribe = MagicMock(return_value="hello world")
    self.app._do_transcribe()
    self.app._type_text.assert_called_with("hello world")
    mock_exec.assert_not_called()

@patch("whisper_voice_typing.app.execute_command", return_value=True)
@patch("whisper_voice_typing.app.parse_command", return_value=("", 36))
def test_command_only_no_text_typed(self, mock_parse, mock_exec):
    from pathlib import Path
    audio_file = MagicMock(spec=Path)
    self.app._audio.save_recording.return_value = audio_file
    self.app.server.transcribe = MagicMock(return_value="command enter")
    self.app._do_transcribe()
    self.app._type_text.assert_not_called()
    mock_exec.assert_called_once_with(36, 0)  # no delay when no text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/manvir/personal/whisper-typer && python -m pytest tests/test_app.py::TestDoTranscribe::test_transcription_with_voice_command -v`
Expected: FAIL — `parse_command` not imported in `app.py`.

- [ ] **Step 3: Modify `_do_transcribe` in `app.py`**

Add import at top of `_do_transcribe` method (line 291, alongside existing local imports):

```python
from .commands import parse_command, execute_command
```

Replace the `if text:` block (lines 307-314) with:

```python
            if text:
                cleaned_text, keycode = parse_command(text)
                self.state_machine.transition(State.TYPING)
                self._ui_queue.put(StateUpdate(State.TYPING))
                # Send TranscriptionResult before typing (matches original ordering —
                # UI update is non-blocking and should reflect state immediately)
                self._ui_queue.put(TranscriptionResult(cleaned_text if cleaned_text else text))
                if cleaned_text:
                    if self._type_text(cleaned_text):
                        tlog.info(f"Typed: {cleaned_text[:60]}{'...' if len(cleaned_text) > 60 else ''}")
                    else:
                        tlog.error("Failed to type text")
                if keycode is not None:
                    tlog.info(f"Voice command detected: keycode={keycode}")
                    delay = self.config.command_delay_ms if cleaned_text else 0
                    if not execute_command(keycode, delay):
                        tlog.error("Failed to execute voice command")
```

Note: `TranscriptionResult` is sent before typing, matching the original ordering in `app.py:310` where it was pushed to the queue before `type_text` was called. The existing `test_successful_transcription_types_text` test continues to pass without modification because it doesn't assert on `parse_command` — it calls `_do_transcribe` which now internally calls `parse_command("hello world")` returning `("hello world", None)`, then types "hello world" as before.

- [ ] **Step 4: Run all app tests**

Run: `cd /Users/manvir/personal/whisper-typer && python -m pytest tests/test_app.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/manvir/personal/whisper-typer && python -m pytest -v`
Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add whisper_voice_typing/app.py tests/test_app.py
git commit -m "feat: integrate voice command system into transcription pipeline"
```
