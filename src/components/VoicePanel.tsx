import { Button } from "@ui-sdk/react/button"
import { Input } from "@ui-sdk/react/input"
import { Switch, SwitchThumb } from "@ui-sdk/react/switch"
import { AlertTriangle, CornerDownLeft, Mic, MicOff, Sparkles, Square, Undo2 } from "lucide-react"
import { useEffect, useRef, useState, useSyncExternalStore } from "react"
import { confirmStore } from "../agent"
import type { Voice } from "../voice/useVoice"

const SHORTCUT = navigator.userAgent.includes("Mac") ? "⌘ ⇧ Mellanslag" : "Ctrl ⇧ Mellanslag"

function statusText(voice: Voice): string {
  const { state, busy, transcribing } = voice
  if (!state.connected) return "Ansluter till röstmotorn…"
  if (state.stt === "loading") return "Laddar KB-Whisper…"
  if (state.stt === "failed") return "Taligenkänningen kunde inte laddas"
  if (busy) return "Tänker…"
  if (transcribing) return "Tolkar…"
  switch (state.phase) {
    case "speech":
      return "Jag hör dig"
    case "listening":
      return "Lyssnar – säg ett kommando"
    case "wake":
      return `Säg ”${state.wakeWord?.replace(/_/g, " ") ?? "väckningsordet"}”`
    default:
      return "Mikrofonen är av"
  }
}

export function VoicePanel({ voice, canUndo, onUndo }: { voice: Voice; canUndo: boolean; onUndo: () => void }) {
  const { state, level, log, busy } = voice
  const pending = useSyncExternalStore(confirmStore.subscribe, confirmStore.get)
  const [typed, setTyped] = useState("")
  const logEnd = useRef<HTMLDivElement>(null)
  useEffect(() => {
    // scrollIntoView returns a Promise in newer browsers; an effect must not return it.
    void logEnd.current?.scrollIntoView({ block: "end", behavior: "smooth" })
  }, [log.length])

  const live = state.phase === "listening" || state.phase === "speech"
  const activity = busy ? "thinking" : voice.transcribing ? "transcribing" : state.phase
  const ready = state.connected && state.stt === "ready"

  return (
    <aside className="voice" data-agent-hidden aria-label="Röststyrning">
      <div className="voice-hero">
        <button
          type="button"
          className="orb"
          data-activity={activity}
          aria-pressed={live}
          aria-label={live ? "Stäng mikrofonen" : "Öppna mikrofonen"}
          disabled={!ready}
          onClick={() => voice.toggle()}
          style={{ "--level": level } as React.CSSProperties}
        >
          <span className="orb-ring" aria-hidden="true" />
          <span className="orb-ring two" aria-hidden="true" />
          <span className="orb-core">{live ? <Mic size={30} aria-hidden="true" /> : <MicOff size={30} aria-hidden="true" />}</span>
        </button>
        <p className="voice-status" aria-live="polite">
          {statusText(voice)}
        </p>
        <p className="muted small">
          {state.mode === "wake" ? "Eller tryck för att prata direkt" : `Tryck, eller ${SHORTCUT}`}
        </p>
      </div>

      {pending && !document.querySelector('[data-slot="alert-dialog-content"][data-open]') && (
        <div className="confirm-bar" role="alertdialog" aria-label="Bekräfta">
          <AlertTriangle size={18} aria-hidden="true" />
          <div>
            <strong>{pending.text}.</strong>
            <span className="muted small"> Säg ”ja” eller ”nej”.</span>
          </div>
          <div className="confirm-actions">
            <Button className="ghost-button" onClick={() => confirmStore.answer(false)}>
              Nej
            </Button>
            <Button className="primary-button" onClick={() => confirmStore.answer(true)}>
              Ja
            </Button>
          </div>
        </div>
      )}

      <div className="voice-log" aria-label="Logg">
        {log.length === 0 && (
          <div className="hint">
            <Sparkles size={16} aria-hidden="true" />
            <div>
              <p>Prova att säga:</p>
              <ul>
                <li>”Lägg till köp kaffe på inköpslistan”</li>
                <li>”Bocka av tvättstugan”</li>
                <li>”Markera offerten som viktig”</li>
                <li>”Visa bara det som är kvar”</li>
                <li>”Rensa alla klara”</li>
              </ul>
            </div>
          </div>
        )}
        {log.map((entry) => (
          <div key={entry.id} className="log-entry" data-kind={entry.kind} data-ok={entry.ok === false ? "false" : undefined}>
            <span className="log-text">{entry.kind === "said" || entry.kind === "typed" ? `”${entry.text}”` : entry.text}</span>
            {entry.detail && <span className="log-detail">{entry.detail}</span>}
          </div>
        ))}
        <div ref={logEnd} />
      </div>

      <form
        className="typed-command"
        onSubmit={(event) => {
          event.preventDefault()
          if (!typed.trim()) return
          voice.sendText(typed.trim())
          setTyped("")
        }}
      >
        <Input aria-label="Skriv ett kommando" placeholder="…eller skriv ett kommando" value={typed} onValueChange={setTyped} />
        <button type="submit" className="icon-button" aria-label="Skicka" disabled={!state.connected}>
          <CornerDownLeft size={16} aria-hidden="true" />
        </button>
      </form>

      <div className="voice-foot">
        <label className="switch-label">
          <Switch
            className="switch"
            checked={state.mode === "wake"}
            disabled={!state.connected || (!state.wakeAvailable && state.mode !== "wake")}
            onCheckedChange={(checked) => voice.setMode(checked ? "wake" : "toggle")}
          >
            <SwitchThumb className="switch-thumb" />
          </Switch>
          Väckningsord
        </label>
        <div className="voice-foot-actions">
          {busy && (
            <Button className="ghost-button" onClick={() => voice.cancel()}>
              <Square size={14} aria-hidden="true" /> Avbryt
            </Button>
          )}
          <Button className="ghost-button" disabled={!canUndo} onClick={onUndo}>
            <Undo2 size={15} aria-hidden="true" /> Ångra
          </Button>
        </div>
      </div>
      {state.agent === "unavailable" && <p className="warning small">{state.agentError ?? "Claude är inte tillgängligt."}</p>}
    </aside>
  )
}
