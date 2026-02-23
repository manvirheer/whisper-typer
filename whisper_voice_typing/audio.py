import time, tempfile, shutil, subprocess
from pathlib import Path
import requests

from .utils import log, tlog, is_macos

class AudioProcessor:
    def __init__(self, config, server):
        self.config, self.server = config, server
        self.temp_dir: Path | None = None
        self._rec_fails = 0
        self._transcribe_fails = 0

    def setup_temp_dir(self) -> None:
        base = Path("/dev/shm") if not is_macos() and Path("/dev/shm").exists() else Path("/tmp")
        self.temp_dir = Path(tempfile.mkdtemp(prefix="whisper_voice.", dir=base))

    def cleanup_temp_dir(self) -> None:
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _cleanup_stale(self) -> None:
        if not self.temp_dir or not self.temp_dir.exists(): return
        now = time.time()
        for f in self.temp_dir.glob("*.wav"):
            try:
                if now - f.stat().st_mtime > 60: f.unlink()
            except OSError: pass

    def record_audio(self) -> Path | None:
        self._cleanup_stale()
        audio_file = self.temp_dir / f"{time.time_ns()}.wav"
        timeout = self.config.max_recording_duration + 10
        return self._record_macos(audio_file, timeout) if is_macos() else self._record_linux(audio_file, timeout)

    def _record_macos(self, audio_file: Path, timeout: int) -> Path | None:
        # sox coreaudio has a buffer overrun bug — ffmpeg captures, sox does silence detection
        device = f":{self.config.headphone_mic}" if (self.config.headphone_mic and self.config.headphone_mic != "default") else ":default"
        ffmpeg_cmd = ["ffmpeg", "-nostdin", "-f", "avfoundation", "-i", device,
                      "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le", "-flush_packets", "1", "-f", "s16le", "-loglevel", "error", "pipe:1"]
        # pad 0.3 prepends 300ms silence so whisper sees full word onset
        sox_cmd = ["sox", "-q", "-t", "raw", "-r", "16000", "-e", "signed-integer", "-b", "16", "-c", "1", "-", str(audio_file),
                   "silence", "1", str(self.config.silence_start_duration), self.config.silence_start_threshold,
                   "1", str(self.config.silence_end_duration), self.config.silence_end_threshold,
                   "trim", "0", str(self.config.max_recording_duration),
                   "pad", "0.3", "0.3"]

        ffmpeg_proc, sox_proc = None, None
        try:
            ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            sox_proc = subprocess.Popen(sox_cmd, stdin=ffmpeg_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            ffmpeg_proc.stdout.close()  # allow sigpipe
            sox_proc.wait(timeout=timeout)

            ffmpeg_proc.terminate()
            try: ffmpeg_proc.wait(timeout=2)
            except subprocess.TimeoutExpired: ffmpeg_proc.kill(); ffmpeg_proc.wait()

            if sox_proc.returncode != 0:
                self._rec_fails += 1
                if self._rec_fails >= 3: tlog.warn(f"Recording failed {self._rec_fails}x in a row")
                audio_file.unlink(missing_ok=True)
                return None
            return self._check_audio(audio_file)

        except subprocess.TimeoutExpired:
            self._rec_fails += 1
            if sox_proc: sox_proc.kill(); sox_proc.wait()
            if ffmpeg_proc: ffmpeg_proc.kill(); ffmpeg_proc.wait()
            if self._rec_fails >= 3: tlog.warn(f"No audio for {self._rec_fails} cycles — mic working?")
            audio_file.unlink(missing_ok=True)
            return None
        except Exception as e:
            self._rec_fails += 1
            log.exception(f"Recording error: {e}")
            if sox_proc and sox_proc.poll() is None: sox_proc.kill()
            if ffmpeg_proc and ffmpeg_proc.poll() is None: ffmpeg_proc.kill()
            audio_file.unlink(missing_ok=True)
            return None

    def _record_linux(self, audio_file: Path, timeout: int) -> Path | None:
        cmd = ["rec"]
        if self.config.headphone_mic and self.config.headphone_mic != "default":
            cmd.extend(["-t", "pulseaudio", self.config.headphone_mic])
        cmd.extend(["-q", str(audio_file), "silence",
                    "1", str(self.config.silence_start_duration), self.config.silence_start_threshold,
                    "1", str(self.config.silence_end_duration), self.config.silence_end_threshold,
                    "trim", "0", str(self.config.max_recording_duration),
                    "pad", "0.3", "0.3"])
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=timeout)
            if result.returncode != 0:
                self._rec_fails += 1
                if self._rec_fails >= 3:
                    stderr = result.stderr.decode(errors="replace").strip()
                    tlog.warn(f"Recording failed {self._rec_fails}x: {stderr[:120]}")
                audio_file.unlink(missing_ok=True)
                return None
            return self._check_audio(audio_file)
        except subprocess.TimeoutExpired:
            self._rec_fails += 1
            if self._rec_fails >= 3: tlog.warn(f"No audio for {self._rec_fails} cycles — mic working?")
            audio_file.unlink(missing_ok=True)
            return None
        except Exception as e:
            self._rec_fails += 1
            log.exception(f"Recording error: {e}")
            audio_file.unlink(missing_ok=True)
            return None

    def _check_audio(self, audio_file: Path) -> Path | None:
        if not audio_file.exists(): return None
        size = audio_file.stat().st_size
        if size >= self.config.min_file_size:
            self._rec_fails = 0
            tlog.info(f"Recorded {size} bytes")
            return audio_file
        tlog.warn(f"Too small ({size}B < {self.config.min_file_size}B), discarding")
        audio_file.unlink()
        return None

    def transcribe_via_server(self, audio_file: Path) -> str | None:
        try:
            with open(audio_file, 'rb') as f:
                resp = requests.post(f"http://{self.config.server_host}:{self.config.server_port}/inference", files={'file': f}, timeout=10)
            if resp.status_code == 200:
                text = resp.json().get('text', '').strip()
                if text and text != "[BLANK_AUDIO]":
                    self._transcribe_fails = 0
                    return text
                tlog.warn("Server returned blank audio")
                return None
            self._transcribe_fails += 1
            tlog.warn(f"Server HTTP {resp.status_code}")
            return None
        except Exception:
            self._transcribe_fails += 1
            return None

    def transcribe_direct(self, audio_file: Path) -> str | None:
        cmd = [str(self.config.whisper_executable), "-m", str(self.config.whisper_model),
               "-f", str(audio_file), "-t", str(self.config.thread_count), "--no-timestamps", "--no-prints", "--flash-attn"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                text = result.stdout.strip()
                if text and text != "[BLANK_AUDIO]": return text
                tlog.warn("Whisper returned blank audio")
                return None
            tlog.warn(f"Whisper exit code {result.returncode}")
            return None
        except Exception as e:
            log.exception(f"Direct transcription error: {e}")
            return None

    def process_audio(self, audio_file: Path) -> bool:
        start = time.time()

        if self._transcribe_fails >= 3:
            tlog.warn("Multiple transcription failures, restarting server...")
            self.server.stop()
            self._transcribe_fails = 0
            time.sleep(1)

        text, mode = None, "server"
        if not self.server.is_running():
            tlog.info("Server not running, starting...")
            if not self.server.start():
                tlog.warn("Server failed, using direct mode")
                mode = "direct"

        if mode == "server":
            text = self.transcribe_via_server(audio_file)
            if text is None:
                tlog.warn("Server failed, falling back to direct mode")
                mode = "direct"
                text = self.transcribe_direct(audio_file)
        else:
            text = self.transcribe_direct(audio_file)

        if text:
            tlog.success(f"Transcribed in {int((time.time() - start) * 1000)}ms via {mode}")
            return self._type_text(text)
        return False

    def _type_text(self, text: str) -> bool:
        try:
            if is_macos():
                # save clipboard → paste → restore
                saved = None
                try:
                    r = subprocess.run(["pbpaste"], capture_output=True, timeout=2)
                    if r.returncode == 0: saved = r.stdout
                except Exception: pass

                subprocess.run(["pbcopy"], input=text.encode(), check=True, timeout=5)
                result = subprocess.run(
                    ["osascript", "-e", 'tell application "System Events" to keystroke "v" using command down'],
                    capture_output=True, text=True, timeout=10)

                if saved is not None:
                    time.sleep(0.1)
                    try: subprocess.run(["pbcopy"], input=saved, timeout=2)
                    except Exception: pass

                if result.returncode != 0:
                    stderr = result.stderr.strip()
                    if "not allowed" in stderr or "1002" in stderr:
                        tlog.error("Accessibility permission denied — System Settings > Privacy & Security > Accessibility")
                    else:
                        tlog.error(f"osascript failed: {stderr}")
                    return False
            else:
                subprocess.run(["xdotool", "type", "--delay", "1", "--clearmodifiers", "--", text], check=True, timeout=10)
            return True
        except Exception as e:
            log.exception(f"Failed to type: {e}")
            return False
