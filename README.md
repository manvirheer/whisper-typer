# whisper-typer

local speech to text. runs whisper.cpp on your mac. talks, types. no cloud, no api, no latency.

metal + coreml + neural engine. apple silicon only.

## setup

```
git clone https://github.com/manvirheer/whisper-typer.git
cd whisper-typer
./setup.sh
```

setup.sh does everything. venv, deps, builds whisper.cpp, downloads model, picks the right size for your hardware.

grant accessibility access when it asks. system settings > privacy > accessibility.

## run

```
wv
```

talk and it types wherever your cursor is. silence detection handles start and stop.

you get a menu bar icon. switch mics, pause, force transcribe, see history. all from the menu bar.

## config

env vars. all optional.

| var | default | what |
|-----|---------|------|
| `WHISPER_CPP_DIR` | `~/.local/share/whisper.cpp` | whisper.cpp path |
| `WHISPER_MODEL` | `ggml-large-v3-turbo.bin` | model file |
| `WHISPER_MIC` | system default | mic device |

```
WHISPER_MIC="MacBook Pro Microphone" wv
```

## launch agent

```
wv install
wv uninstall
```

## how it works

whisper.cpp is a c++ port of openai whisper. runs locally, no python inference overhead. silero vad detects when you start and stop talking. 512 sample chunks, adaptive silence timeout that learns your speech patterns. pre roll buffer so it never clips the start of your sentence.

three threads. capture thread writes audio to a ring buffer. processing thread runs vad and sends to whisper server for transcription. main thread runs the menu bar.
