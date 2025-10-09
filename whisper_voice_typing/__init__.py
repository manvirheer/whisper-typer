"""
Whisper Voice Typing - Python Edition
Captures audio, transcribes using whisper.cpp (GPU-accelerated), and types the result.
Optimized for Fedora with AMD GPU.
"""

__version__ = "2.0.0"

from .config import Config
from .server import WhisperServer
from .audio import AudioProcessor
from .app import WhisperVoiceTyping

__all__ = [
    "Config",
    "WhisperServer",
    "AudioProcessor",
    "WhisperVoiceTyping",
]
