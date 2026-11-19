"""Microphone capture at 16 kHz mono, delivered as frames on an asyncio queue."""

from __future__ import annotations

import asyncio
import logging

import numpy as np

from vcui_engine.endpointer import SAMPLE_RATE

log = logging.getLogger("vcui_engine.audio")


class MicStream:
    def __init__(self, frames: asyncio.Queue[np.ndarray], loop: asyncio.AbstractEventLoop, frame_ms: int = 32,
                 device: str | int | None = None):
        self._frames = frames
        self._loop = loop
        self._blocksize = SAMPLE_RATE * frame_ms // 1000
        self._device = device
        self._stream = None

    @property
    def running(self) -> bool:
        return self._stream is not None

    def _callback(self, indata, frame_count, time_info, status) -> None:  # runs on the audio thread
        if status:
            log.debug("audio status: %s", status)
        frame = indata[:, 0].copy()
        self._loop.call_soon_threadsafe(self._put, frame)

    def _put(self, frame: np.ndarray) -> None:
        if self._frames.full():
            self._frames.get_nowait()  # drop the oldest frame rather than fall behind
        self._frames.put_nowait(frame)

    def start(self) -> None:
        if self._stream is not None:
            return
        import sounddevice as sd

        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=self._blocksize,
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()
        log.info("microphone started")

    def stop(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None
            log.info("microphone stopped")
