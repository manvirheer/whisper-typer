# Setup Overhaul: macOS-Only, Model Picker, Preflight Checks

**Date:** 2026-03-16
**Status:** Approved

## Context

whisper-typer currently supports both macOS and Linux with a legacy ffmpeg+sox fallback pipeline. The project is narrowing scope to macOS with Apple Silicon only. The setup experience has friction: no preflight checks, hardcoded model, no venv guidance, and redundant README steps.

## Decisions

1. **Drop Linux support entirely** — remove all Linux code paths, legacy pipeline, and `--legacy` CLI flag
2. **Preflight checks in setup.sh** — fail fast with clear messages for missing tools
3. **Model picker** — detect chip and RAM, recommend a model, let user choose
4. **Venv detection** — warn if not in a venv, offer to create one, but don't force
5. **Simplify README** — just `git clone` + `./setup.sh` + `wv`

## Code Removal

### Delete entirely

- `LegacyAudioProcessor` class in `audio.py` (~110 lines) — includes `_record_macos()` (ffmpeg+sox), `_record_linux()`, `_check_audio()`, `process_audio()`, temp dir management
- `_run_legacy()` and `_cleanup_legacy()` in `app.py` (~50 lines)
- `_type_linux()` function in `typer.py`
- `--legacy` CLI flag in `__main__.py`
- `TestTypeTextLinux` class in `tests/test_typer.py`
- `test_install_exits_on_linux` and `test_legacy_flag` in `tests/test_main.py`
- `TestCanUseNewPipeline` class in `tests/test_app.py`
- `is_macos()` utility function in `utils.py`
- Linux setup sections in `README.md`

### Simplify

- **`audio.py`**: Remove `/dev/shm` check, always use `/tmp` for temp dir
- **`config.py`**: Remove sox silence detection settings (`silence_start_duration`, `silence_start_threshold`, `silence_end_duration`, `silence_end_threshold`). Remove `use_new_pipeline` parameter from `validate()`. Only validate whisper binaries, model, and sounddevice.
- **`app.py`**: `run()` directly runs macOS pipeline. Remove `_can_use_new_pipeline()` — if deps missing, error with "Run ./setup.sh". Remove `is_macos()` import and checks.
- **`typer.py`**: Remove `is_macos()` guard and `_type_linux()`. The PyObjC conditional import (`if is_macos(): try: from AppKit ...`) becomes unconditional: always attempt the import, set `_HAS_PYOBJC` accordingly. Keep native PyObjC path + subprocess fallback (pbcopy+osascript).
- **`__main__.py`**: Remove `is_macos()` checks in install/uninstall (they're macOS-only commands on a macOS-only app now).
- **`config.py`**: Also remove `post_processing_delay` and `no_audio_delay` — only used by legacy pipeline. Remove `~/personal/whisper.cpp` from `_find_whisper_dir()` candidates (personal path leak).
- **`tests/test_typer.py`**: Strip `@patch("whisper_voice_typing.typer.is_macos", return_value=True)` from all remaining test classes (`TestTypeTextMacOSSubprocess`, `TestClipboardRestoration`, `TestNativeMacOS`, `TestSendCmdV`) since there's no longer an `is_macos` to patch.

## setup.sh Overhaul

### Preflight Checks (fail fast)

```bash
# 1. macOS check
[[ "$(uname)" != "Darwin" ]] && echo "macOS only" && exit 1

# 2. Apple Silicon check
[[ "$(uname -m)" != "arm64" ]] && echo "Apple Silicon (M-series) required" && exit 1

# 3. Required tools
command -v git >/dev/null || { echo "git not found. Install: xcode-select --install"; exit 1; }
command -v cmake >/dev/null || { echo "cmake not found. Install: brew install cmake (or https://cmake.org)"; exit 1; }
xcode-select -p >/dev/null 2>&1 || { echo "Xcode CLI tools required: xcode-select --install"; exit 1; }
command -v python3 >/dev/null || { echo "python3 not found"; exit 1; }
```

### Venv Detection

```bash
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Warning: not running in a virtual environment."
    read -p "Create .venv in project directory? [Y/n] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        python3 -m venv .venv
        source .venv/bin/activate
        echo "Activated .venv"
    fi
fi
```

### Model Picker

Detect hardware:
- Chip: `sysctl -n machdep.cpu.brand_string` (e.g., "Apple M2 Pro")
- RAM: `sysctl -n hw.memsize` (bytes → GB)

Display:

```
Detected: Apple M2 Pro (16GB RAM)

Models:
  1) tiny            75MB   — fastest, lower accuracy
  2) base           142MB   — fast, decent accuracy
  3) small          466MB   — good balance
  4) medium         1.5GB   — high accuracy
  5) large-v3-turbo 1.5GB   — best accuracy

  ★ Recommended for your device: medium

Pick [1-5] (default: 4):
```

Recommendation logic (using range comparisons since `hw.memsize` returns bytes):
- RAM < 16GB → `small` (option 3)
- 16GB ≤ RAM < 24GB → `medium` (option 4)
- RAM ≥ 24GB → `large-v3-turbo` (option 5)

### Install Order

1. Preflight checks (macOS, arm64, git, cmake, xcode-select)
2. Venv check/offer
3. `pip install -e ".[macos]"`
4. Clone whisper.cpp (if not already present)
5. Build with Metal + CoreML + Flash Attention
6. Model picker → download selected model
7. CoreML encoder prompt (with added context: "Speeds up inference ~2x. Takes 10-60 min.")
8. Download Silero VAD model (`python3 -c "from silero_vad import load_silero_vad; load_silero_vad(onnx=True)"`)
9. Print success message and next steps

### Success Output

```
Setup complete!

  Model:  medium (ggml-medium.bin)
  Venv:   .venv (activate with: source .venv/bin/activate)

  Run:    wv
```

If the user declined venv creation, omit the Venv line.

## First-Run Experience

When `wv` is run before setup.sh:
- `config.py` `validate()` catches missing whisper-cli or model
- Error message changed to: `"whisper.cpp not set up. Run: ./setup.sh"`

When macOS deps are missing (sounddevice/rumps):
- `app.py` `run()` catches ImportError
- Error message: `"Dependencies missing. Run: ./setup.sh"`

## README Changes

Simplify to:

```markdown
## setup

git clone https://github.com/manvirheer/whisper-typer.git
cd whisper-typer
./setup.sh

Grant accessibility when prompted: System Settings > Privacy & Security > Accessibility.

## usage

wv

Talk and it types. Silence detection handles start/stop automatically.
```

Keep: config env vars table, what's whisper.cpp section, usage output example.
Remove: Linux sections, `brew install sox ffmpeg`, manual `pip install` step.

## Files Changed

| File | Change |
|------|--------|
| `setup.sh` | Full rewrite: preflight, venv, model picker |
| `README.md` | Simplify setup, remove Linux |
| `whisper_voice_typing/app.py` | Remove legacy pipeline, `_can_use_new_pipeline()`, simplify `run()` |
| `whisper_voice_typing/audio.py` | Remove `LegacyAudioProcessor`, `/dev/shm` check |
| `whisper_voice_typing/typer.py` | Remove `_type_linux()`, make PyObjC import unconditional, remove `is_macos` import |
| `whisper_voice_typing/config.py` | Remove sox settings, `post_processing_delay`, `no_audio_delay`, `~/personal/whisper.cpp` candidate, simplify `validate()` |
| `whisper_voice_typing/utils.py` | Remove `is_macos()` |
| `whisper_voice_typing/__main__.py` | Remove `--legacy` flag, `is_macos()` checks |
| `tests/test_typer.py` | Remove `TestTypeTextLinux`, strip `is_macos` patches from all remaining test classes |
| `tests/test_main.py` | Remove `test_install_exits_on_linux`, `test_legacy_flag` |
| `tests/test_app.py` | Remove `TestCanUseNewPipeline`, update tests for simplified `run()` |
