"""Optional wake-word detection with openWakeWord.

Install with the `wake` extra. openWakeWord ships English pretrained models;
the default is "hey jarvis". A Swedish wake word needs a custom model trained
with openWakeWord's tools, passed as a path to an .onnx file.
"""

from __future__ import annotations

import logging
from typing import Protocol

import numpy as np

log = logging.getLogger("vcui_engine.wake")
DEFAULT_WAKE_MODEL = "hey_jarvis"
# openWakeWord scores 80 ms chunks of 16 kHz int16 audio.
CHUNK_SAMPLES = 1280


class WakeDetector(Protocol):
    name: str

    def feed(self, frame: np.ndarray) -> bool: ...

    def reset(self) -> None: ...


class OpenWakeWordDetector:
    def __init__(self, model: str = DEFAULT_WAKE_MODEL, threshold: float = 0.5):
        import openwakeword
        from openwakeword.model import Model

        if not model.endswith((".onnx", ".tflite")):
            openwakeword.utils.download_models([model])
        self._model = Model(wakeword_models=[model], inference_framework="onnx")
        self.name = model
        self._threshold = threshold
        self._buffer = np.zeros(0, dtype=np.int16)

    def reset(self) -> None:
        self._buffer = np.zeros(0, dtype=np.int16)
        self._model.reset()

    def feed(self, frame: np.ndarray) -> bool:
        pcm = (np.clip(frame, -1.0, 1.0) * 32767).astype(np.int16)
        self._buffer = np.concatenate([self._buffer, pcm])
        heard = False
        while self._buffer.size >= CHUNK_SAMPLES:
            chunk, self._buffer = self._buffer[:CHUNK_SAMPLES], self._buffer[CHUNK_SAMPLES:]
            scores = self._model.predict(chunk)
            if max(scores.values(), default=0.0) >= self._threshold:
                heard = True
        if heard:
            self.reset()
        return heard


def load_wake_detector(model: str = DEFAULT_WAKE_MODEL) -> WakeDetector | None:
    try:
        return OpenWakeWordDetector(model)
    except ImportError:
        log.info("openwakeword is not installed; wake-word mode is off")
    except Exception:  # noqa: BLE001 - wake word is optional
        log.exception("Could not load wake-word model %s", model)
    return None
