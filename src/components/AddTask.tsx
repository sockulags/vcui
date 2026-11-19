import { Button } from "@ui-sdk/react/button"
import { Input } from "@ui-sdk/react/input"
import { Toggle } from "@ui-sdk/react/toggle"
import { Plus, Star } from "lucide-react"
import { useRef, useState } from "react"
import { LISTS, type ListId } from "../todos"
import { ListSelect } from "./ListSelect"

interface Props {
  onAdd: (text: string, list: ListId, important: boolean, byAgent: boolean) => void
}

export function AddTask({ onAdd }: Props) {
  const [text, setText] = useState("")
  const [list, setList] = useState<ListId>("inkorg")
  const [important, setImportant] = useState(false)
  // The agent sets the fields and presses the button in one act call, before
  // React re-renders, so the button reads the latest values from this ref.
  const draft = useRef({ text, list, important })

  const submit = (source: string) => {
    const { text: value, list: target, important: flagged } = draft.current
    if (!value.trim()) throw new Error("Skriv vad uppgiften gäller först.")
    onAdd(value, target, flagged, source === "agent")
    draft.current = { text: "", list: target, important: false }
    setText("")
    setImportant(false)
  }

  return (
    <form
      className="add-task"
      onSubmit={(event) => {
        event.preventDefault()
        if (draft.current.text.trim()) submit("keyboard")
      }}
    >
      <div className="add-row">
        <Input
          aria-label="Ny uppgift"
          placeholder="Vad behöver göras?"
          className="add-input"
          value={text}
          onValueChange={(value) => {
            draft.current.text = value
            setText(value)
          }}
        />
        <Toggle
          aria-label="Prioritera"
          className="star-toggle"
          pressed={important}
          onPressedChange={(pressed) => {
            draft.current.important = pressed
            setImportant(pressed)
          }}
        >
          <Star size={17} aria-hidden="true" />
        </Toggle>
        <Button className="primary-button" onClick={(_, { source }) => submit(source)}>
          <Plus size={17} aria-hidden="true" />
          Lägg till
        </Button>
      </div>
      <div className="add-options">
        <ListSelect
          label="Lista"
          items={LISTS}
          value={list}
          onChange={(value) => {
            draft.current.list = value
            setList(value)
          }}
        />
      </div>
    </form>
  )
}
