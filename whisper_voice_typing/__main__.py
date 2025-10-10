"""Entry point for running whisper_voice_typing as a module"""

from .app import WhisperVoiceTyping


def main():
    """Main entry point"""
    app = WhisperVoiceTyping()
    app.run()


if __name__ == "__main__":
    main()
