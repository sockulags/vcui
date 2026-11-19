"""WebSocket server between the vcui window and the voice engine.

The window connects to ws://127.0.0.1:<port>/?token=<token>. The engine accepts
only that token and only the app's own origins, because any web page in a
browser on the same computer can open a connection to localhost. One window is
served at a time; a new connection replaces the old one. The message protocol is
described in PROTOCOL.md.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import itertools
import json
import logging
import os
import secrets
import time
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs, urlparse

import numpy as np
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from vcui_engine import PROTOCOL_VERSION, __version__
from vcui_engine.agent import Agent, to_claude_tools
from vcui_engine.listener import Listener

log = logging.getLogger("vcui_engine.server")

APP_ORIGINS = ["tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"]
DEV_ORIGINS = ["http://localhost:1420", "http://127.0.0.1:1420"]
TOOL_TIMEOUT_S = 90  # long enough for a person to answer a confirmation


class Engine:
    def __init__(self, listener: Listener, agent: Agent | None, agent_error: str | None = None):
        self.listener = listener
        self.agent = agent
        self.agent_error = agent_error
        self.stt_status = "loading"
        self.stt_device: str | None = None
        self._connection: ServerConnection | None = None
        self._tools: list[dict[str, Any]] = []
        self._tool_ids = itertools.count(1)
        self._tool_waiters: dict[str, asyncio.Future] = {}
        self._commands: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        self._current: asyncio.Task | None = None

    # ----- sending -----

    async def emit(self, message: dict) -> None:
        connection = self._connection
        if connection is None:
            return
        with contextlib.suppress(ConnectionClosed):
            await connection.send(json.dumps(message, ensure_ascii=False))

    def status(self) -> dict:
        return {
            "type": "status",
            "version": __version__,
            "protocol": PROTOCOL_VERSION,
            "stt": self.stt_status,
            "device": self.stt_device,
            "agent": "ready" if self.agent else "unavailable",
            "agent_backend": getattr(self.agent, "backend", None),
            "agent_error": self.agent_error,
        }

    # ----- one window connection -----

    async def handle(self, connection: ServerConnection) -> None:
        previous = self._connection
        self._connection = connection
        if previous is not None:
            await previous.close(1000, "replaced by a new window")
        self._fail_tool_calls("the window reconnected")
        await self.emit(self.status())
        await self.emit(self.listener.state())
        try:
            async for raw in connection:
                try:
                    await self.receive(json.loads(raw))
                except (ValueError, KeyError, TypeError) as error:
                    await self.emit({"type": "error", "message": f"Bad message: {error}"})
        except ConnectionClosed:
            pass
        finally:
            if self._connection is connection:
                self._connection = None
                self._fail_tool_calls("the window closed")
                await self.listener.set_open(False)

    async def receive(self, message: dict) -> None:
        kind = message["type"]
        if kind == "hello":
            self._tools = to_claude_tools(message.get("tools", []))
        elif kind == "toggle":
            await self.listener.toggle()
        elif kind == "set_open":
            await self.listener.set_open(bool(message["open"]))
        elif kind == "set_mode":
            await self.listener.set_mode(message["mode"])
        elif kind == "command":
            text = str(message["text"]).strip()
            if text:
                self._commands.put_nowait((str(message.get("id", "")), text))
        elif kind == "cancel":
            if self._current is not None:
                self._current.cancel()
        elif kind == "tool_result":
            waiter = self._tool_waiters.pop(str(message["id"]), None)
            if waiter is not None and not waiter.done():
                waiter.set_result((bool(message.get("ok", True)), message.get("result")))
        else:
            raise ValueError(f"unknown type {kind!r}")

    # ----- tools run in the window -----

    async def run_tool(self, name: str, tool_input: dict[str, Any]) -> tuple[bool, Any]:
        if self._connection is None:
            return False, "The app window is not connected."
        call_id = f"t{next(self._tool_ids)}"
        log.info("tool %s %s", name, json.dumps(tool_input, ensure_ascii=False)[:400])
        waiter = asyncio.get_running_loop().create_future()
        self._tool_waiters[call_id] = waiter
        await self.emit({"type": "tool_call", "id": call_id, "name": name, "input": tool_input})
        try:
            return await asyncio.wait_for(waiter, TOOL_TIMEOUT_S)
        except TimeoutError:
            return False, "The app did not answer in time."
        finally:
            self._tool_waiters.pop(call_id, None)

    def _fail_tool_calls(self, reason: str) -> None:
        for waiter in self._tool_waiters.values():
            if not waiter.done():
                waiter.set_result((False, f"Cancelled: {reason}."))
        self._tool_waiters.clear()

    # ----- commands, one at a time -----

    async def command_worker(self) -> None:
        while True:
            command_id, text = await self._commands.get()
            self._current = asyncio.create_task(self._run_command(command_id, text))
            with contextlib.suppress(asyncio.CancelledError):
                await self._current
            self._current = None

    async def _run_command(self, command_id: str, text: str) -> None:
        if self.agent is None:
            await self.emit({"type": "reply", "id": command_id, "ok": False,
                             "text": self.agent_error or "Agenten är inte tillgänglig."})
            return
        await self.emit({"type": "busy", "id": command_id, "busy": True})
        started = time.perf_counter()
        try:
            result = await self.agent.run(text, self._tools, self.run_tool)
            await self.emit({
                "type": "reply", "id": command_id, "ok": True, "text": result.reply,
                "tool_calls": result.tool_calls, "ms": round((time.perf_counter() - started) * 1000),
                "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
            })
        except asyncio.CancelledError:
            await self.emit({"type": "reply", "id": command_id, "ok": False, "text": "Avbrutet."})
            raise
        except Exception as error:  # noqa: BLE001 - report every failure to the window
            log.exception("command failed")
            await self.emit({"type": "reply", "id": command_id, "ok": False, "text": describe_error(error)})
        finally:
            await self.emit({"type": "busy", "id": command_id, "busy": False})


def describe_error(error: Exception) -> str:
    import anthropic

    if isinstance(error, anthropic.AuthenticationError):
        return "API-nyckeln godkändes inte. Kontrollera ANTHROPIC_API_KEY."
    if isinstance(error, anthropic.RateLimitError):
        return "För många anrop just nu. Vänta en stund och försök igen."
    if isinstance(error, anthropic.APIConnectionError):
        return "Kunde inte nå Claude. Kontrollera nätverket."
    if isinstance(error, anthropic.APIStatusError):
        return f"Claude svarade med fel {error.status_code}."
    return f"Något gick fel: {error}"


def make_request_check(token: str):
    def process_request(connection: ServerConnection, request):
        query = parse_qs(urlparse(request.path).query)
        supplied = query.get("token", [""])[0]
        if not secrets.compare_digest(supplied.encode(), token.encode()):
            return connection.respond(HTTPStatus.FORBIDDEN, "bad token\n")
        return None

    return process_request


async def serve_engine(engine: Engine, host: str, port: int, token: str, allow_dev: bool,
                       frames: asyncio.Queue[np.ndarray]) -> None:
    origins = APP_ORIGINS + (DEV_ORIGINS if allow_dev else [])
    async with serve(engine.handle, host, port, origins=origins,
                     process_request=make_request_check(token), max_size=2**22) as server:
        bound = server.sockets[0].getsockname()[1]
        # The Tauri shell reads this line to learn the engine is up.
        print(json.dumps({"event": "listening", "port": bound}), flush=True)
        log.info("engine listening on ws://%s:%d", host, bound)
        await asyncio.gather(engine.listener.run(), engine.command_worker())


def create_agent(backend: str) -> tuple[Agent | None, str | None]:
    """`sdk` runs on the computer's Claude Code login; `api` needs ANTHROPIC_API_KEY."""
    try:
        if backend == "api":
            return Agent(), None
        from vcui_engine.agent_sdk import SdkAgent

        return SdkAgent(), None  # type: ignore[return-value]
    except Exception as error:  # noqa: BLE001 - the window shows why
        return None, f"Claude är inte tillgängligt: {error}"


async def load_speech(engine: Engine, model: str, device: str, wake_model: str | None) -> None:
    from vcui_engine.stt import WhisperTranscriber
    from vcui_engine.wakeword import load_wake_detector

    if wake_model:
        engine.listener.wake = await asyncio.to_thread(load_wake_detector, wake_model)
        if engine.listener.wake is not None:
            log.info("wake word ready: %s", wake_model)
        await engine.emit(engine.listener.state())
    try:
        transcriber = await asyncio.to_thread(WhisperTranscriber, model, device)
        engine.listener.transcriber = transcriber
        engine.stt_status, engine.stt_device = "ready", transcriber.device
        log.info("speech model ready: %s on %s", model, transcriber.device)
    except Exception as error:  # noqa: BLE001
        log.exception("speech model failed to load")
        engine.stt_status = "failed"
        await engine.emit({"type": "error", "message": f"Taligenkänningen kunde inte laddas: {error}"})
    await engine.emit(engine.status())


async def amain(args: argparse.Namespace) -> None:
    from vcui_engine.audio import MicStream

    loop = asyncio.get_running_loop()
    frames: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=200)
    device = int(args.input_device) if args.input_device and args.input_device.isdigit() else args.input_device
    mic = MicStream(frames, loop, device=device)

    def control_mic(on: bool) -> None:
        try:
            mic.start() if on else mic.stop()
        except Exception as error:  # noqa: BLE001
            log.exception("microphone failed")
            loop.create_task(engine.emit({"type": "error", "message": f"Mikrofonen gick inte att öppna: {error}"}))

    agent, agent_error = create_agent(args.agent)
    holder: dict[str, Engine] = {}

    async def emit(message: dict) -> None:
        await holder["engine"].emit(message)

    listener = Listener(frames, emit, control_mic)
    engine = Engine(listener, agent, agent_error)
    holder["engine"] = engine
    loop.create_task(load_speech(engine, args.model, args.device, args.wake_model))
    token = args.token or os.environ.get("VCUI_TOKEN") or ""
    if not token:
        token = secrets.token_urlsafe(24)
        log.warning("no token given; generated one for this run: %s", token)
    await serve_engine(engine, args.host, args.port, token, args.dev, frames)


def main() -> None:
    parser = argparse.ArgumentParser(description="vcui voice engine")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("VCUI_ENGINE_PORT", "8765")))
    parser.add_argument("--token", default=None, help="defaults to $VCUI_TOKEN")
    parser.add_argument("--dev", action="store_true", help="also accept the Vite dev server's origin")
    parser.add_argument("--model", default=os.environ.get("VCUI_STT_MODEL", "KBLab/kb-whisper-small"))
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--wake-model", default=os.environ.get("VCUI_WAKE_MODEL", "hey_jarvis"),
                        help="openWakeWord model name or .onnx path; empty turns wake word off")
    parser.add_argument("--agent", choices=["sdk", "api"], default=os.environ.get("VCUI_AGENT", "sdk"),
                        help="sdk: the Claude Code login on this computer (default); api: ANTHROPIC_API_KEY")
    parser.add_argument("--log-file", default=None, help="also write the log to this file")
    parser.add_argument("--input-device", default=None, help="sounddevice input device name or index")
    args = parser.parse_args()
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if args.log_file:
        handlers.append(logging.FileHandler(args.log_file, encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=handlers)
    # Quiet the per-request lines from the model download.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(amain(args))


if __name__ == "__main__":
    main()
