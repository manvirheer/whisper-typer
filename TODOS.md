# TODOS

## P1

### Global hotkey to force-transcribe
**What:** Dedicated hotkey (e.g., Cmd+Shift+T) to immediately send current audio buffer to whisper, same as clicking "Transcribe Now" in menu bar.
**Why:** The menu bar click-to-transcribe requires mouse. A hotkey is faster for power users mid-dictation.
**Where to start:** Use PyObjC `NSEvent.addGlobalMonitorForEventsMatchingMask` or `pynput`. Wire to `command_queue.put("force_transcribe")` in `app.py`.
**Effort:** S
**Depends on:** Menu bar pipeline (done)

## P2

### Global hotkey to toggle listening
**What:** Configurable hotkey (e.g., Cmd+Shift+V) to toggle whisper-typer on/off without clicking the menu bar.
**Why:** Faster than clicking menu bar icon. Hands-on-keyboard workflow.
**Where to start:** Same hotkey infrastructure as force-transcribe. Wire to `command_queue.put("start"/"stop")`.
**Effort:** S
**Depends on:** Menu bar pipeline (done)

### Audio level indicator in menu dropdown
**What:** Live audio level meter (e.g., `|||||`) in the menu dropdown when expanded. Shows real-time mic input level.
**Why:** "Is my mic working?" is the #1 debugging question. This answers it instantly.
**Where to start:** Compute RMS from ring buffer frames. Update a `rumps.MenuItem` title on the 100ms timer when the menu is open.
**Effort:** S
**Depends on:** Menu bar pipeline (done)

## P3

### Notification sound on transcription complete
**What:** Play a subtle system sound (e.g., Glass) when text has been typed. Toggleable via menu checkbox or env var.
**Why:** Audio confirmation without looking at menu bar. Useful when dictating while reading a document.
**Where to start:** `NSSound.soundNamed_("Glass").play()` via PyObjC in `_type_text` success path. Add a `WHISPER_SOUND` env var toggle.
**Effort:** S
**Depends on:** Menu bar pipeline (done)
