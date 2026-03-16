# Setup Overhaul Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drop Linux support, rewrite setup.sh with preflight checks / model picker / venv handling, clean up all legacy code paths, simplify README.

**Architecture:** Remove all Linux code and the legacy ffmpeg+sox pipeline. The app becomes macOS Apple Silicon only. setup.sh becomes the single entry point that handles everything from dependency checks to model download.

**Tech Stack:** Bash (setup.sh), Python 3.10+ (source cleanup), pytest (test updates)

**Spec:** `docs/superpowers/specs/2026-03-16-setup-overhaul-design.md`

---

## Chunk 1: Code Removal — Strip Linux & Legacy

### Task 1: Remove `is_macos()` from utils.py and all imports

**Files:**
- Modify: `whisper_voice_typing/utils.py:1-7`

- [ ] **Step 1: Remove `is_macos()` function and unused `platform` import**

In `whisper_voice_typing/utils.py`, delete line 7 (`def is_macos() -> bool: return platform.system() == "Darwin"`) and remove `platform` from the imports on line 1 (keep `os, sys, logging`).

After edit, line 1 should be:
```python
import os, sys, logging
```

And the `is_macos` function should be gone entirely.

- [ ] **Step 2: Run tests to see what breaks**

Run: `python3 -m pytest tests/ -q 2>&1 | tail -20`
Expected: Multiple import errors for `is_macos` across the codebase. This is expected — we'll fix them in the following tasks.

- [ ] **Step 3: Commit**

```bash
git add whisper_voice_typing/utils.py
git commit -m "refactor: remove is_macos() — project is macOS-only now"
```

---

### Task 2: Remove Linux code from typer.py

**Files:**
- Modify: `whisper_voice_typing/typer.py`

- [ ] **Step 1: Rewrite typer.py to remove Linux path and is_macos guard**

Replace the entire file with:

```python
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


def _send_cmd_v() -> bool:
    try:
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
```

Key changes: removed `is_macos` import/guard, removed `_type_linux()`, made PyObjC import unconditional, renamed `_type_macos_native` → `_type_native` and `_type_macos_subprocess` → `_type_subprocess`.

- [ ] **Step 2: Verify no references to old function names**

Run: `grep -r "_type_linux\|_type_macos" whisper_voice_typing/`
Expected: No matches.

- [ ] **Step 3: Commit**

```bash
git add whisper_voice_typing/typer.py
git commit -m "refactor: remove Linux text insertion, simplify typer to macOS-only"
```

---

### Task 3: Remove LegacyAudioProcessor and /dev/shm from audio.py

**Files:**
- Modify: `whisper_voice_typing/audio.py`

- [ ] **Step 1: Remove `is_macos` import from line 3**

Change line 3 from:
```python
from .utils import log, tlog, is_macos
```
to:
```python
from .utils import log, tlog
```

- [ ] **Step 2: Simplify temp dir in AudioPipeline.setup_temp_dir() (line 84)**

Replace:
```python
base = Path("/dev/shm") if not is_macos() and Path("/dev/shm").exists() else Path("/tmp")
```
with:
```python
base = Path("/tmp")
```

- [ ] **Step 3: Delete the entire LegacyAudioProcessor class (lines 178-289)**

Remove everything from `# --- Legacy path (Linux / fallback) ---` to end of file.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_audio.py -q`
Expected: All audio tests pass (they test `RingBuffer` and `AudioPipeline`, not `LegacyAudioProcessor`).

- [ ] **Step 5: Commit**

```bash
git add whisper_voice_typing/audio.py
git commit -m "refactor: remove LegacyAudioProcessor and Linux temp dir logic"
```

---

### Task 4: Remove legacy pipeline from app.py

**Files:**
- Modify: `whisper_voice_typing/app.py`

- [ ] **Step 1: Remove `is_macos` import (line 15)**

Change:
```python
from .utils import log, tlog, setup_gpu_environment, is_macos
```
to:
```python
from .utils import log, tlog, setup_gpu_environment
```

- [ ] **Step 2: Replace `run()` method (lines 43-47) and remove `_can_use_new_pipeline()` (lines 49-55)**

Replace the `run()` method and `_can_use_new_pipeline()` with:

```python
    def run(self) -> None:
        try:
            import sounddevice, rumps  # noqa: F401
        except ImportError:
            tlog.error("Dependencies missing. Run: ./setup.sh")
            tlog.footer()
            sys.exit(1)
        self._run_macos()
```

Delete `_can_use_new_pipeline()` entirely.

- [ ] **Step 3: Delete `_run_legacy()` and `_cleanup_legacy()` (lines 332 to end of file)**

Remove both methods entirely — from the `# --- Legacy pipeline` comment through the end of the class.

- [ ] **Step 3b: Fix `validate()` call in `_run_macos()`**

The `validate()` signature will change in Task 5 (removing `use_new_pipeline` param). Fix it now to avoid breakage:

Change:
```python
self.config.validate(tlog, use_new_pipeline=True)
```
to:
```python
self.config.validate(tlog)
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_app.py -q -k "not TestCanUseNewPipeline"`
Expected: All app tests pass.

- [ ] **Step 5: Commit**

```bash
git add whisper_voice_typing/app.py
git commit -m "refactor: remove legacy pipeline, simplify run() to macOS-only"
```

---

### Task 5: Clean up config.py

**Files:**
- Modify: `whisper_voice_typing/config.py`

- [ ] **Step 1: Remove `is_macos` import and `~/personal/whisper.cpp` candidate**

Change line 4:
```python
from .utils import is_macos
```
to remove it entirely (delete the line).

In `_find_whisper_dir()`, change the candidates list from:
```python
for candidate in [Path.home() / ".local/share/whisper.cpp", Path.home() / "whisper.cpp", Path.home() / "personal/whisper.cpp"]:
```
to:
```python
for candidate in [Path.home() / ".local/share/whisper.cpp", Path.home() / "whisper.cpp"]:
```

- [ ] **Step 2: Remove legacy-only config fields**

Delete these lines from the `Config` dataclass:

```python
    # sox silence detection (legacy)
    silence_start_duration: float = 0.05
    silence_start_threshold: str = "1.5%"
    silence_end_duration: float = 2.0
    silence_end_threshold: str = "1%"
```

And delete:
```python
    post_processing_delay: float = 1.0
    no_audio_delay: float = 0.1
```

- [ ] **Step 3: Simplify `validate()` method (lines 74-91)**

Replace the entire `validate()` method with:

```python
    def validate(self, tlog) -> None:
        errors = []
        if not self.whisper_executable.exists() or not self.server_binary.exists():
            errors.append("whisper.cpp not set up. Run: ./setup.sh")
        if not self.whisper_model.exists():
            errors.append(f"model not found: {self.whisper_model}. Run: ./setup.sh")

        try: import sounddevice  # noqa: F401
        except ImportError: errors.append("sounddevice not installed. Run: ./setup.sh")

        if errors:
            for e in errors: tlog.error(e)
            tlog.footer()
            sys.exit(1)
```

Note: removed `use_new_pipeline` parameter, removed legacy command checks (`rec`, `ffmpeg`, `osascript`, `xdotool`).

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_config.py -q`
Expected: Pass (config tests don't test removed fields or legacy validate).

- [ ] **Step 5: Commit**

```bash
git add whisper_voice_typing/config.py
git commit -m "refactor: remove legacy config fields and Linux validate checks"
```

---

### Task 6: Clean up __main__.py

**Files:**
- Modify: `whisper_voice_typing/__main__.py`

- [ ] **Step 1: Remove `is_macos` import and checks, remove --legacy flag**

Replace the entire file with:

```python
import sys, argparse, plistlib, shutil
from pathlib import Path
from .app import WhisperVoiceTyping
from .config import Config


def _install_launchagent() -> None:
    config = Config()
    config.launchagent_dir.mkdir(parents=True, exist_ok=True)
    config.log_dir.mkdir(parents=True, exist_ok=True)

    wv_path = shutil.which("wv")
    if not wv_path:
        print("'wv' not found in PATH. Install: pip install -e ."); sys.exit(1)

    plist = {
        "Label": config.launchagent_label,
        "ProgramArguments": [wv_path],
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "StandardOutPath": str(config.log_dir / "stdout.log"),
        "StandardErrorPath": str(config.log_dir / "stderr.log"),
        "ProcessType": "Interactive",
    }
    with open(config.launchagent_plist, "wb") as f:
        plistlib.dump(plist, f)

    print(f"Installed: {config.launchagent_plist}")
    print(f"Logs: {config.log_dir}")
    print(f"Start now: launchctl load {config.launchagent_plist}")


def _uninstall_launchagent() -> None:
    config = Config()
    if config.launchagent_plist.exists():
        import subprocess
        subprocess.run(["launchctl", "unload", str(config.launchagent_plist)], capture_output=True)
        config.launchagent_plist.unlink()
        print(f"Removed: {config.launchagent_plist}")
    else:
        print("No LaunchAgent installed")


def main():
    parser = argparse.ArgumentParser(prog="wv", description="whisper-typer: local voice-to-text")
    parser.add_argument("command", nargs="?", choices=["install", "uninstall"])
    args = parser.parse_args()

    if args.command == "install":
        _install_launchagent()
    elif args.command == "uninstall":
        _uninstall_launchagent()
    else:
        app = WhisperVoiceTyping()
        app.run()


if __name__ == "__main__":
    main()
```

Key changes: removed `is_macos` import and guards from install/uninstall, removed `--legacy` flag, `run()` called directly (no legacy branch).

- [ ] **Step 2: Commit**

```bash
git add whisper_voice_typing/__main__.py
git commit -m "refactor: remove --legacy flag and Linux checks from CLI"
```

---

### Task 7: Update all tests

**Files:**
- Modify: `tests/test_typer.py`
- Modify: `tests/test_main.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Update test_typer.py**

1. Delete the entire `TestTypeTextLinux` class (lines 10-24).
2. Strip `@patch("whisper_voice_typing.typer.is_macos", return_value=True)` from every remaining test method AND remove the corresponding mock parameter (`_`) from each method signature. This decorator appears in:
   - `TestTypeTextMacOSSubprocess` (lines 28, 40, 52) — remove trailing `_` param
   - `TestClipboardRestoration` (lines 66, 80) — remove trailing `_` param
   - `TestNativeMacOS` (lines 96, 110, 120, 134) — remove trailing `_` param
3. Note: `_type_macos_native` was renamed to `_type_native` and `_type_macos_subprocess` to `_type_subprocess` in Task 2, but no tests reference these private names by string, so no test changes needed for the renames.

- [ ] **Step 2: Update test_main.py**

1. Delete the `test_legacy_flag` method (lines 18-23).
2. Delete the `test_install_exits_on_linux` method (lines 63-67).
3. Strip `@patch("whisper_voice_typing.__main__.is_macos", return_value=True)` from all remaining `TestLaunchAgent` methods AND remove the `mock_macos` parameter from each method signature:
   - `test_install_creates_plist` (line 41): decorator + `mock_macos` param (line 43)
   - `test_install_exits_if_wv_not_found` (line 69): decorator + `mock_macos` param (line 71)
   - `test_uninstall_removes_plist` (line 76): decorator + `mock_macos` param (line 77)
   - `test_uninstall_no_plist_is_noop` (line 92): decorator + `mock_macos` param (line 93)

- [ ] **Step 3: Update test_app.py**

1. Delete the entire `TestCanUseNewPipeline` class (lines 13-27).

- [ ] **Step 4: Verify no remaining is_macos references**

Run: `grep -r "is_macos" whisper_voice_typing/ tests/`
Expected: No matches.

- [ ] **Step 5: Run full test suite**

Run: `python3 -m pytest tests/ -q`
Expected: All tests pass, no failures, some skips for Silero.

- [ ] **Step 6: Commit**

```bash
git add tests/test_typer.py tests/test_main.py tests/test_app.py
git commit -m "test: remove Linux tests and is_macos patches"
```

---

## Chunk 2: setup.sh Rewrite

### Task 9: Rewrite setup.sh with preflight checks, venv, and model picker

**Files:**
- Rewrite: `setup.sh`

- [ ] **Step 1: Write the new setup.sh**

```bash
#!/bin/bash
set -e

# ── Preflight checks ────────────────────────────────────────────────────────

if [[ "$(uname)" != "Darwin" ]]; then
    echo "Error: whisper-typer requires macOS."
    exit 1
fi

if [[ "$(uname -m)" != "arm64" ]]; then
    echo "Error: whisper-typer requires Apple Silicon (M-series chip)."
    exit 1
fi

command -v git >/dev/null 2>&1 || {
    echo "Error: git not found. Install: xcode-select --install"
    exit 1
}

xcode-select -p >/dev/null 2>&1 || {
    echo "Error: Xcode Command Line Tools required. Install: xcode-select --install"
    exit 1
}

command -v cmake >/dev/null 2>&1 || {
    echo "Error: cmake not found. Install: brew install cmake (or https://cmake.org)"
    exit 1
}

command -v python3 >/dev/null 2>&1 || {
    echo "Error: python3 not found."
    exit 1
}

echo "Preflight checks passed."
echo ""

# ── Virtual environment ──────────────────────────────────────────────────────

CREATED_VENV=false
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Warning: not running in a virtual environment."
    read -p "Create .venv in project directory? [Y/n] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        python3 -m venv .venv
        source .venv/bin/activate
        CREATED_VENV=true
        echo "Created and activated .venv"
    else
        echo "Proceeding without venv."
    fi
    echo ""
fi

# ── Install Python dependencies ──────────────────────────────────────────────

echo "Installing whisper-typer and macOS dependencies..."
pip install -e ".[macos]"
echo ""

# ── Build whisper.cpp ────────────────────────────────────────────────────────

WHISPER_DIR="${WHISPER_CPP_DIR:-$HOME/.local/share/whisper.cpp}"

echo "whisper.cpp -> $WHISPER_DIR"

if [ ! -d "$WHISPER_DIR" ]; then
    git clone https://github.com/ggerganov/whisper.cpp.git "$WHISPER_DIR"
fi

cd "$WHISPER_DIR"

echo "Building with Metal + CoreML + Flash Attention..."
cmake -B build \
    -DGGML_METAL=ON \
    -DGGML_METAL_EMBED_LIBRARY=ON \
    -DWHISPER_COREML=ON \
    -DGGML_FLASH_ATTN=ON
cmake --build build --config Release -j$(sysctl -n hw.ncpu)
echo ""

# ── Model picker ─────────────────────────────────────────────────────────────

CHIP=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "Apple Silicon")
RAM_BYTES=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
RAM_GB=$((RAM_BYTES / 1073741824))

# Recommendation based on RAM
if [ "$RAM_GB" -ge 24 ]; then
    RECOMMENDED=5
    REC_NAME="large-v3-turbo"
elif [ "$RAM_GB" -ge 16 ]; then
    RECOMMENDED=4
    REC_NAME="medium"
else
    RECOMMENDED=3
    REC_NAME="small"
fi

echo "Detected: $CHIP (${RAM_GB}GB RAM)"
echo ""
echo "Models:"
echo "  1) tiny            75MB   — fastest, lower accuracy"
echo "  2) base           142MB   — fast, decent accuracy"
echo "  3) small          466MB   — good balance"
echo "  4) medium         1.5GB   — high accuracy"
echo "  5) large-v3-turbo 1.5GB   — best accuracy"
echo ""
echo "  ★ Recommended for your device: $REC_NAME"
echo ""
read -p "Pick [1-5] (default: $RECOMMENDED): " MODEL_CHOICE

case "${MODEL_CHOICE:-$RECOMMENDED}" in
    1) MODEL="tiny" ;;
    2) MODEL="base" ;;
    3) MODEL="small" ;;
    4) MODEL="medium" ;;
    5) MODEL="large-v3-turbo" ;;
    *) echo "Invalid choice, using $REC_NAME"; MODEL="$REC_NAME" ;;
esac

if [ ! -f "models/ggml-${MODEL}.bin" ]; then
    echo ""
    echo "Downloading $MODEL model..."
    ./models/download-ggml-model.sh "$MODEL"
fi

# ── CoreML encoder (optional) ───────────────────────────────────────────────

if [ ! -d "models/ggml-${MODEL}-encoder.mlmodelc" ]; then
    echo ""
    echo "CoreML Neural Engine encoder speeds up inference ~2x."
    echo "Generating it takes 10-60 minutes (one-time cost)."
    read -p "Generate CoreML model? [Y/n] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        pip install ane_transformers openai-whisper coremltools 'numpy<2'
        ./models/generate-coreml-model.sh "$MODEL"
    fi
fi

# ── Download Silero VAD model ────────────────────────────────────────────────

echo ""
echo "Downloading Silero VAD model..."
python3 -c "from silero_vad import load_silero_vad; load_silero_vad(onnx=True)" 2>/dev/null || true

# ── Done ─────────────────────────────────────────────────────────────────────

cd - >/dev/null

echo ""
echo "════════════════════════════════════════"
echo "  Setup complete!"
echo ""
echo "  Model:  $MODEL (ggml-${MODEL}.bin)"
if [ "$CREATED_VENV" = true ]; then
    echo "  Venv:   .venv (activate with: source .venv/bin/activate)"
fi
echo ""
echo "  Run:    wv"
echo "════════════════════════════════════════"
```

- [ ] **Step 2: Make executable**

Run: `chmod +x setup.sh` (should already be, but verify)

- [ ] **Step 3: Commit**

```bash
git add setup.sh
git commit -m "feat: rewrite setup.sh with preflight checks, model picker, venv support"
```

---

## Chunk 3: README & Final Verification

### Task 10: Simplify README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Rewrite README.md**

```markdown
# whisper-typer

local speech-to-text that types wherever your cursor is. runs [whisper.cpp](https://github.com/ggerganov/whisper.cpp) on your machine — no API calls, no cloud, no latency.

uses Metal + CoreML + Neural Engine on Apple Silicon for fast inference.

## requirements

- macOS with Apple Silicon (M1/M2/M3/M4)
- Xcode Command Line Tools (`xcode-select --install`)
- cmake (`brew install cmake`)

## setup

```bash
git clone https://github.com/manvirheer/whisper-typer.git
cd whisper-typer
./setup.sh
```

setup.sh handles everything: virtual environment, Python dependencies, building whisper.cpp, model download, and VAD setup.

grant accessibility when prompted: System Settings > Privacy & Security > Accessibility.

## usage

```bash
wv
```

that's it. talk and it types. silence detection handles start/stop automatically.

```
────────────────────────────────────────────────────────────────────────────────
TIME       │ LEVEL    │ MESSAGE
────────────────────────────────────────────────────────────────────────────────
14:23:01   │ INFO     │ whisper-typer activated (menu bar mode)
14:23:01   │ INFO     │ Threads: 8
14:23:05   │ INFO     │ Listening...
14:23:09   │ INFO     │ Recorded 48320 bytes
14:23:10   │ SUCCESS  │ Transcribed in 823ms via server
────────────────────────────────────────────────────────────────────────────────
```

## what's whisper.cpp

[whisper.cpp](https://github.com/ggerganov/whisper.cpp) is a C/C++ port of OpenAI's [Whisper](https://github.com/openai/whisper) speech recognition model. it runs locally on your hardware with no python runtime overhead. the `setup.sh` script clones it, builds with GPU acceleration, and downloads the model.

## config

env vars, all optional:

| var | default | what |
|-----|---------|------|
| `WHISPER_CPP_DIR` | `~/.local/share/whisper.cpp` | whisper.cpp install path |
| `WHISPER_MODEL` | `ggml-large-v3-turbo.bin` | model file |
| `WHISPER_MIC` | system default | mic device name |

```bash
WHISPER_MIC="MacBook Pro Microphone" wv
```

## install as launch agent

```bash
wv install    # start on login
wv uninstall  # remove
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: simplify README for macOS-only setup"
```

---

### Task 11: Final verification

- [ ] **Step 1: Verify no remaining Linux/legacy references in source**

Run: `grep -r "is_macos\|_type_linux\|_record_linux\|LegacyAudio\|_run_legacy\|/dev/shm\|xdotool\|--legacy" whisper_voice_typing/`
Expected: No matches.

- [ ] **Step 2: Verify no remaining broken imports in tests**

Run: `grep -r "is_macos" tests/`
Expected: No matches.

- [ ] **Step 3: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All pass (some Silero skips expected).

- [ ] **Step 4: Verify setup.sh syntax**

Run: `bash -n setup.sh`
Expected: No syntax errors.

- [ ] **Step 5: Commit any remaining fixes, if needed**

Only if previous steps revealed issues.
