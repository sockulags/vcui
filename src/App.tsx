import { AudioLines } from "lucide-react"
import { useCallback, useEffect, useReducer, useRef, useState } from "react"
import { Board } from "./components/Board"
import { VoicePanel } from "./components/VoicePanel"
import { loadTodos, reducer, saveTodos, type Todo } from "./todos"
import { useVoice } from "./voice/useVoice"

const UNDO_LIMIT = 20

export function App() {
  const [todos, dispatch] = useReducer(reducer, undefined, loadTodos)
  const todosRef = useRef(todos)
  todosRef.current = todos
  // Undo goes back to the list as it was before each voice or typed command.
  const undoStack = useRef<Todo[][]>([])
  const [undoCount, setUndoCount] = useState(0)

  useEffect(() => {
    saveTodos(todos)
  }, [todos])

  const onCommandStart = useCallback(() => {
    undoStack.current = [...undoStack.current.slice(-(UNDO_LIMIT - 1)), todosRef.current]
    setUndoCount(undoStack.current.length)
  }, [])

  const undo = useCallback(() => {
    const previous = undoStack.current.pop()
    setUndoCount(undoStack.current.length)
    if (!previous) return false
    dispatch({ type: "replace", todos: previous })
    return true
  }, [])

  const voice = useVoice({ onCommandStart, onUndo: undo })

  return (
    <div className="app">
      <header className="topbar" data-agent-hidden>
        <div className="brand">
          <span className="brand-mark">
            <AudioLines size={18} aria-hidden="true" />
          </span>
          <span className="brand-name">vcui</span>
          <span className="brand-sub">röststyrd att göra-lista</span>
        </div>
        <div className="engine-pill" data-ok={voice.state.connected && voice.state.stt === "ready" ? "true" : "false"}>
          <span className="dot" />
          {voice.state.connected
            ? `KB-Whisper ${voice.state.stt === "ready" ? `· ${voice.state.device ?? ""}` : "laddar"} · Haiku 5.5`
            : "Röstmotorn är inte ansluten"}
        </div>
      </header>
      <main className="layout">
        <Board todos={todos} dispatch={dispatch} />
        <VoicePanel voice={voice} canUndo={undoCount > 0} onUndo={undo} />
      </main>
    </div>
  )
}
