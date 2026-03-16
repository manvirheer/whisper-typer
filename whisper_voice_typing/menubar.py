"""
macOS menu bar app using rumps.

Menu bar state display:

  STATE          | ICON TINT  | TITLE TEXT    | MENU ITEMS
  ---------------|------------|---------------|----------------------------------
  IDLE           | gray       | (none)        | [Start Listening] [Quit]
  LISTENING      | gray       | (none)        | [Listening...] [Pause] [Stop] [Quit]
  DETECTED       | blue       | (none)        | [Speech detected] [Transcribe Now] [Pause] [Stop] [Quit]
  RECORDING      | blue       | "3s"          | [Recording... 3s] [Transcribe Now] [Pause] [Stop] [Quit]
  TRANSCRIBING   | gray       | "..."         | [Transcribing...] [Stop] [Quit]
  TYPING         | green      | (none)        | [Typed!] [Stop] [Quit]
  PAUSED         | gray       | "||"          | [Resume] [Stop] [Quit]
  ERROR          | red        | "!"           | [Error: ...] [Retry] [Quit]

Thread safety: all UI updates happen on the main thread via rumps.Timer
polling a queue.Queue. Background threads put state updates on the queue.
"""

import queue
import logging
from collections import deque

from .state import State

log = logging.getLogger("whisper_voice_typing")

try:
    import rumps
    _HAS_RUMPS = True
except ImportError:
    _HAS_RUMPS = False


# icon characters (used as title when no template images available)
_STATE_ICONS = {
    State.IDLE: "\u25cb",          # ○
    State.LISTENING: "\u25cb",     # ○
    State.DETECTED: "\u25cf",      # ●
    State.RECORDING: "\u25cf",     # ●
    State.TRANSCRIBING: "\u25d0",  # ◐
    State.TYPING: "\u25cf",        # ●
    State.PAUSED: "\u25cb",        # ○
    State.ERROR: "\u2717",         # ✗
}

_STATE_TITLES = {
    State.IDLE: "",
    State.LISTENING: "",
    State.DETECTED: "",
    State.RECORDING: "",  # overridden with duration counter
    State.TRANSCRIBING: "...",
    State.TYPING: "",
    State.PAUSED: "||",
    State.ERROR: "!",
}


class StateUpdate:
    """Message from background thread to menu bar."""
    def __init__(self, state: State, detail: str = "", duration: float = 0.0):
        self.state = state
        self.detail = detail
        self.duration = duration


class TranscriptionResult:
    """Message carrying a completed transcription."""
    def __init__(self, text: str):
        self.text = text


class WhisperMenuBar:
    """Menu bar app for whisper-typer. Runs on the main thread."""

    def __init__(self, config, ui_queue: queue.Queue, command_queue: queue.Queue):
        """
        Args:
            config: Config instance
            ui_queue: Queue for receiving StateUpdate/TranscriptionResult from background threads
            command_queue: Queue for sending commands (force_transcribe, toggle, stop) to processing thread
        """
        if not _HAS_RUMPS:
            raise ImportError("rumps is required for menu bar: pip install whisper-typer[macos]")

        self.config = config
        self._ui_queue = ui_queue
        self._command_queue = command_queue
        self._current_state = State.IDLE
        self._history: deque[str] = deque(maxlen=config.transcription_history_size)
        self._error_detail = ""
        self._onboarded = False
        self._permissions_ok = {"mic": None, "accessibility": None, "whisper": None}

        self._app = rumps.App(
            "whisper-typer",
            title=_STATE_ICONS[State.IDLE],
            quit_button=None,  # we add our own
        )
        self._build_menu()
        self._setup_timer()

    def _build_menu(self) -> None:
        """Build the initial menu structure."""
        self._status_item = rumps.MenuItem("Idle", callback=None)
        self._status_item.set_callback(None)

        self._transcribe_btn = rumps.MenuItem("Transcribe Now", callback=self._on_transcribe)
        self._toggle_btn = rumps.MenuItem("Start Listening", callback=self._on_toggle)
        self._pause_btn = rumps.MenuItem("Pause", callback=self._on_pause)

        self._history_separator = rumps.separator
        self._history_items: list[rumps.MenuItem] = []

        self._quit_btn = rumps.MenuItem("Quit", callback=self._on_quit)

        self._app.menu = [
            self._status_item,
            None,  # separator
            self._transcribe_btn,
            self._toggle_btn,
            self._pause_btn,
            None,  # separator
            self._quit_btn,
        ]

        # initial state: only Start and Quit visible
        self._transcribe_btn.set_callback(None)
        self._pause_btn.set_callback(None)

    def _setup_timer(self) -> None:
        """Poll the UI queue every 100ms for state updates."""
        self._timer = rumps.Timer(self._poll_queue, self.config.menu_update_interval)
        self._timer.start()

    def _poll_queue(self, _sender) -> None:
        """Process all pending UI updates from the queue."""
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
        """Apply a state change to the menu bar UI."""
        self._current_state = update.state
        icon = _STATE_ICONS.get(update.state, "\u25cb")

        # title: icon + optional duration/detail
        if update.state == State.RECORDING and update.duration > 0:
            title = f"{icon} {int(update.duration)}s"
        else:
            suffix = _STATE_TITLES.get(update.state, "")
            title = f"{icon} {suffix}".strip() if suffix else icon

        self._app.title = title

        # update status menu item
        status_text = {
            State.IDLE: "Idle",
            State.LISTENING: "Listening...",
            State.DETECTED: "Speech detected",
            State.RECORDING: f"Recording... {int(update.duration)}s",
            State.TRANSCRIBING: "Transcribing...",
            State.TYPING: "Typed!",
            State.PAUSED: "Paused",
            State.ERROR: f"Error: {update.detail}" if update.detail else "Error",
        }
        self._status_item.title = status_text.get(update.state, "Unknown")

        # update button visibility/labels
        can_transcribe = update.state in (State.DETECTED, State.RECORDING)
        self._transcribe_btn.set_callback(self._on_transcribe if can_transcribe else None)

        if update.state == State.IDLE:
            self._toggle_btn.title = "Start Listening"
            self._toggle_btn.set_callback(self._on_toggle)
            self._pause_btn.set_callback(None)
        elif update.state == State.PAUSED:
            self._toggle_btn.title = "Stop"
            self._toggle_btn.set_callback(self._on_toggle)
            self._pause_btn.title = "Resume"
            self._pause_btn.set_callback(self._on_pause)
        elif update.state == State.ERROR:
            self._toggle_btn.title = "Retry"
            self._toggle_btn.set_callback(self._on_toggle)
            self._pause_btn.set_callback(None)
            self._error_detail = update.detail
        else:
            self._toggle_btn.title = "Stop"
            self._toggle_btn.set_callback(self._on_toggle)
            self._pause_btn.title = "Pause"
            self._pause_btn.set_callback(self._on_pause)

    def _add_transcription(self, text: str) -> None:
        """Add a transcription to the history in the menu dropdown."""
        # truncate long transcriptions for display
        display = text if len(text) <= 60 else text[:57] + "..."
        self._history.appendleft(display)
        self._rebuild_history_menu()

    def _rebuild_history_menu(self) -> None:
        """Rebuild the transcription history section of the menu."""
        # remove old history items
        for item in self._history_items:
            try:
                del self._app.menu[item.title]
            except KeyError:
                pass

        self._history_items.clear()

        if not self._history:
            return

        # insert history items before the quit separator
        # we insert after pause button
        for i, text in enumerate(self._history):
            item = rumps.MenuItem(f"  {text}", callback=None)
            self._history_items.append(item)

        # add a header
        header = rumps.MenuItem("Recent:", callback=None)
        header.set_callback(None)
        self._history_items.insert(0, header)

        # insert all history items before quit
        insert_pos = "Quit"
        for item in reversed(self._history_items):
            self._app.menu.insert_before(insert_pos, item)
            insert_pos = item.title

    def check_permissions(self) -> dict[str, bool]:
        """Check system permissions for onboarding display."""
        import shutil

        # mic: try opening sounddevice
        try:
            import sounddevice as sd
            sd.query_devices(kind='input')
            self._permissions_ok["mic"] = True
        except Exception:
            self._permissions_ok["mic"] = False

        # whisper: check binary exists
        self._permissions_ok["whisper"] = self.config.whisper_executable.exists() and self.config.whisper_model.exists()

        # accessibility: can't easily check without trying CGEvent
        # will be determined on first type attempt
        self._permissions_ok["accessibility"] = None

        return self._permissions_ok

    def show_onboarding(self) -> None:
        """Show first-launch permission checklist in the menu."""
        perms = self.check_permissions()

        items = []
        for name, ok in perms.items():
            if ok is True:
                items.append(rumps.MenuItem(f"  {name}: ready", callback=None))
            elif ok is False:
                items.append(rumps.MenuItem(f"  {name}: not ready", callback=None))
            else:
                items.append(rumps.MenuItem(f"  {name}: unknown", callback=None))

        header = rumps.MenuItem("Setup Status:", callback=None)
        header.set_callback(None)

        insert_pos = "Quit"
        self._app.menu.insert_before(insert_pos, None)  # separator
        self._app.menu.insert_before(insert_pos, header)
        for item in items:
            item.set_callback(None)
            self._app.menu.insert_before(insert_pos, item)

        self._onboarded = True

    # --- Command callbacks ---

    def _on_transcribe(self, _sender) -> None:
        """User clicked Transcribe Now."""
        self._command_queue.put("force_transcribe")

    def _on_toggle(self, _sender) -> None:
        """User clicked Start/Stop/Retry."""
        if self._current_state == State.IDLE or self._current_state == State.ERROR:
            self._command_queue.put("start")
        else:
            self._command_queue.put("stop")

    def _on_pause(self, _sender) -> None:
        """User clicked Pause/Resume."""
        if self._current_state == State.PAUSED:
            self._command_queue.put("resume")
        else:
            self._command_queue.put("pause")

    def _on_quit(self, _sender) -> None:
        """User clicked Quit."""
        self._command_queue.put("quit")
        rumps.quit_application()

    def run(self) -> None:
        """Start the menu bar app. Blocks on the main thread."""
        if not self._onboarded:
            self.show_onboarding()
        self._app.run()
