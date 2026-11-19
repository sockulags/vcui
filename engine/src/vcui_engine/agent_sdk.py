"""Agent backend that runs on the person's own Claude login.

The Claude Agent SDK starts the Claude Code CLI, which signs in the way Claude
Code does on that computer (a Claude subscription after `claude` /login, or an
API key if one is set). This is how T3 Code connects too. No API key is needed in
vcui itself.

The three UI SDK tools become an in-process MCP server, so tool calls still go to
the app's window through the same `ToolRunner` as the API backend. Every
built-in Claude Code tool is turned off, and no settings, CLAUDE.md or MCP
servers from the computer are loaded: the model can only read and act on the app.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from collections import deque
from typing import Any

from vcui_engine.agent import MODEL, SYSTEM_PROMPT, CommandResult, ToolRunner, build_user_message

log = logging.getLogger("vcui_engine.agent_sdk")

SERVER = "ui"
MAX_TURNS = 8


def find_claude_cli() -> str | None:
    """The Claude Code CLI the SDK will use: its bundled copy, or one on PATH."""
    try:
        from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport
        from claude_agent_sdk.types import ClaudeAgentOptions

        return SubprocessCLITransport(prompt="", options=ClaudeAgentOptions())._find_cli()
    except Exception:  # noqa: BLE001 - fall back to a PATH lookup
        return shutil.which("claude")


def _text(result: Any) -> str:
    return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)


class SdkAgent:
    backend = "sdk"

    def __init__(self, model: str = MODEL, effort: str = "low", cli_path: str | None = None):
        import claude_agent_sdk  # noqa: F401 - fail early if it is missing

        self.model = model
        self.effort = effort
        self.cli_path = cli_path or find_claude_cli()
        if not self.cli_path:
            raise RuntimeError("Claude Code hittades inte. Installera Claude Code och logga in med `claude`.")
        self.recent: deque[tuple[str, str]] = deque(maxlen=4)
        self._workdir = tempfile.mkdtemp(prefix="vcui-agent-")

    def _server(self, tools: list[dict[str, Any]], run_tool: ToolRunner, counter: list[int]):
        from claude_agent_sdk import create_sdk_mcp_server, tool

        def make(definition: dict[str, Any]):
            name = definition["name"]

            async def handler(args: dict[str, Any]) -> dict[str, Any]:
                counter[0] += 1
                ok, result = await run_tool(name, dict(args))
                return {"content": [{"type": "text", "text": _text(result)}], **({} if ok else {"is_error": True})}

            return tool(name, definition.get("description", ""), definition["input_schema"])(handler)

        return create_sdk_mcp_server(SERVER, tools=[make(d) for d in tools])

    async def run(self, text: str, tools: list[dict[str, Any]], run_tool: ToolRunner) -> CommandResult:
        from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query

        ok, snapshot = await run_tool("snapshot", {})
        if not ok:
            snapshot = {"error": _text(snapshot)}
        counter = [0]
        options = ClaudeAgentOptions(
            model=self.model,
            effort=self.effort,
            system_prompt=SYSTEM_PROMPT,
            tools=[],
            mcp_servers={SERVER: self._server(tools, run_tool, counter)},
            allowed_tools=[f"mcp__{SERVER}__{t['name']}" for t in tools],
            strict_mcp_config=True,
            setting_sources=[],
            max_turns=MAX_TURNS,
            cwd=self._workdir,
            cli_path=self.cli_path,
            stderr=lambda line: log.debug("claude: %s", line),
        )
        reply, stop_reason = "", None
        input_tokens = output_tokens = 0
        texts: list[str] = []
        async for message in query(prompt=build_user_message(text, snapshot, list(self.recent)), options=options):
            if isinstance(message, AssistantMessage):
                texts = [block.text.strip() for block in message.content if isinstance(block, TextBlock) and block.text.strip()] or texts
            elif isinstance(message, ResultMessage):
                stop_reason = message.terminal_reason or message.subtype
                usage = message.usage or {}
                input_tokens = int(usage.get("input_tokens", 0) or 0)
                output_tokens = int(usage.get("output_tokens", 0) or 0)
                if message.is_error:
                    detail = "; ".join(message.errors or []) or message.result or message.subtype
                    raise RuntimeError(describe_cli_error(detail, message.api_error_status))
                reply = (message.result or "").strip()
        reply = reply or " ".join(texts) or "Klart."
        self.recent.append((text, reply))
        log.info("command %r -> %r (%d tool calls, %s)", text, reply, counter[0], stop_reason)
        return CommandResult(reply, counter[0], stop_reason, input_tokens, output_tokens)


def describe_cli_error(detail: str, status: int | None) -> str:
    lowered = detail.lower()
    if status == 401 or "login" in lowered or "authenticat" in lowered or "api key" in lowered:
        return "Claude Code är inte inloggat. Kör `claude` i en terminal och logga in."
    if status == 429 or "rate limit" in lowered or "usage limit" in lowered:
        return "Användningsgränsen för Claude är nådd just nu."
    if status and status >= 500:
        return f"Claude svarade med fel {status}. Försök igen."
    return f"Claude Code-fel: {detail}"
