"""Decide what the microphone is for right now, and turn speech into transcripts.

Two modes:

- `toggle`: a press (button or global shortcut) opens the microphone and keeps
  it open. Every pause ends an utterance, which is transcribed and sent as a
  command, until the next press closes it.
- `wake`: the microphone stays on and listens only for the wake word. After it,
  utterances are taken as commands until `wake_session_ms` passes with no speech.

The listener owns no microphone and no model: it gets frames from a queue and
calls the transcriber and callbacks it was given, so it runs in tests as is.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import time
from typing import Awaitable, Callable

import numpy as np

from vcui_engine.endpointer import Endpointer, EndpointerConfig
from vcui_engine.stt import Transcriber
from vcui_engine.wakeword import WakeDetector

log = logging.getLogger("vcui_engine.listener")

Emit = Callable[[dict], Awaitable[None]]
MicControl = Callable[[bool], None]


class Listener:
    def __init__(
        self,
        frames: asyncio.Queue[np.ndarray],
        emit: Emit,
        mic: MicControl,
        transcriber: Transcriber | None = None,
        wake: WakeDetector | None = None,
        endpointer_config: EndpointerConfig | None = None,
        wake_session_ms: int = 8000,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._frames = frames
        self._emit = emit
        self._mic = mic
        self.transcriber = transcriber
        self.wake = wake
        self._endpointer = Endpointer(endpointer_config or EndpointerConfig())
        self._wake_session_s = wake_session_ms / 1000
        self._clock = clock
        self.mode = "toggle"
        self.open = False  # toggle mode: microphone open for commands
        self._awake_until = 0.0  # wake mode: commands accepted until this time
        self._phase = ""
        self._ids = itertools.count(1)
        self._pending: asyncio.Queue[np.ndarray] = asyncio.Queue()
        self._frame_count = 0

    # ----- state the UI sees -----

    def phase(self) -> str:
        if self.mode == "toggle" and not self.open:
            return "off"
        if self.mode == "wake" and not self._awake():
            return "wake"
        if self._endpointer.in_speech:
            return "speech"
        return "listening"

    def _awake(self) -> bool:
        return self._clock() < self._awake_until

    def state(self) -> dict:
        return {
            "type": "state",
            "mode": self.mode,
            "open": self.open,
            "phase": self.phase(),
            "wake_available": self.wake is not None,
            "wake_word": getattr(self.wake, "name", None),
        }

    async def _publish(self, force: bool = False) -> None:
        phase = self.phase()
        if force or phase != self._phase:
            self._phase = phase
            await self._emit(self.state())

    def _sync_mic(self) -> None:
        self._mic(self.mode == "wake" or self.open)

    # ----- commands from the UI -----

    async def set_open(self, value: bool) -> None:
        if self.mode != "toggle":
            # A press in wake mode starts a command window right away.
            self._awake_until = self._clock() + self._wake_session_s if value else 0.0
        else:
            self.open = value
        self._endpointer.reset()
        self._sync_mic()
        await self._publish(force=True)

    async def toggle(self) -> None:
        if self.mode == "toggle":
            await self.set_open(not self.open)
        else:
            await self.set_open(not self._awake())

    async def set_mode(self, mode: str) -> None:
        if mode not in ("toggle", "wake"):
            raise ValueError(f"unknown mode {mode!r}")
        if mode == "wake" and self.wake is None:
            await self._emit({"type": "error", "message": "Väckningsord är inte installerat (pip install vcui-engine[wake])."})
            return
        self.mode = mode
        self.open = False
        self._awake_until = 0.0
        self._endpointer.reset()
        if self.wake is not None:
            self.wake.reset()
        self._sync_mic()
        await self._publish(force=True)

    # ----- the audio loop -----

    async def run(self) -> None:
        worker = asyncio.create_task(self._transcribe_worker())
        try:
            while True:
                frame = await self._frames.get()
                await self.process(frame)
        finally:
            worker.cancel()

    async def process(self, frame: np.ndarray) -> None:
        self._frame_count += 1
        if self._frame_count % 3 == 0:
            rms = float(np.sqrt(np.mean(np.square(frame)))) if frame.size else 0.0
            await self._emit({"type": "level", "rms": round(min(1.0, rms * 8), 3)})

        if self.mode == "wake" and not self._awake():
            if self.wake is not None and self.wake.feed(frame):
                self._awake_until = self._clock() + self._wake_session_s
                self._endpointer.reset()
                await self._emit({"type": "wake"})
            await self._publish()
            return
        if self.mode == "toggle" and not self.open:
            return

        for event in self._endpointer.feed(frame):
            if event.kind == "utterance" and event.audio is not None:
                self._pending.put_nowait(event.audio)
        if self.mode == "wake" and self._endpointer.in_speech:
            # Speaking keeps the command window open.
            self._awake_until = self._clock() + self._wake_session_s
        await self._publish()

    async def _transcribe_worker(self) -> None:
        while True:
            audio = await self._pending.get()
            await self.handle_utterance(audio)

    async def handle_utterance(self, audio: np.ndarray) -> None:
        if self.transcriber is None:
            await self._emit({"type": "error", "message": "Taligenkänningen laddas fortfarande."})
            return
        utterance_id = next(self._ids)
        await self._emit({"type": "transcribing", "id": utterance_id})
        started = time.perf_counter()
        try:
            text = await asyncio.to_thread(self.transcriber.transcribe, audio)
        except Exception as error:  # noqa: BLE001 - report and keep listening
            log.exception("transcription failed")
            await self._emit({"type": "error", "message": f"Taligenkänningen misslyckades: {error}"})
            return
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        log.info("transcribed %.1f s of audio in %d ms: %r", audio.size / 16000, elapsed_ms, text)
        await self._emit({"type": "transcript", "id": utterance_id, "text": text, "stt_ms": elapsed_ms,
                          "audio_ms": round(audio.size / 16)})
