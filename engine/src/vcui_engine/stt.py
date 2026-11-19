"""Swedish speech recognition with KB-Whisper through faster-whisper.

Loading follows referat's transcription server: use the cached model without
asking the Hugging Face Hub, fall back from CUDA to CPU, and run the encoder
once on CUDA so a broken GPU setup fails at start instead of on the first command.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import TYPE_CHECKING, Protocol

import numpy as np

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

DEFAULT_MODEL = "KBLab/kb-whisper-small"
log = logging.getLogger("vcui_engine.stt")

# Words the app uses, so recognition prefers them over sound-alikes.
DEFAULT_PROMPT = "Att göra-lista. Lägg till, ta bort, bocka av, markera som klar, viktig, inköp, jobb, hem, inkorg."


class Transcriber(Protocol):
    device: str

    def transcribe(self, audio: np.ndarray) -> str: ...


def resolve_model_path(model_name: str) -> str:
    if os.path.isdir(model_name):
        return model_name
    from faster_whisper.utils import download_model
    from huggingface_hub.errors import LocalEntryNotFoundError

    try:
        return download_model(model_name, local_files_only=True)
    except LocalEntryNotFoundError:
        log.info("Model %s is not cached yet; downloading it", model_name)
        return download_model(model_name)


def _load(model_path: str, device: str) -> WhisperModel:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_path, device=device, compute_type="float16" if device == "cuda" else "int8")
    if device == "cuda":
        segments, _ = model.transcribe(
            np.zeros(16_000, dtype=np.float32), language="sv", beam_size=1, without_timestamps=True
        )
        list(segments)
    return model


class WhisperTranscriber:
    def __init__(self, model_name: str = DEFAULT_MODEL, device: str = "auto", prompt: str = DEFAULT_PROMPT):
        path = resolve_model_path(model_name)
        devices = ["cuda", "cpu"] if device == "auto" else [device]
        last_error: Exception | None = None
        for candidate in devices:
            try:
                self._model = _load(path, candidate)
                self.device = candidate
                break
            except Exception as error:  # noqa: BLE001 - try the next device
                last_error = error
                log.warning("Could not load %s on %s: %s", model_name, candidate, error)
        else:
            raise RuntimeError(f"Could not load speech model: {last_error}")
        self._prompt = prompt
        self._lock = threading.Lock()

    def transcribe(self, audio: np.ndarray) -> str:
        with self._lock:
            segments, _ = self._model.transcribe(
                audio.astype(np.float32),
                language="sv",
                # A command is short: greedy decoding on CPU keeps it fast.
                beam_size=1 if self.device == "cpu" else 3,
                vad_filter=False,
                condition_on_previous_text=False,
                without_timestamps=True,
                initial_prompt=self._prompt,
            )
            return " ".join(segment.text.strip() for segment in segments).strip()
