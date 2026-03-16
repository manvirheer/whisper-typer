import sys, argparse, plistlib, shutil
from pathlib import Path
from .app import WhisperVoiceTyping
from .config import Config
from .utils import is_macos


def _install_launchagent() -> None:
    if not is_macos():
        print("LaunchAgent is macOS-only"); sys.exit(1)

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
    if not is_macos():
        print("LaunchAgent is macOS-only"); sys.exit(1)

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
    parser.add_argument("--legacy", action="store_true", help="force legacy mode (no menu bar)")
    args = parser.parse_args()

    if args.command == "install":
        _install_launchagent()
    elif args.command == "uninstall":
        _uninstall_launchagent()
    else:
        app = WhisperVoiceTyping()
        app._run_legacy() if args.legacy else app.run()


if __name__ == "__main__":
    main()
