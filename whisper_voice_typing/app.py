"""
whisper-typer application controller.

Threading architecture (macOS new pipeline):

  CAPTURE THREAD            PROCESSING THREAD             MAIN THREAD
  (sounddevice callback)    (VAD + transcribe + type)     (rumps menu bar)
  +------------------+      +------------------------+    +-----------------+
  | sounddevice      |      | Read ring buffer       |    | rumps.App       |
  | callback writes  |----->| Run Silero VAD         |    | NSRunLoop       |
  | to ring buffer   | ring | State machine drives   |    |                 |
  |                  | buf  | transitions:           |--->| 100ms Timer     |
  | Never stops.     |      |   LISTENING->DETECTED  | q  | polls ui_queue  |
  |                  |      |   DETECTED->RECORDING  |    | updates icon    |
  +------------------+      |   RECORDING->TRANSCRIBE|    |                 |
                            |   TRANSCRIBING->TYPING |    | command_queue   |
                            | Save .wav, transcribe, |<---| sends user cmds |
                            | type text              |    +-----------------+
                            +------------------------+

Linux uses the legacy synchronous loop (no menu bar, no threads).
"""

import os, sys, signal, time, threading, queue
from pathlib import Path

from .config import Config
from .server import WhisperServer
from .state import State, StateMachine
from .utils import log, tlog, setup_gpu_environment, is_macos


class WhisperVoiceTyping:
    def __init__(self):
        self.config = Config()
        self.server = WhisperServer(self.config)
        self.state_machine = StateMachine()
        self.running = False
        self.pid_file = Path("/tmp/whisper_voice_typing.pid")

        # inter-thread communication
        self._ui_queue: queue.Queue = queue.Queue()
        self._command_queue: queue.Queue = queue.Queue()

    def _check_single_instance(self) -> None:
        if self.pid_file.exists():
            try:
                pid = int(self.pid_file.read_text().strip())
                try:
                    os.kill(pid, 0)
                    tlog.error(f"Already running (PID {pid}). Kill it: kill {pid}")
                    tlog.footer()
                    sys.exit(1)
                except OSError:
                    self.pid_file.unlink()
            except Exception:
                self.pid_file.unlink()
        self.pid_file.write_text(str(os.getpid()))

    def _cleanup(self, signum=None, frame=None) -> None:
        if not self.running: return
        self.running = False
        print()
        tlog.info("Exiting whisper-typer")
        tlog.footer()
        self.server.stop()
        self.pid_file.unlink(missing_ok=True)
        time.sleep(0.2)

    def run(self) -> None:
        """Entry point. Detects platform and runs appropriate pipeline."""
        if is_macos() and self._can_use_new_pipeline():
            self._run_macos()
        else:
            self._run_legacy()

    def _can_use_new_pipeline(self) -> bool:
        """Check if all macOS new pipeline dependencies are available."""
        try:
            import sounddevice  # noqa: F401
            import rumps  # noqa: F401
            return True
        except ImportError:
            tlog.warn("Menu bar dependencies not installed, using legacy mode. Install with: pip install whisper-typer[macos]")
            return False

    # --- macOS new pipeline ---

    def _run_macos(self) -> None:
        """Run the 3-thread macOS pipeline with menu bar."""
        from .audio import AudioPipeline
        from .vad import VAD
        from .menubar import WhisperMenuBar, StateUpdate, TranscriptionResult
        from .typer import type_text

        self.config.validate(tlog, use_new_pipeline=True)
        self._check_single_instance()
        signal.signal(signal.SIGINT, self._cleanup_macos)
        signal.signal(signal.SIGTERM, self._cleanup_macos)
        setup_gpu_environment(self.config)

        self._audio = AudioPipeline(self.config)
        self._audio.setup_temp_dir()
        self._vad = VAD(threshold=self.config.vad_threshold)
        self._type_text = type_text

        # state machine listener pushes updates to UI queue
        self.state_machine.on_transition(
            lambda old, new: self._ui_queue.put(StateUpdate(new))
        )

        # start the menu bar (this will block on main thread)
        self._menubar = WhisperMenuBar(self.config, self._ui_queue, self._command_queue)

        # start processing thread
        self.running = True
        self._processing_thread = threading.Thread(
            target=self._processing_loop, daemon=True, name="processing"
        )
        self._processing_thread.start()

        tlog.info("whisper-typer activated (menu bar mode)")
        tlog.info(f"Threads: {self.config.thread_count}")
        if self.config.headphone_mic and self.config.headphone_mic != "default":
            tlog.info(f"Mic: {self.config.headphone_mic}")

        # auto-start listening
        self._command_queue.put("start")

        # run menu bar on main thread (blocks until quit)
        self._menubar.run()

        # cleanup after menu bar exits
        self.running = False
        self._audio.stop()
        self._audio.cleanup_temp_dir()
        self.server.stop()
        self.pid_file.unlink(missing_ok=True)

    def _cleanup_macos(self, signum=None, frame=None) -> None:
        self.running = False
        self._command_queue.put("quit")

    def _processing_loop(self) -> None:
        """Processing thread: VAD + state management + transcription.

        Reads frames from the frame queue (each frame exactly once),
        runs VAD, and drives state transitions.
        """
        from .menubar import StateUpdate, TranscriptionResult

        silence_frames = 0
        speech_frames = 0
        frame_duration_ms = 100  # each frame is 100ms
        confirmation_frames = self.config.vad_confirmation_ms // frame_duration_ms
        silence_end_frames = self.config.vad_silence_ms // frame_duration_ms
        last_duration_s = -1  # for throttling duration UI updates to 1/sec

        while self.running:
            try:
                # check for commands from menu bar
                self._process_commands()

                state = self.state_machine.state

                if state in (State.IDLE, State.PAUSED, State.ERROR):
                    time.sleep(0.1)
                    continue

                if not self._audio.is_active():
                    # mic may have disconnected - try restarting
                    if state in (State.LISTENING, State.DETECTED, State.RECORDING):
                        tlog.warn("Audio stream inactive, attempting restart...")
                        if self._audio.restart_stream():
                            continue
                        self.state_machine.transition(State.ERROR)
                        self._ui_queue.put(StateUpdate(State.ERROR, detail="Mic disconnected"))
                    time.sleep(0.1)
                    continue

                # block until next frame arrives (each frame processed exactly once)
                frame = self._audio.next_frame(timeout=0.2)
                if frame is None:
                    continue

                is_speech = self._vad.is_speech(frame, self.config.sample_rate)

                # --- state transitions based on VAD ---

                if state == State.LISTENING:
                    if is_speech:
                        speech_frames += 1
                        silence_frames = 0
                        if speech_frames >= confirmation_frames:
                            # confirmed speech after 300ms - begin recording
                            self.state_machine.transition(State.DETECTED)
                            self._audio.begin_recording()
                            self._audio.accumulate(frame)
                            self.state_machine.transition(State.RECORDING)
                            self._ui_queue.put(StateUpdate(State.RECORDING, duration=0.0))
                            speech_frames = 0
                    else:
                        speech_frames = 0

                elif state == State.RECORDING:
                    self._audio.accumulate(frame)
                    duration = self._audio.recording_duration()

                    if is_speech:
                        silence_frames = 0
                    else:
                        silence_frames += 1

                    # throttle duration counter to 1 update per second
                    dur_s = int(duration)
                    if dur_s != last_duration_s:
                        last_duration_s = dur_s
                        self._ui_queue.put(StateUpdate(State.RECORDING, duration=duration))

                    # end recording on silence or max duration
                    if silence_frames >= silence_end_frames or duration >= self.config.max_recording_duration:
                        self._do_transcribe()
                        silence_frames = 0
                        speech_frames = 0
                        last_duration_s = -1

                elif state == State.TRANSCRIBING:
                    # wait for transcription to complete (handled in _do_transcribe)
                    time.sleep(0.05)

                elif state == State.TYPING:
                    # brief pause then back to listening
                    time.sleep(0.5)
                    self.state_machine.transition(State.LISTENING)
                    self._ui_queue.put(StateUpdate(State.LISTENING))
                    self._vad.reset()
                    speech_frames = 0
                    silence_frames = 0
                    last_duration_s = -1

            except Exception as e:
                log.exception(f"Processing loop error: {e}")
                try:
                    self.state_machine.transition(State.ERROR)
                    self._ui_queue.put(StateUpdate(State.ERROR, detail=str(e)[:100]))
                except ValueError:
                    pass
                time.sleep(2)
                try:
                    self.state_machine.transition(State.IDLE)
                    self._command_queue.put("start")
                except ValueError:
                    self.state_machine.reset()

    def _process_commands(self) -> None:
        """Process commands from the menu bar."""
        from .menubar import StateUpdate

        while True:
            try:
                cmd = self._command_queue.get_nowait()
            except queue.Empty:
                break

            if cmd == "start":
                try:
                    if self.state_machine.state in (State.IDLE, State.ERROR):
                        self.state_machine.transition(State.LISTENING)

                    if not self._audio.is_active():
                        self._audio.start()

                    if not self.server.is_running():
                        self.server.start()

                    self._ui_queue.put(StateUpdate(State.LISTENING))
                    tlog.info("Listening...")
                except Exception as e:
                    log.error(f"Failed to start: {e}")
                    self._ui_queue.put(StateUpdate(State.ERROR, detail=str(e)[:100]))

            elif cmd == "stop":
                self._audio.stop()
                try:
                    self.state_machine.transition(State.IDLE)
                except ValueError:
                    self.state_machine.reset()
                self._ui_queue.put(StateUpdate(State.IDLE))
                tlog.info("Stopped")

            elif cmd == "pause":
                self._audio.stop()
                try:
                    self.state_machine.transition(State.PAUSED)
                except ValueError:
                    pass
                self._ui_queue.put(StateUpdate(State.PAUSED))
                tlog.info("Paused")

            elif cmd == "resume":
                try:
                    self.state_machine.transition(State.LISTENING)
                    self._audio.start()
                    self._ui_queue.put(StateUpdate(State.LISTENING))
                    tlog.info("Resumed")
                except Exception as e:
                    log.error(f"Failed to resume: {e}")
                    self._ui_queue.put(StateUpdate(State.ERROR, detail=str(e)[:100]))

            elif cmd == "force_transcribe":
                if self.state_machine.state in (State.DETECTED, State.RECORDING):
                    tlog.info("Force transcribe triggered")
                    self._do_transcribe()

            elif cmd == "quit":
                self.running = False
                self._audio.stop()
                return

    def _do_transcribe(self) -> None:
        """Save the current recording and transcribe it."""
        from .menubar import StateUpdate, TranscriptionResult

        self.state_machine.transition(State.TRANSCRIBING)
        self._ui_queue.put(StateUpdate(State.TRANSCRIBING))

        audio_file = self._audio.save_recording()
        if audio_file is None:
            tlog.warn("No audio to transcribe")
            self.state_machine.transition(State.LISTENING)
            self._ui_queue.put(StateUpdate(State.LISTENING))
            self._vad.reset()
            return

        try:
            text = self.server.transcribe(audio_file)
            audio_file.unlink(missing_ok=True)

            if text:
                self.state_machine.transition(State.TYPING)
                self._ui_queue.put(StateUpdate(State.TYPING))
                self._ui_queue.put(TranscriptionResult(text))

                if self._type_text(text):
                    tlog.info(f"Typed: {text[:60]}{'...' if len(text) > 60 else ''}")
                else:
                    tlog.error("Failed to type text")
            else:
                self.state_machine.transition(State.LISTENING)
                self._ui_queue.put(StateUpdate(State.LISTENING))
                self._vad.reset()
        except Exception as e:
            log.exception(f"Transcription error: {e}")
            try:
                self.state_machine.transition(State.LISTENING)
                self._ui_queue.put(StateUpdate(State.LISTENING))
            except ValueError:
                pass
            self._vad.reset()

    # --- Legacy pipeline (Linux / fallback) ---

    def _run_legacy(self) -> None:
        """Run the original synchronous loop (Linux or missing deps)."""
        from .audio import LegacyAudioProcessor

        self.config.validate(tlog, use_new_pipeline=False)
        self._check_single_instance()
        signal.signal(signal.SIGINT, self._cleanup)
        signal.signal(signal.SIGTERM, self._cleanup)
        setup_gpu_environment(self.config)

        processor = LegacyAudioProcessor(self.config, self.server)
        processor.setup_temp_dir()

        if not self.server.is_running(): self.server.start()

        tlog.info("whisper-typer activated (legacy mode)")
        tlog.info(f"Threads: {self.config.thread_count}")
        if self.config.headphone_mic and self.config.headphone_mic != "default":
            tlog.info(f"Mic: {self.config.headphone_mic}")
        tlog.info("Listening... (Ctrl+C to exit)")

        self.running = True
        errors = 0
        while self.running:
            try:
                tlog.status("Listening...")
                audio_file = processor.record_audio()
                if audio_file:
                    tlog.status("Processing...")
                    if processor.process_audio(audio_file):
                        errors = 0
                        tlog.status("Done, waiting...")
                        time.sleep(self.config.post_processing_delay)
                    audio_file.unlink(missing_ok=True)
                else:
                    time.sleep(self.config.no_audio_delay)
            except KeyboardInterrupt:
                break
            except Exception as e:
                errors += 1
                log.exception(f"Main loop error: {e}")
                if errors >= 10:
                    tlog.error("Too many errors, restarting server...")
                    self.server.stop()
                    time.sleep(2)
                    self.server.start()
                    errors = 0
                else:
                    time.sleep(1)

        self._cleanup()
        processor.cleanup_temp_dir()
