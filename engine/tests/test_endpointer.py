import numpy as np

from vcui_engine.endpointer import SAMPLE_RATE, Endpointer, EndpointerConfig

FRAME = SAMPLE_RATE * 32 // 1000


def tone(ms: int, level: float = 0.2) -> list[np.ndarray]:
    count = ms // 32
    t = np.arange(FRAME) / SAMPLE_RATE
    frame = (level * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    return [frame.copy() for _ in range(count)]


def silence(ms: int, level: float = 0.001) -> list[np.ndarray]:
    rng = np.random.default_rng(1)
    return [(rng.standard_normal(FRAME) * level).astype(np.float32) for _ in range(ms // 32)]


def run(endpointer: Endpointer, frames: list[np.ndarray]):
    events = []
    for frame in frames:
        events.extend(endpointer.feed(frame))
    return events


def test_one_utterance_between_silences():
    ep = Endpointer()
    events = run(ep, silence(1000) + tone(800) + silence(1000))
    kinds = [e.kind for e in events]
    assert kinds == ["speech_start", "utterance"]
    audio = events[1].audio
    # The speech plus up to the pre-roll, without the silence that ended it.
    seconds = audio.size / SAMPLE_RATE
    assert 0.8 <= seconds <= 0.8 + 0.32 + 0.05


def test_short_click_is_not_speech():
    ep = Endpointer()
    events = run(ep, silence(500) + tone(64) + silence(1000))
    assert events == []


def test_two_utterances_with_a_pause():
    ep = Endpointer()
    events = run(ep, silence(500) + tone(600) + silence(900) + tone(600) + silence(900))
    assert [e.kind for e in events].count("utterance") == 2


def test_short_pause_does_not_split():
    ep = Endpointer()
    events = run(ep, silence(500) + tone(500) + silence(300) + tone(500) + silence(900))
    assert [e.kind for e in events].count("utterance") == 1


def test_sound_without_pause_is_cut_once_then_learned_as_background():
    ep = Endpointer(EndpointerConfig(max_utterance_ms=2000))
    events = run(ep, silence(300) + tone(6000))
    utterances = [e for e in events if e.kind == "utterance"]
    assert len(utterances) == 1
    assert utterances[0].audio.size <= SAMPLE_RATE * 2.1


def test_background_learned_from_a_loud_start_still_lets_speech_through():
    ep = Endpointer()
    events = run(ep, silence(1000, level=0.02) + tone(800, level=0.3) + silence(1000, level=0.02))
    assert [e.kind for e in events] == ["speech_start", "utterance"]


def test_noise_floor_follows_a_loud_room():
    ep = Endpointer()
    # Steady fan noise well above the minimum level is learned as background.
    events = run(ep, silence(3000, level=0.02))
    assert events == []
    assert ep.threshold() > 0.04
