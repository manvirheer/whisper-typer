# Whisper Voice Typing

Voice-to-text typing system using whisper.cpp with GPU acceleration.

## Installation

```bash
# Install Python dependencies
pip install -r requirements.txt

# Ensure system dependencies are installed (Fedora)
sudo dnf install sox xdotool curl jq
```

## Usage

### Run the Python version (recommended):

```bash
# Using the launcher script
./run_voice_typing.py

# Or run as a module
python3 -m whisper_voice_typing
```

### Run the bash version:

```bash
./run.sh
```

## Project Structure

```
whisper_voice_typing/
├── config.py       # Configuration management
├── utils.py        # Logging and environment setup
├── server.py       # Whisper server management
├── audio.py        # Audio recording and transcription
├── app.py          # Main application logic
├── __init__.py     # Package initialization
└── __main__.py     # Module entry point

run_voice_typing.py # Simple launcher script
run.sh              # Legacy bash script
requirements.txt    # Python dependencies
```

## Configuration

Edit `whisper_voice_typing/config.py` to customize:

- Audio device
- Whisper model path
- Recording parameters (silence thresholds, durations)
- Server settings

## How It Works

1. **Records audio** using sox with silence detection
2. **Transcribes** via whisper-server (fast) or direct CLI (fallback)
3. **Types the result** using xdotool
4. Cleans up temporary files automatically

## Troubleshooting

- **Dependencies missing**: Check error messages on startup
- **Audio not detected**: Adjust silence thresholds in config.py
- **Recording too short**: Lower `min_file_size` in config.py
- **Server issues**: Check whisper-server binary path
