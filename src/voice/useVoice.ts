import { useCallback, useEffect, useRef, useState } from "react"
import { agentTools, confirmStore, runAgentTool } from "../agent"
import { isNoise, isUndo, yesOrNo } from "./speech"
import { EngineClient, engineConfig, type EngineMessage, type EngineState, inTauri, initialEngineState } from "./engine"

export interface LogEntry {
  id: string
  kind: "said" | "typed" | "reply" | "error" | "info"
  text: string
  detail?: string
  ok?: boolean
}

interface Options {
  /** A command is about to change the app: save what undo goes back to. */
  onCommandStart: () => void
  onUndo: () => boolean
}

let entryId = 0
const nextId = () => `e${++entryId}`

export function useVoice({ onCommandStart, onUndo }: Options) {
  const [state, setState] = useState<EngineState>(initialEngineState)
  const [level, setLevel] = useState(0)
  const [log, setLog] = useState<LogEntry[]>([])
  const [busy, setBusy] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const client = useRef<EngineClient | null>(null)
  const options = useRef({ onCommandStart, onUndo })
  options.current = { onCommandStart, onUndo }

  const add = useCallback((entry: Omit<LogEntry, "id">) => {
    setLog((entries) => [...entries.slice(-40), { ...entry, id: nextId() }])
  }, [])

  const runCommand = useCallback(
    (text: string, kind: "said" | "typed", detail?: string) => {
      // Spoken answers to a pending confirmation, and "ångra", never reach the agent.
      if (confirmStore.get()) {
        const answer = yesOrNo(text)
        if (answer !== null) {
          add({ kind, text, detail: answer ? "bekräftat" : "nekat" })
          confirmStore.answer(answer)
          return
        }
      }
      if (isUndo(text)) {
        const undone = options.current.onUndo()
        add({ kind, text })
        add({ kind: "reply", ok: undone, text: undone ? "Ångrade senaste kommandot." : "Det finns inget att ångra." })
        return
      }
      const id = nextId()
      add({ kind, text, detail })
      if (!client.current?.send({ type: "command", id, text })) {
        add({ kind: "error", text: "Motorn är inte ansluten." })
      }
    },
    [add],
  )

  const handle = useCallback(
    async (message: EngineMessage) => {
      switch (message.type) {
        case "status":
          setState((s) => ({ ...s, stt: message.stt, device: message.device, agent: message.agent, agentError: message.agent_error }))
          break
        case "state":
          setState((s) => ({
            ...s,
            mode: message.mode,
            open: message.open,
            phase: message.phase,
            wakeAvailable: message.wake_available,
            wakeWord: message.wake_word,
          }))
          if (message.phase === "off" || message.phase === "wake") setLevel(0)
          break
        case "level":
          setLevel(message.rms)
          break
        case "wake":
          add({ kind: "info", text: "Väckningsord hört – jag lyssnar." })
          break
        case "transcribing":
          setTranscribing(true)
          break
        case "transcript":
          setTranscribing(false)
          if (!isNoise(message.text)) {
            runCommand(message.text, "said", `${(message.audio_ms / 1000).toFixed(1)} s tal · ${message.stt_ms} ms`)
          }
          break
        case "busy":
          setBusy(message.busy)
          if (message.busy) options.current.onCommandStart()
          break
        case "reply":
          add({ kind: "reply", ok: message.ok, text: message.text, detail: message.ms ? `${message.ms} ms · ${message.tool_calls} verktygsanrop` : undefined })
          break
        case "tool_call": {
          let reply: Record<string, unknown>
          try {
            reply = { ok: true, result: await runAgentTool(message.name, message.input) }
          } catch (error) {
            reply = { ok: false, result: error instanceof Error ? error.message : String(error) }
          }
          client.current?.send({ type: "tool_result", id: message.id, ...reply })
          break
        }
        case "error":
          add({ kind: "error", text: message.message })
          break
      }
    },
    [add, runCommand],
  )

  useEffect(() => {
    const engine = new EngineClient(
      engineConfig,
      () => ({ client: "vcui", tools: agentTools }),
      (message) => void handle(message),
      (connected) => setState((s) => (connected ? { ...s, connected } : { ...initialEngineState })),
    )
    client.current = engine
    void engine.start()

    // The global shortcut is registered by the Tauri shell, which forwards it here.
    let unlisten: (() => void) | undefined
    if (inTauri()) {
      void import("@tauri-apps/api/event").then(({ listen }) =>
        listen("vcui://toggle", () => engine.send({ type: "toggle" })).then((stop) => {
          unlisten = stop
        }),
      )
    }
    return () => {
      unlisten?.()
      engine.stop()
    }
  }, [handle])

  return {
    state,
    level,
    log,
    busy,
    transcribing,
    toggle: () => client.current?.send({ type: "toggle" }),
    setMode: (mode: "toggle" | "wake") => client.current?.send({ type: "set_mode", mode }),
    cancel: () => client.current?.send({ type: "cancel" }),
    sendText: (text: string) => runCommand(text, "typed"),
  }
}

export type Voice = ReturnType<typeof useVoice>
