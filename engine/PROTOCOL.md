# Engine protocol

The window and the voice engine talk over one WebSocket on 127.0.0.1. Every
message, in both directions, is one JSON object with a `type`.

The window connects to `ws://127.0.0.1:<port>/?token=<token>`. The engine refuses
a wrong token and any origin other than the app's own (`tauri://localhost`,
`http(s)://tauri.localhost`, and with `--dev` the Vite server on port 1420),
because any web page in a browser on the same computer can reach localhost. The
Tauri shell picks the port and token, passes the token to the engine in
`VCUI_TOKEN`, and gives both to the window through the `engine_config` command.

One window is served at a time. A new connection replaces the old one, and tool
calls waiting on the old one fail.

## Window to engine

| type | fields | meaning |
| --- | --- | --- |
| `hello` | `tools`: the UI SDK `agentTools` definitions | Sent on connect. The engine gives these tools to Claude. |
| `toggle` | | Open or close the microphone (toggle mode), or open or close a command window (wake mode). |
| `set_open` | `open` | Same, with an explicit state. |
| `set_mode` | `mode`: `toggle` or `wake` | Wake mode needs the `wake` extra. |
| `command` | `id`, `text` | Run one command through the agent. Commands run one at a time, in order. |
| `cancel` | | Stop the running command. |
| `tool_result` | `id`, `ok`, `result` | The answer to a `tool_call`. |

## Engine to window

| type | fields | meaning |
| --- | --- | --- |
| `status` | `version`, `protocol`, `stt` (`loading`, `ready`, `failed`), `device`, `agent` (`ready`, `unavailable`), `agent_error` | Sent on connect and when the speech model finishes loading. |
| `state` | `mode`, `open`, `phase` (`off`, `wake`, `listening`, `speech`), `wake_available`, `wake_word` | The microphone state changed. |
| `level` | `rms` (0 to 1) | Input level, about ten times a second while the microphone is on. |
| `wake` | | The wake word was heard. |
| `transcribing` | `id` | An utterance ended and is being transcribed. |
| `transcript` | `id`, `text`, `stt_ms`, `audio_ms` | What was said. The window decides what to do with it: answer a pending confirmation, undo, or send it back as a `command`. |
| `busy` | `id`, `busy` | A command started or finished. |
| `tool_call` | `id`, `name` (`snapshot`, `act`, `query`), `input` | Run this on the UI SDK agent bridge and answer with `tool_result`. |
| `reply` | `id`, `ok`, `text`, and when it worked `ms`, `tool_calls`, `input_tokens`, `output_tokens` | The agent's answer to a command. |
| `error` | `message` | Something failed. The text is in Swedish and is shown as is. |

## Why the window dispatches transcripts

The engine does not turn a transcript into a command by itself. A person who
answers "ja" while the agent waits for a confirmation is answering that question,
and "ångra" restores the list without a model call. Only the window knows whether
a confirmation is pending, so it routes each transcript.
