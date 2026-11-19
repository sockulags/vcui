from types import SimpleNamespace

import pytest

from vcui_engine.agent import Agent, build_user_message, to_claude_tools

UI_TOOLS = [
    {"name": "snapshot", "description": "Lists components", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "act", "description": "Runs steps", "inputSchema": {"type": "object", "properties": {"steps": {"type": "array"}}, "required": ["steps"]}},
]


def block(kind, **fields):
    return SimpleNamespace(type=kind, **fields)


def response(content, stop_reason):
    return SimpleNamespace(content=content, stop_reason=stop_reason,
                           usage=SimpleNamespace(input_tokens=100, output_tokens=20))


class FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def create(self, **request):
        # Copy the message list: the agent appends to it after this call.
        self.requests.append({**request, "messages": list(request["messages"])})
        return self.responses.pop(0)


class FakeClient:
    def __init__(self, responses):
        self.messages = FakeMessages(responses)


class FakeUI:
    def __init__(self):
        self.calls = []

    async def __call__(self, name, tool_input):
        self.calls.append((name, tool_input))
        if name == "snapshot":
            return True, [{"ref": "c1", "component": "input", "label": "Ny uppgift", "value": ""}]
        return True, {"ok": True}


def test_tools_are_converted():
    tools = to_claude_tools(UI_TOOLS)
    assert tools[1] == {"name": "act", "description": "Runs steps", "input_schema": UI_TOOLS[1]["inputSchema"]}


def test_user_message_holds_snapshot_transcript_and_history():
    text = build_user_message("lägg till mjölk", [{"ref": "c1"}], [("hej", "Hej!")])
    assert "<transcript>lägg till mjölk</transcript>" in text
    assert '"ref": "c1"' in text
    assert "recent_commands" in text


@pytest.mark.asyncio
async def test_runs_tools_then_replies():
    steps = {"steps": [{"ref": "Ny uppgift", "action": "setValue", "args": ["Köp mjölk"]},
                       {"ref": "Lägg till", "action": "press"}]}
    client = FakeClient([
        response([block("thinking", thinking="", signature="s"),
                  block("tool_use", id="tu1", name="act", input=steps)], "tool_use"),
        response([block("text", text="Jag lade till Köp mjölk.")], "end_turn"),
    ])
    ui = FakeUI()
    agent = Agent(client=client)
    result = await agent.run("lägg till köp mjölk", to_claude_tools(UI_TOOLS), ui)

    assert result.reply == "Jag lade till Köp mjölk."
    assert result.tool_calls == 1
    assert ui.calls == [("snapshot", {}), ("act", steps)]
    first, second = client.messages.requests
    assert first["model"] == "claude-haiku-5-5"
    assert first["output_config"] == {"effort": "low"}
    assert "temperature" not in first
    # The assistant turn goes back unchanged, thinking block included, then the tool result.
    assistant, results = second["messages"][1], second["messages"][2]
    assert assistant["content"][0].type == "thinking"
    assert results["content"][0]["tool_use_id"] == "tu1"
    assert "is_error" not in results["content"][0]
    assert agent.recent[-1] == ("lägg till köp mjölk", "Jag lade till Köp mjölk.")


@pytest.mark.asyncio
async def test_failed_tool_is_reported_as_error():
    client = FakeClient([
        response([block("tool_use", id="tu1", name="act", input={"steps": []})], "tool_use"),
        response([block("text", text="Det gick inte.")], "end_turn"),
    ])

    async def failing_ui(name, tool_input):
        return (True, []) if name == "snapshot" else (False, "Needs a person")

    await Agent(client=client).run("rensa allt", [], failing_ui)
    result_block = client.messages.requests[1]["messages"][2]["content"][0]
    assert result_block["is_error"] is True
    assert result_block["content"] == "Needs a person"


@pytest.mark.asyncio
async def test_refusal_gives_a_fixed_reply():
    client = FakeClient([response([], "refusal")])
    result = await Agent(client=client).run("något", [], FakeUI())
    assert result.reply == "Det kan jag inte hjälpa till med."
    assert result.stop_reason == "refusal"


@pytest.mark.asyncio
async def test_loop_stops_after_max_turns():
    endless = [response([block("tool_use", id=f"tu{i}", name="snapshot", input={})], "tool_use") for i in range(10)]
    client = FakeClient(endless)
    result = await Agent(client=client).run("gör något", [], FakeUI())
    assert len(client.messages.requests) == 6
    assert "hann inte" in result.reply
