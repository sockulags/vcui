import { agentTools, createAgent } from "@ui-sdk/react/agent"

/**
 * A step on a control marked with data-agent-confirm waits here for the person.
 * They answer with the buttons in the voice panel or by saying yes or no.
 */
export interface PendingConfirm {
  text: string
  resolve: (yes: boolean) => void
}

type Listener = () => void
let pending: PendingConfirm | null = null
const listeners = new Set<Listener>()

function setPending(next: PendingConfirm | null) {
  pending = next
  listeners.forEach((listener) => listener())
}

export const confirmStore = {
  get: () => pending,
  subscribe(listener: Listener) {
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
    }
  },
  answer(yes: boolean) {
    const current = pending
    if (!current) return false
    setPending(null)
    current.resolve(yes)
    return true
  },
}

const deniedListeners = new Set<() => void>()
export const onConfirmDenied = (listener: () => void) => {
  deniedListeners.add(listener)
  return () => {
    deniedListeners.delete(listener)
  }
}

function askPerson(text: string, signal: AbortSignal): Promise<boolean> {
  confirmStore.answer(false) // only one question at a time
  return new Promise((resolve) => {
    const done = (yes: boolean) => {
      if (!yes) deniedListeners.forEach((listener) => listener())
      resolve(yes)
    }
    setPending({ text, resolve: done })
    signal.addEventListener("abort", () => {
      if (pending?.text === text) setPending(null)
      done(false)
    })
  })
}

// Created before the app renders so the bridge sees every component as it mounts.
export const agent = createAgent({
  allow: (step, { signal }) => (step.confirm ? askPerson(step.confirm, signal) : true),
  timeout: 60_000,
})

export { agentTools }

export async function runAgentTool(name: string, input: Record<string, unknown>): Promise<unknown> {
  switch (name) {
    case "snapshot":
      return agent.snapshot()
    case "act":
      return agent.act(input as Parameters<typeof agent.act>[0])
    case "query":
      return agent.query(input as Parameters<typeof agent.query>[0])
    default:
      throw new Error(`Unknown tool ${name}`)
  }
}

if (import.meta.env.DEV) Object.assign(window, { agent })
