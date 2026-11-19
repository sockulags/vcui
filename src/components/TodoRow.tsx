import { Button } from "@ui-sdk/react/button"
import { Checkbox, CheckboxIndicator } from "@ui-sdk/react/checkbox"
import { Toggle } from "@ui-sdk/react/toggle"
import { Check, Star, Trash2 } from "lucide-react"
import { listLabel, type Todo } from "../todos"

interface Props {
  todo: Todo
  flash: boolean
  onDone: (done: boolean, byAgent: boolean) => void
  onImportant: (important: boolean, byAgent: boolean) => void
  onRemove: (byAgent: boolean) => void
}

export function TodoRow({ todo, flash, onDone, onImportant, onRemove }: Props) {
  return (
    <li className="todo" data-done={todo.done || undefined} data-flash={flash || undefined} data-list={todo.list}>
      <label className="todo-main">
        <Checkbox
          aria-label={todo.text}
          className="todo-check"
          checked={todo.done}
          onCheckedChange={(checked, details) => onDone(checked === true, details.source === "agent")}
        >
          <CheckboxIndicator>
            <Check size={14} strokeWidth={3} aria-hidden="true" />
          </CheckboxIndicator>
        </Checkbox>
        <span className="todo-text">{todo.text}</span>
      </label>
      <span className="chip" data-list={todo.list}>
        {listLabel(todo.list)}
      </span>
      <Toggle
        aria-label={`Viktig: ${todo.text}`}
        className="star-toggle small"
        pressed={todo.important}
        onPressedChange={(pressed, details) => onImportant(pressed, details.source === "agent")}
      >
        <Star size={15} aria-hidden="true" />
      </Toggle>
      <Button
        aria-label={`Ta bort ${todo.text}`}
        className="icon-button danger"
        onClick={(_, { source }) => onRemove(source === "agent")}
      >
        <Trash2 size={15} aria-hidden="true" />
      </Button>
    </li>
  )
}
