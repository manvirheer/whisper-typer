"""
macOS menu bar via rumps.

  STATE          | ICON  | TITLE  | KEY MENU ITEMS
  IDLE           | ○     | (none) | Start Listening, Quit
  LISTENING      | ○     | (none) | Listening..., Pause, Stop
  DETECTED       | ●     | (none) | Speech detected, Transcribe Now
  RECORDING      | ●     | "3s"   | Recording..., Transcribe Now
  TRANSCRIBING   | ◐     | "..."  | Transcribing...
  TYPING         | ●     | (none) | Typed!
  PAUSED         | ○     | "||"   | Resume, Stop
  ERROR          | ✗     | "!"    | Error: ..., Retry

UI updates via rumps.Timer polling a queue.Queue every 100ms.
"""

import queue, logging
from collections import deque
from .state import State

log = logging.getLogger("whisper_voice_typing")

try:
    import rumps
    _HAS_RUMPS = True
except ImportError:
    _HAS_RUMPS = False

_ICONS = {
    State.IDLE: "\u25cb", State.LISTENING: "\u25cb",
    State.DETECTED: "\u25cf", State.RECORDING: "\u25cf",
    State.TRANSCRIBING: "\u25d0", State.TYPING: "\u25cf",
    State.PAUSED: "\u25cb", State.ERROR: "\u2717",
}

_TITLES = {
    State.IDLE: "", State.LISTENING: "", State.DETECTED: "",
    State.RECORDING: "", State.TRANSCRIBING: "...",
    State.TYPING: "", State.PAUSED: "||", State.ERROR: "!",
}

_STATUS_TEXT = {
    State.IDLE: "Idle", State.LISTENING: "Listening...",
    State.DETECTED: "Speech detected", State.TRANSCRIBING: "Transcribing...",
    State.TYPING: "Typed!", State.PAUSED: "Paused",
}


class StateUpdate:
    def __init__(self, state: State, detail: str = "", duration: float = 0.0):
        self.state, self.detail, self.duration = state, detail, duration


class TranscriptionResult:
    def __init__(self, text: str):
        self.text = text


class WhisperMenuBar:
    def __init__(self, config, ui_queue: queue.Queue, command_queue: queue.Queue):
        if not _HAS_RUMPS:
            raise ImportError("rumps required: pip install whisper-typer[macos]")

        self.config = config
        self._ui_queue, self._command_queue = ui_queue, command_queue
        self._current_state = State.IDLE
        self._history: deque[str] = deque(maxlen=config.transcription_history_size)

        self._app = rumps.App("whisper-typer", title=_ICONS[State.IDLE], quit_button=None)
        self._build_menu()
        self._timer = rumps.Timer(self._poll_queue, config.menu_update_interval)
        self._timer.start()

    def _build_menu(self) -> None:
        self._status_item = rumps.MenuItem("Idle", callback=None)
        self._transcribe_btn = rumps.MenuItem("Transcribe Now", callback=self._on_transcribe)
        self._toggle_btn = rumps.MenuItem("Start Listening", callback=self._on_toggle)
        self._pause_btn = rumps.MenuItem("Pause", callback=self._on_pause)
        self._quit_btn = rumps.MenuItem("Quit", callback=self._on_quit)

        self._app.menu = [
            self._status_item, None,
            self._transcribe_btn, self._toggle_btn, self._pause_btn,
            None, self._quit_btn,
        ]
        self._transcribe_btn.set_callback(None)
        self._pause_btn.set_callback(None)
        self._history_items: list[rumps.MenuItem] = []

    def _poll_queue(self, _sender) -> None:
        while True:
            try:
                msg = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(msg, StateUpdate):
                self._apply_state(msg)
            elif isinstance(msg, TranscriptionResult):
                self._add_transcription(msg.text)

    def _apply_state(self, update: StateUpdate) -> None:
        self._current_state = update.state
        icon = _ICONS.get(update.state, "\u25cb")

        if update.state == State.RECORDING and update.duration > 0:
            self._app.title = f"{icon} {int(update.duration)}s"
        else:
            suffix = _TITLES.get(update.state, "")
            self._app.title = f"{icon} {suffix}".strip() if suffix else icon

        if update.state == State.RECORDING:
            self._status_item.title = f"Recording... {int(update.duration)}s"
        elif update.state == State.ERROR:
            self._status_item.title = f"Error: {update.detail}" if update.detail else "Error"
        else:
            self._status_item.title = _STATUS_TEXT.get(update.state, "Unknown")

        can_transcribe = update.state in (State.DETECTED, State.RECORDING)
        self._transcribe_btn.set_callback(self._on_transcribe if can_transcribe else None)

        if update.state == State.IDLE:
            self._toggle_btn.title = "Start Listening"
            self._toggle_btn.set_callback(self._on_toggle)
            self._pause_btn.set_callback(None)
        elif update.state == State.PAUSED:
            self._toggle_btn.title, self._pause_btn.title = "Stop", "Resume"
            self._toggle_btn.set_callback(self._on_toggle)
            self._pause_btn.set_callback(self._on_pause)
        elif update.state == State.ERROR:
            self._toggle_btn.title = "Retry"
            self._toggle_btn.set_callback(self._on_toggle)
            self._pause_btn.set_callback(None)
        else:
            self._toggle_btn.title, self._pause_btn.title = "Stop", "Pause"
            self._toggle_btn.set_callback(self._on_toggle)
            self._pause_btn.set_callback(self._on_pause)

    def _add_transcription(self, text: str) -> None:
        display = text if len(text) <= 60 else text[:57] + "..."
        self._history.appendleft(display)
        self._rebuild_history_menu()

    def _rebuild_history_menu(self) -> None:
        for item in self._history_items:
            try: del self._app.menu[item.title]
            except KeyError: pass
        self._history_items.clear()
        if not self._history:
            return

        header = rumps.MenuItem("Recent:", callback=None)
        header.set_callback(None)
        self._history_items.append(header)
        for text in self._history:
            item = rumps.MenuItem(f"  {text}", callback=None)
            self._history_items.append(item)

        insert_pos = "Quit"
        for item in reversed(self._history_items):
            self._app.menu.insert_before(insert_pos, item)
            insert_pos = item.title

    def check_permissions(self) -> dict[str, bool | None]:
        perms: dict[str, bool | None] = {}
        try:
            import sounddevice as sd
            sd.query_devices(kind='input')
            perms["mic"] = True
        except Exception:
            perms["mic"] = False
        perms["whisper"] = self.config.whisper_executable.exists() and self.config.whisper_model.exists()
        perms["accessibility"] = None
        return perms

    def show_onboarding(self) -> None:
        perms = self.check_permissions()
        labels = {True: "ready", False: "not ready", None: "unknown"}
        items = [rumps.MenuItem("Setup Status:", callback=None)]
        items[0].set_callback(None)
        for name, ok in perms.items():
            item = rumps.MenuItem(f"  {name}: {labels[ok]}", callback=None)
            item.set_callback(None)
            items.append(item)

        self._app.menu.insert_before("Quit", None)
        for item in items:
            self._app.menu.insert_before("Quit", item)

    def _on_transcribe(self, _): self._command_queue.put("force_transcribe")
    def _on_toggle(self, _):
        self._command_queue.put("start" if self._current_state in (State.IDLE, State.ERROR) else "stop")
    def _on_pause(self, _):
        self._command_queue.put("resume" if self._current_state == State.PAUSED else "pause")
    def _on_quit(self, _):
        self._command_queue.put("quit")
        rumps.quit_application()

    def run(self) -> None:
        self.show_onboarding()
        self._app.run()
