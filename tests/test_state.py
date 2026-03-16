"""Tests for the state machine."""

import pytest
from whisper_voice_typing.state import State, StateMachine, TRANSITIONS


class TestTransitionTable:
    """Verify all valid and invalid transitions."""

    def test_all_states_have_transitions(self):
        for state in State:
            assert state in TRANSITIONS, f"{state.name} missing from TRANSITIONS"

    def test_no_self_transitions_in_table(self):
        """Self-transitions are handled by returning current state, not in table."""
        for state, targets in TRANSITIONS.items():
            assert state not in targets, f"{state.name} has self-transition in table"

    def test_idle_can_only_go_to_listening(self):
        assert TRANSITIONS[State.IDLE] == {State.LISTENING}

    def test_error_can_only_go_to_idle(self):
        assert TRANSITIONS[State.ERROR] == {State.IDLE}

    def test_paused_can_go_to_listening_or_idle(self):
        assert TRANSITIONS[State.PAUSED] == {State.LISTENING, State.IDLE}

    def test_detected_can_force_transcribe(self):
        assert State.TRANSCRIBING in TRANSITIONS[State.DETECTED]

    def test_recording_can_force_transcribe(self):
        assert State.TRANSCRIBING in TRANSITIONS[State.RECORDING]


class TestStateMachine:
    def setup_method(self):
        self.sm = StateMachine()

    def test_initial_state_is_idle(self):
        assert self.sm.state == State.IDLE

    def test_valid_transition(self):
        result = self.sm.transition(State.LISTENING)
        assert result == State.LISTENING
        assert self.sm.state == State.LISTENING

    def test_invalid_transition_raises(self):
        with pytest.raises(ValueError, match="Invalid transition"):
            self.sm.transition(State.TRANSCRIBING)

    def test_self_transition_is_noop(self):
        result = self.sm.transition(State.IDLE)
        assert result == State.IDLE

    def test_full_happy_path(self):
        """IDLE -> LISTENING -> DETECTED -> RECORDING -> TRANSCRIBING -> TYPING -> LISTENING"""
        self.sm.transition(State.LISTENING)
        self.sm.transition(State.DETECTED)
        self.sm.transition(State.RECORDING)
        self.sm.transition(State.TRANSCRIBING)
        self.sm.transition(State.TYPING)
        self.sm.transition(State.LISTENING)
        assert self.sm.state == State.LISTENING

    def test_force_transcribe_from_detected(self):
        self.sm.transition(State.LISTENING)
        self.sm.transition(State.DETECTED)
        self.sm.transition(State.TRANSCRIBING)
        assert self.sm.state == State.TRANSCRIBING

    def test_force_transcribe_from_recording(self):
        self.sm.transition(State.LISTENING)
        self.sm.transition(State.DETECTED)
        self.sm.transition(State.RECORDING)
        self.sm.transition(State.TRANSCRIBING)
        assert self.sm.state == State.TRANSCRIBING

    def test_false_trigger_detected_to_listening(self):
        self.sm.transition(State.LISTENING)
        self.sm.transition(State.DETECTED)
        self.sm.transition(State.LISTENING)
        assert self.sm.state == State.LISTENING

    def test_pause_from_listening(self):
        self.sm.transition(State.LISTENING)
        self.sm.transition(State.PAUSED)
        assert self.sm.state == State.PAUSED

    def test_pause_from_detected(self):
        self.sm.transition(State.LISTENING)
        self.sm.transition(State.DETECTED)
        self.sm.transition(State.PAUSED)
        assert self.sm.state == State.PAUSED

    def test_pause_from_recording(self):
        self.sm.transition(State.LISTENING)
        self.sm.transition(State.DETECTED)
        self.sm.transition(State.RECORDING)
        self.sm.transition(State.PAUSED)
        assert self.sm.state == State.PAUSED

    def test_resume_from_paused(self):
        self.sm.transition(State.LISTENING)
        self.sm.transition(State.PAUSED)
        self.sm.transition(State.LISTENING)
        assert self.sm.state == State.LISTENING

    def test_error_from_listening(self):
        self.sm.transition(State.LISTENING)
        self.sm.transition(State.ERROR)
        assert self.sm.state == State.ERROR

    def test_error_recovery(self):
        self.sm.transition(State.LISTENING)
        self.sm.transition(State.ERROR)
        self.sm.transition(State.IDLE)
        assert self.sm.state == State.IDLE

    def test_cannot_go_from_error_to_listening(self):
        self.sm.transition(State.LISTENING)
        self.sm.transition(State.ERROR)
        with pytest.raises(ValueError):
            self.sm.transition(State.LISTENING)

    def test_reset_forces_idle(self):
        self.sm.transition(State.LISTENING)
        self.sm.transition(State.DETECTED)
        self.sm.reset()
        assert self.sm.state == State.IDLE

    def test_can_transition_check(self):
        assert self.sm.can_transition(State.LISTENING) is True
        assert self.sm.can_transition(State.TRANSCRIBING) is False

    def test_can_transition_self(self):
        assert self.sm.can_transition(State.IDLE) is True

    def test_listener_called_on_transition(self):
        transitions = []
        self.sm.on_transition(lambda old, new: transitions.append((old, new)))
        self.sm.transition(State.LISTENING)
        self.sm.transition(State.DETECTED)
        assert transitions == [
            (State.IDLE, State.LISTENING),
            (State.LISTENING, State.DETECTED),
        ]

    def test_listener_not_called_on_self_transition(self):
        transitions = []
        self.sm.on_transition(lambda old, new: transitions.append((old, new)))
        self.sm.transition(State.IDLE)  # self-transition
        assert transitions == []

    def test_invalid_transition_error_message(self):
        with pytest.raises(ValueError, match="IDLE -> TRANSCRIBING"):
            self.sm.transition(State.TRANSCRIBING)

    def test_stop_from_any_active_state(self):
        """All active states should be able to transition to IDLE (stop)."""
        for state in [State.LISTENING, State.DETECTED, State.RECORDING, State.TRANSCRIBING, State.TYPING]:
            sm = StateMachine()
            # navigate to the state
            sm.transition(State.LISTENING)
            if state == State.LISTENING:
                pass
            elif state == State.DETECTED:
                sm.transition(State.DETECTED)
            elif state == State.RECORDING:
                sm.transition(State.DETECTED)
                sm.transition(State.RECORDING)
            elif state == State.TRANSCRIBING:
                sm.transition(State.DETECTED)
                sm.transition(State.TRANSCRIBING)
            elif state == State.TYPING:
                sm.transition(State.DETECTED)
                sm.transition(State.TRANSCRIBING)
                sm.transition(State.TYPING)

            sm.transition(State.IDLE)
            assert sm.state == State.IDLE, f"Failed to stop from {state.name}"
