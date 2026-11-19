# vcui

Voice controlled UI: a Swedish to-do app you run by talking to it.

- **Speech recognition** runs on your computer with
  [KB-Whisper](https://huggingface.co/KBLab/kb-whisper-small) through faster-whisper,
  loaded the same way as in [referat](https://github.com/sockulags/referat).
- **Claude Haiku 5.5** turns what you said into actions, through the Claude Agent SDK and the
  Claude Code login on your computer (your Claude subscription, no API key). It gets the three tools of the
  [UI SDK](https://github.com/vercel-labs/ui) agent bridge (`snapshot`, `act`, `query`) and
  changes the app through its components' own APIs, without screenshots or clicks.
- **The app** is React 19 with UI SDK components (beta) in a Tauri 2 window.

```
microphone ─► endpointer ─► KB-Whisper ─► transcript ─► window
                                                          │  "ja" / "nej" / "ångra" handled here
                                                          ▼
                     Claude Haiku 5.5 ◄─► engine ◄── command
                                            │ tool_call (snapshot / act / query)
                                            ▼
                                 window: UI SDK agent bridge ─► components
```

## Run it

### Install a release

Download `vcui_<version>_x64-setup.exe` from the
[latest release](https://github.com/sockulags/vcui/releases/latest) and run it. vcui uses the
[Claude Code](https://claude.ai/install) installed on your computer: install it and run `claude`
once to log in. On Windows it must be the native `claude.exe` (the PowerShell installer), not
npm's `claude.cmd`. Windows SmartScreen warns about the unsigned installer: choose *More info*,
then *Run anyway*.

### Develop

You need Node 20+, [uv](https://docs.astral.sh/uv/), Rust with the
[Tauri prerequisites](https://v2.tauri.app/start/prerequisites/), and Claude Code logged in.

```bash
npm install
uv sync --project engine --extra wake
npm run tauri dev
```

Set `VCUI_AGENT=api` and `ANTHROPIC_API_KEY` to use the Messages API with a key instead of the
Claude Code login.

The debug build starts the engine itself with `uv run`. The first start downloads
KB-Whisper small (a few hundred MB) to the Hugging Face cache. The engine uses CUDA when
it can and falls back to the CPU.

Without Tauri, run the window in a browser and the engine beside it:

```bash
npm run engine   # terminal 1: engine on ws://127.0.0.1:8765, token "dev"
npm run dev      # terminal 2: http://localhost:1420
```

## Using it

- **Press to talk:** click the microphone or press `Ctrl+Shift+Space` (`⌘⇧Space` on macOS).
  The microphone stays open, and every pause ends a command, until you press again.
- **Wake word:** turn on *Väckningsord* (needs `--extra wake`). Say "hey jarvis", then
  your command. It keeps listening for 8 seconds after you last spoke.
  openWakeWord has no Swedish models; train one with its tools and pass the `.onnx`
  file with `VCUI_WAKE_MODEL`.
- **Type** a command in the field under the log when you can't talk.
- Say **"ångra"** to undo the last command. Clearing finished tasks asks you first:
  answer **"ja"** or **"nej"**, or press the buttons.

Things to try: "lägg till köp kaffe på inköpslistan", "bocka av tvättstugan",
"markera offerten som viktig", "visa bara det som är kvar", "rensa alla klara".

## Configuration

| Variable | Default | |
| --- | --- | --- |
| `VCUI_AGENT` | `sdk` | `sdk`: the Claude Code login on this computer. `api`: the Messages API with `ANTHROPIC_API_KEY`. |
| `VCUI_STT_MODEL` | `KBLab/kb-whisper-small` | Any faster-whisper model name or local path, e.g. `KBLab/kb-whisper-medium`. |
| `VCUI_WAKE_MODEL` | `hey_jarvis` | openWakeWord model name or `.onnx` path. Empty turns it off. |
| `VCUI_ENGINE_CMD` | | Tauri: run this shell command as the engine instead of the default. |

## Layout

| Path | |
| --- | --- |
| `src/` | The window: the to-do app (`components/`), the agent bridge (`agent.ts`) and the engine client (`voice/`). |
| `engine/` | Python engine: microphone, endpointer, KB-Whisper, wake word, the Claude agent loop, WebSocket server. Protocol in [engine/PROTOCOL.md](engine/PROTOCOL.md). |
| `src-tauri/` | Tauri shell: starts the engine with a fresh port and token, forwards the global shortcut. |

## Tests

```bash
npm test                         # transcript rules
npm run build                    # typecheck and build
uv run --project engine pytest   # endpointer, agent loop, WebSocket protocol
cargo build --manifest-path src-tauri/Cargo.toml
```

## Releases

`.github/workflows/build.yml` runs the tests, packages the engine with PyInstaller
(`engine/vcui-engine.spec`, one folder, shipped as app resources through
`src-tauri/tauri.release.conf.json`), smoke-tests it and builds the NSIS installer on Windows.
Every push keeps the installer as a workflow artifact. A push to `main` also publishes the
GitHub Release `v<version>`, with the version from `src-tauri/tauri.conf.json`.

The packaged app writes the engine log to `%LOCALAPPDATA%\se.sockulags.vcui\logs\engine.log`
(Windows).

## Limits

- Commands take about 2.5–3 seconds with Haiku through Claude Code: the CLI starts for each command.
- UI SDK is in beta (`0.1.0-beta.10`), and its APIs may change.
