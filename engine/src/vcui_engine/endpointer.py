"""Split a stream of microphone frames into utterances.

The endpointer is a small state machine over 16 kHz mono float32 frames. It
tracks the background level, decides when speech starts and ends, and returns
each finished utterance with a little audio from before it started, so the
first syllable is not cut off. It has no I/O, so it is tested directly.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

SAMPLE_RATE = 16_000


@dataclass
class EndpointerConfig:
    frame_ms: int = 32
    # Speech must be this much louder than the background level.
    speech_ratio: float = 3.0
    # Never treat anything quieter than this RMS as speech, however quiet the room.
    min_speech_rms: float = 0.012
    start_ms: int = 96
    end_silence_ms: int = 700
    pre_roll_ms: int = 320
    min_utterance_ms: int = 300
    max_utterance_ms: int = 15_000
    # How fast the background estimate follows the room while nobody speaks.
    noise_adapt: float = 0.05
    # After a reset, the first frames set the background level. The quietest of
    # them count, so a word spoken right away does not raise it much.
    calibrate_ms: int = 256

    def frames(self, ms: int) -> int:
        return max(1, round(ms / self.frame_ms))


@dataclass
class EndpointerEvent:
    kind: str  # "speech_start" or "utterance"
    audio: np.ndarray | None = None


@dataclass
class Endpointer:
    config: EndpointerConfig = field(default_factory=EndpointerConfig)
    noise_rms: float = 0.004

    def __post_init__(self) -> None:
        self._pre_roll: deque[np.ndarray] = deque(maxlen=self.config.frames(self.config.pre_roll_ms))
        self._candidate: list[np.ndarray] = []
        self._speech: list[np.ndarray] = []
        self._in_speech = False
        self._silent_frames = 0
        self._calibration: list[float] = []
        self._speech_rms: list[float] = []

    @property
    def in_speech(self) -> bool:
        return self._in_speech

    def reset(self) -> None:
        self._pre_roll.clear()
        self._candidate = []
        self._speech = []
        self._in_speech = False
        self._silent_frames = 0
        self._calibration = []
        self._speech_rms = []

    def threshold(self) -> float:
        return max(self.noise_rms * self.config.speech_ratio, self.config.min_speech_rms)

    def feed(self, frame: np.ndarray) -> list[EndpointerEvent]:
        """Feed one frame and return what happened, if anything."""
        rms = float(np.sqrt(np.mean(np.square(frame, dtype=np.float64)))) if frame.size else 0.0
        config = self.config
        events: list[EndpointerEvent] = []
        if len(self._calibration) < config.frames(config.calibrate_ms):
            self._calibration.append(rms)
            self._pre_roll.append(frame)
            if len(self._calibration) == config.frames(config.calibrate_ms):
                self.noise_rms = float(np.percentile(self._calibration, 20))
            return events
        loud = rms >= self.threshold()

        if not self._in_speech:
            if loud:
                self._candidate.append(frame)
                if len(self._candidate) >= config.frames(config.start_ms):
                    self._in_speech = True
                    self._speech = [*self._pre_roll, *self._candidate]
                    self._speech_rms = []
                    self._candidate = []
                    self._silent_frames = 0
                    events.append(EndpointerEvent("speech_start"))
            else:
                # A short click is background, not speech.
                for held in self._candidate:
                    self._pre_roll.append(held)
                self._candidate = []
                self._pre_roll.append(frame)
                self.noise_rms += config.noise_adapt * (rms - self.noise_rms)
            return events

        self._speech.append(frame)
        self._speech_rms.append(rms)
        self._silent_frames = 0 if loud else self._silent_frames + 1
        too_long = len(self._speech) >= config.frames(config.max_utterance_ms)
        if self._silent_frames >= config.frames(config.end_silence_ms) or too_long:
            audio = np.concatenate(self._speech)
            if too_long:
                # Nobody talks for that long without a pause: the room got
                # louder. Learn the new level so the next frames are not speech.
                self.noise_rms = max(self.noise_rms, float(np.percentile(self._speech_rms, 20)) / config.speech_ratio * 1.5)
            else:
                # Drop the trailing silence that ended the utterance.
                audio = audio[: max(0, audio.size - self._silent_frames * frame.size)]
            self._in_speech = False
            self._speech = []
            self._silent_frames = 0
            self._pre_roll.clear()
            if audio.size >= SAMPLE_RATE * config.min_utterance_ms / 1000:
                events.append(EndpointerEvent("utterance", audio))
        return events
