"""
State machine for whisper-typer.

                      start()
                        |
                        v
  IDLE -----> LISTENING ---------> DETECTED --300ms--> RECORDING
    ^            ^  ^               |    |                  |
    |            |  |        <300ms |    | force             | silence
  stop()        |  |        (false)|    | click             | or force
    |       TYPING  |       ------+    |                  |
    |          ^    |                   v                  v
    |          +----+---------- TRANSCRIBING <------------+
    |                                  |
    +----------------------------------+ (on error)

  Any state -> PAUSED -> LISTENING (resume)
  Any state -> ERROR -> IDLE (reset)
"""

import threading
from enum import Enum, auto


class State(Enum):
    IDLE = auto()
    LISTENING = auto()
    DETECTED = auto()
    RECORDING = auto()
    TRANSCRIBING = auto()
    TYPING = auto()
    PAUSED = auto()
    ERROR = auto()


TRANSITIONS: dict[State, set[State]] = {
    State.IDLE: {State.LISTENING},
    State.LISTENING: {State.DETECTED, State.PAUSED, State.IDLE, State.ERROR},
    State.DETECTED: {State.RECORDING, State.LISTENING, State.TRANSCRIBING, State.PAUSED, State.IDLE, State.ERROR},
    State.RECORDING: {State.TRANSCRIBING, State.LISTENING, State.PAUSED, State.IDLE, State.ERROR},
    State.TRANSCRIBING: {State.TYPING, State.LISTENING, State.IDLE, State.ERROR},
    State.TYPING: {State.LISTENING, State.IDLE, State.ERROR},
    State.PAUSED: {State.LISTENING, State.IDLE},
    State.ERROR: {State.IDLE},
}


class StateMachine:
    def __init__(self):
        self._state = State.IDLE
        self._listeners: list = []
        self._lock = threading.Lock()

    @property
    def state(self) -> State:
        return self._state

    def transition(self, new_state: State) -> State:
        with self._lock:
            if new_state == self._state:
                return self._state
            allowed = TRANSITIONS.get(self._state, set())
            if new_state not in allowed:
                raise ValueError(
                    f"Invalid transition: {self._state.name} -> {new_state.name}. "
                    f"Allowed: {', '.join(s.name for s in allowed)}"
                )
            old_state = self._state
            self._state = new_state

        for listener in self._listeners:
            listener(old_state, new_state)
        return new_state

    def on_transition(self, callback) -> None:
        self._listeners.append(callback)

    def can_transition(self, new_state: State) -> bool:
        if new_state == self._state:
            return True
        return new_state in TRANSITIONS.get(self._state, set())

    def reset(self) -> None:
        with self._lock:
            self._state = State.IDLE
