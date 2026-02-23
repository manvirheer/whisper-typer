# whisper-typer

local speech-to-text that types wherever your cursor is. runs [whisper.cpp](https://github.com/ggerganov/whisper.cpp) on your machine — no API calls, no cloud, no latency.

on apple silicon it hits Metal + CoreML + Neural Engine for fast inference. linux gets vulkan/cuda.

## setup (macOS)

```bash
brew install sox ffmpeg
pip install -e .
./setup.sh
```

grant accessibility when prompted: System Settings > Privacy & Security > Accessibility.

## setup (linux)

```bash
# fedora
sudo dnf install sox xdotool curl jq
# ubuntu
sudo apt install sox xdotool curl jq

pip install -e .
./setup.sh
```

## usage

```bash
wv
```

that's it. talk and it types. silence detection handles start/stop automatically.

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
