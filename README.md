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
