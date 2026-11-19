"""End-to-end over a real WebSocket: window <-> engine <-> fake agent and fake speech."""

import asyncio
import json

import numpy as np
import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import InvalidStatus

from vcui_engine.agent import CommandResult
from vcui_engine.listener import Listener
from vcui_engine.server import APP_ORIGINS, Engine, make_request_check

TOKEN = "secret-token"


class ScriptedAgent:
    """Calls one tool in the window, then replies with what it got back."""

    async def run(self, text, tools, run_tool):
        ok, result = await run_tool("act", {"steps": [{"ref": "Ny uppgift", "action": "setValue", "args": [text]}]})
        return CommandResult(reply=f"{ok}:{result}", tool_calls=1, stop_reason="end_turn")


class FakeTranscriber:
    device = "cpu"

    def transcribe(self, audio):
        return "lägg till mjölk"


async def start(engine):
    server = await serve(engine.handle, "127.0.0.1", 0, origins=APP_ORIGINS,
                         process_request=make_request_check(TOKEN))
    port = server.sockets[0].getsockname()[1]
    workers = [asyncio.create_task(engine.command_worker()), asyncio.create_task(engine.listener.run())]
    return server, port, workers


async def receive_until(ws, kind):
    while True:
        message = json.loads(await asyncio.wait_for(ws.recv(), 5))
        if message["type"] == kind:
            return message


def make_engine():
    async def emit(message):
        await holder["engine"].emit(message)

    holder = {}
    frames = asyncio.Queue()
    listener = Listener(frames, emit, mic=lambda on: None, transcriber=FakeTranscriber())
    engine = Engine(listener, ScriptedAgent())
    holder["engine"] = engine
    return engine


@pytest.mark.asyncio
async def test_rejects_wrong_token_and_foreign_origin():
    engine = make_engine()
    server, port, workers = await start(engine)
    try:
        with pytest.raises(InvalidStatus):
            async with connect(f"ws://127.0.0.1:{port}/?token=wrong", origin="tauri://localhost"):
                pass
        with pytest.raises(InvalidStatus):
            async with connect(f"ws://127.0.0.1:{port}/?token={TOKEN}", origin="https://evil.example"):
                pass
    finally:
        server.close()
        for w in workers:
            w.cancel()


@pytest.mark.asyncio
async def test_command_round_trip_through_window_tools():
    engine = make_engine()
    server, port, workers = await start(engine)
    try:
        async with connect(f"ws://127.0.0.1:{port}/?token={TOKEN}", origin="tauri://localhost") as ws:
            status = await receive_until(ws, "status")
            assert status["agent"] == "ready"
            await ws.send(json.dumps({"type": "hello", "tools": []}))
            await ws.send(json.dumps({"type": "command", "id": "k1", "text": "Köp mjölk"}))

            call = await receive_until(ws, "tool_call")
            assert call["name"] == "act"
            assert call["input"]["steps"][0]["args"] == ["Köp mjölk"]
            await ws.send(json.dumps({"type": "tool_result", "id": call["id"], "ok": True, "result": "done"}))

            reply = await receive_until(ws, "reply")
            assert reply == {**reply, "id": "k1", "ok": True, "text": "True:done"}
    finally:
        server.close()
        for w in workers:
            w.cancel()


@pytest.mark.asyncio
async def test_toggle_opens_mic_and_speech_becomes_a_transcript():
    engine = make_engine()
    mic_states = []
    engine.listener._mic = mic_states.append
    server, port, workers = await start(engine)
    try:
        async with connect(f"ws://127.0.0.1:{port}/?token={TOKEN}", origin="tauri://localhost") as ws:
            await receive_until(ws, "state")
            await ws.send(json.dumps({"type": "toggle"}))
            state = await receive_until(ws, "state")
            assert state["open"] is True and state["phase"] == "listening"
            assert mic_states[-1] is True

            await engine.listener.handle_utterance(np.zeros(16000, dtype=np.float32))
            transcript = await receive_until(ws, "transcript")
            assert transcript["text"] == "lägg till mjölk"

            await ws.send(json.dumps({"type": "toggle"}))
            state = await receive_until(ws, "state")
            assert state["open"] is False and state["phase"] == "off"
            assert mic_states[-1] is False
    finally:
        server.close()
        for w in workers:
            w.cancel()


@pytest.mark.asyncio
async def test_wake_mode_without_detector_reports_error():
    engine = make_engine()
    server, port, workers = await start(engine)
    try:
        async with connect(f"ws://127.0.0.1:{port}/?token={TOKEN}", origin="tauri://localhost") as ws:
            await ws.send(json.dumps({"type": "set_mode", "mode": "wake"}))
            error = await receive_until(ws, "error")
            assert "Väckningsord" in error["message"]
    finally:
        server.close()
        for w in workers:
            w.cancel()
