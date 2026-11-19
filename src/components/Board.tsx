import {
  AlertDialog,
  AlertDialogBackdrop,
  AlertDialogClose,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@ui-sdk/react/alert-dialog"
import { Progress, ProgressIndicator, ProgressLabel, ProgressTrack, ProgressValue } from "@ui-sdk/react/progress"
import { SegmentedControl, SegmentedControlIndicator, SegmentedControlItem } from "@ui-sdk/react/segmented-control"
import { Switch, SwitchThumb } from "@ui-sdk/react/switch"
import { ListChecks } from "lucide-react"
import { useEffect, useState, useSyncExternalStore } from "react"
import { confirmStore, onConfirmDenied } from "../agent"
import { type Action, LISTS, type ListId, newTodo, type StatusFilter, type Todo, type View, visibleTodos } from "../todos"
import { AddTask } from "./AddTask"
import { ListSelect } from "./ListSelect"
import { TodoRow } from "./TodoRow"

function AgentWaiting() {
  const pending = useSyncExternalStore(confirmStore.subscribe, confirmStore.get)
  if (!pending) return null
  return <p className="agent-waiting">Rösten väntar på ditt svar – säg ”ja” eller ”nej”, eller tryck.</p>
}

const LIST_FILTER: { value: ListId | "alla"; label: string }[] = [{ value: "alla", label: "Alla listor" }, ...LISTS]

interface Props {
  todos: Todo[]
  dispatch: (action: Action) => void
}

export function Board({ todos, dispatch }: Props) {
  const [view, setView] = useState<View>({ status: "alla", list: "alla", importantFirst: false })
  const [flashing, setFlashing] = useState<Set<string>>(new Set())
  const [clearOpen, setClearOpen] = useState(false)

  // When the person says no to "Rensa", close the dialog the agent opened.
  useEffect(() => onConfirmDenied(() => setClearOpen(false)), [])

  const flash = (id: string) => {
    setFlashing((ids) => new Set(ids).add(id))
    setTimeout(() => setFlashing((ids) => {
      const next = new Set(ids)
      next.delete(id)
      return next
    }), 1400)
  }

  const shown = visibleTodos(todos, view)
  const doneCount = todos.filter((t) => t.done).length
  const percent = todos.length ? Math.round((doneCount / todos.length) * 100) : 0

  return (
    <section className="board" aria-labelledby="board-title">
      <header className="board-head">
        <div>
          <h1 id="board-title">Att göra</h1>
          <p className="muted">
            {todos.length - doneCount} kvar av {todos.length}
          </p>
        </div>
        <Progress value={percent} className="progress">
          <ProgressLabel className="sr-only">Avklarat</ProgressLabel>
          <ProgressTrack className="progress-track">
            <ProgressIndicator className="progress-indicator" />
          </ProgressTrack>
          <ProgressValue className="progress-value" />
        </Progress>
      </header>

      <AddTask
        onAdd={(text, list, important, byAgent) => {
          const todo = newTodo(text, list, important)
          dispatch({ type: "add", todo })
          if (byAgent) flash(todo.id)
          // Show the new task even when a filter would hide it.
          setView((v) => ({ ...v, status: v.status === "klara" ? "alla" : v.status, list: v.list === "alla" || v.list === list ? v.list : "alla" }))
        }}
      />

      <div className="filters">
        <SegmentedControl
          aria-label="Visa"
          className="segmented"
          value={view.status}
          onValueChange={(value) => value && setView((v) => ({ ...v, status: value as StatusFilter }))}
        >
          <SegmentedControlIndicator className="segmented-indicator" />
          <SegmentedControlItem value="alla" className="segmented-item">Alla</SegmentedControlItem>
          <SegmentedControlItem value="kvar" className="segmented-item">Att göra</SegmentedControlItem>
          <SegmentedControlItem value="klara" className="segmented-item">Klara</SegmentedControlItem>
        </SegmentedControl>
        <ListSelect label="Listfilter" hideLabel items={LIST_FILTER} value={view.list} onChange={(list) => setView((v) => ({ ...v, list }))} />
        <label className="switch-label">
          <Switch
            className="switch"
            checked={view.importantFirst}
            onCheckedChange={(checked) => setView((v) => ({ ...v, importantFirst: checked }))}
          >
            <SwitchThumb className="switch-thumb" />
          </Switch>
          Viktiga först
        </label>
      </div>

      {shown.length ? (
        <ul className="todo-list">
          {shown.map((todo) => (
            <TodoRow
              key={todo.id}
              todo={todo}
              flash={flashing.has(todo.id)}
              onDone={(done, byAgent) => {
                dispatch({ type: "setDone", id: todo.id, done })
                if (byAgent) flash(todo.id)
              }}
              onImportant={(important, byAgent) => {
                dispatch({ type: "setImportant", id: todo.id, important })
                if (byAgent) flash(todo.id)
              }}
              onRemove={() => dispatch({ type: "remove", id: todo.id })}
            />
          ))}
        </ul>
      ) : (
        <div className="empty">
          <ListChecks size={28} aria-hidden="true" />
          <p>{todos.length ? "Inget att visa med de här filtren." : "Listan är tom. Säg vad du behöver göra."}</p>
        </div>
      )}

      <footer className="board-foot">
        <span className="muted">{doneCount} klara</span>
        <AlertDialog
          open={clearOpen}
          onOpenChange={(open, details) => {
            // While the agent waits for the person, their click in the dialog is the
            // answer. The agent's own press then closes it.
            if (!open && confirmStore.get()) {
              details.cancel()
              confirmStore.answer(details.returnValue === "confirm")
              return
            }
            if (!open && details.returnValue === "confirm") dispatch({ type: "clearDone" })
            setClearOpen(open)
          }}
        >
          <AlertDialogTrigger className="ghost-button" disabled={!doneCount}>
            Rensa klara
          </AlertDialogTrigger>
          <AlertDialogBackdrop className="backdrop" />
          <AlertDialogContent className="dialog">
            <AlertDialogTitle className="dialog-title">Rensa klara uppgifter?</AlertDialogTitle>
            <AlertDialogDescription className="muted">
              {doneCount === 1 ? "En klar uppgift tas bort." : `${doneCount} klara uppgifter tas bort.`} Det går att ångra
              direkt efteråt.
            </AlertDialogDescription>
            <AgentWaiting />
            <div className="dialog-actions">
              <AlertDialogClose className="ghost-button">Avbryt</AlertDialogClose>
              <AlertDialogClose
                className="primary-button danger"
                value="confirm"
                data-agent-confirm="Tar bort alla klara uppgifter"
              >
                Rensa
              </AlertDialogClose>
            </div>
          </AlertDialogContent>
        </AlertDialog>
      </footer>
    </section>
  )
}
