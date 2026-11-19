/**
 * The window's side of the engine protocol (engine/PROTOCOL.md).
 *
 * Inside Tauri the shell starts the engine and tells the window its address and
 * token. In a plain browser (`npm run dev` with `npm run engine`), the dev
 * engine runs on port 8765 with the token "dev".
 */

export type Phase = "off" | "wake" | "listening" | "speech"

export interface EngineState {
  connected: boolean
  stt: "loading" | "ready" | "failed" | "unknown"
  device: string | null
  agent: "ready" | "unavailable" | "unknown"
  agentError: string | null
  mode: "toggle" | "wake"
  open: boolean
  phase: Phase
  wakeAvailable: boolean
  wakeWord: string | null
}

export const initialEngineState: EngineState = {
  connected: false,
  stt: "unknown",
  device: null,
  agent: "unknown",
  agentError: null,
  mode: "toggle",
  open: false,
  phase: "off",
  wakeAvailable: false,
  wakeWord: null,
}

export type EngineMessage =
  | { type: "status"; stt: EngineState["stt"]; device: string | null; agent: EngineState["agent"]; agent_error: string | null }
  | { type: "state"; mode: EngineState["mode"]; open: boolean; phase: Phase; wake_available: boolean; wake_word: string | null }
  | { type: "level"; rms: number }
  | { type: "wake" }
  | { type: "transcribing"; id: number }
  | { type: "transcript"; id: number; text: string; stt_ms: number; audio_ms: number }
  | { type: "busy"; id: string; busy: boolean }
  | { type: "reply"; id: string; ok: boolean; text: string; ms?: number; tool_calls?: number }
  | { type: "tool_call"; id: string; name: string; input: Record<string, unknown> }
  | { type: "error"; message: string }

export interface EngineConfig {
  url: string
  token: string
}

declare global {
  interface Window {
    __TAURI_INTERNALS__?: unknown
  }
}

export const inTauri = () => typeof window !== "undefined" && "__TAURI_INTERNALS__" in window

export async function engineConfig(): Promise<EngineConfig> {
  if (inTauri()) {
    const { invoke } = await import("@tauri-apps/api/core")
    return invoke<EngineConfig>("engine_config")
  }
  return {
    url: import.meta.env.VITE_ENGINE_URL ?? "ws://127.0.0.1:8765",
    token: import.meta.env.VITE_ENGINE_TOKEN ?? "dev",
  }
}

type Handler = (message: EngineMessage) => void
type ConnectionHandler = (connected: boolean) => void

export class EngineClient {
  private socket: WebSocket | null = null
  private retry = 0
  private closed = false
  private timer: ReturnType<typeof setTimeout> | null = null

  constructor(
    private readonly config: () => Promise<EngineConfig>,
    private readonly hello: () => Record<string, unknown>,
    private readonly onMessage: Handler,
    private readonly onConnection: ConnectionHandler,
  ) {}

  async start() {
    this.closed = false
    let config: EngineConfig
    try {
      config = await this.config()
    } catch {
      this.schedule()
      return
    }
    if (this.closed) return
    const socket = new WebSocket(`${config.url}/?token=${encodeURIComponent(config.token)}`)
    this.socket = socket
    socket.onopen = () => {
      this.retry = 0
      socket.send(JSON.stringify({ type: "hello", ...this.hello() }))
      this.onConnection(true)
    }
    socket.onmessage = (event) => {
      try {
        this.onMessage(JSON.parse(String(event.data)) as EngineMessage)
      } catch (error) {
        console.error("Bad engine message", error)
      }
    }
    socket.onclose = () => {
      if (this.socket === socket) this.socket = null
      this.onConnection(false)
      this.schedule()
    }
  }

  private schedule() {
    if (this.closed) return
    const delay = Math.min(5000, 300 * 2 ** this.retry)
    this.retry += 1
    this.timer = setTimeout(() => void this.start(), delay)
  }

  send(message: Record<string, unknown>) {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(message))
      return true
    }
    return false
  }

  stop() {
    this.closed = true
    if (this.timer) clearTimeout(this.timer)
    this.socket?.close()
    this.socket = null
  }
}
