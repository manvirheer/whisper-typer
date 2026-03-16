import sys
import argparse
import plistlib
import shutil
from pathlib import Path

from .app import WhisperVoiceTyping
from .config import Config
from .utils import is_macos


def _install_launchagent() -> None:
    """Create a LaunchAgent plist to start whisper-typer at login."""
    if not is_macos():
        print("LaunchAgent is macOS-only")
        sys.exit(1)

    config = Config()
    config.launchagent_dir.mkdir(parents=True, exist_ok=True)
    config.log_dir.mkdir(parents=True, exist_ok=True)

    wv_path = shutil.which("wv")
    if not wv_path:
        print("Error: 'wv' command not found in PATH. Install with: pip install -e .")
        sys.exit(1)

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

    print(f"LaunchAgent installed: {config.launchagent_plist}")
    print(f"Logs: {config.log_dir}")
    print("It will start automatically at next login.")
    print(f"To start now: launchctl load {config.launchagent_plist}")


def _uninstall_launchagent() -> None:
    """Remove the LaunchAgent plist."""
    if not is_macos():
        print("LaunchAgent is macOS-only")
        sys.exit(1)

    config = Config()
    plist_path = config.launchagent_plist

    if plist_path.exists():
        # unload first
        import subprocess
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
        plist_path.unlink()
        print(f"LaunchAgent removed: {plist_path}")
    else:
        print("No LaunchAgent installed")


def main():
    parser = argparse.ArgumentParser(
        prog="wv",
        description="whisper-typer: local voice-to-text that types wherever your cursor is",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["install", "uninstall"],
        help="install/uninstall LaunchAgent for login startup",
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="force legacy mode (sox + terminal, no menu bar)",
    )

    args = parser.parse_args()

    if args.command == "install":
        _install_launchagent()
    elif args.command == "uninstall":
        _uninstall_launchagent()
    else:
        app = WhisperVoiceTyping()
        if args.legacy:
            app._run_legacy()
        else:
            app.run()


if __name__ == "__main__":
    main()
