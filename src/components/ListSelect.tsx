import { Select, SelectContent, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@ui-sdk/react/select"
import { ChevronDown } from "lucide-react"

interface Props<T extends string> {
  label: string
  items: { value: T; label: string }[]
  value: T
  onChange: (value: T, source: string) => void
  hideLabel?: boolean
}

/** A labelled UI SDK Select. The label is what the agent names it by. */
export function ListSelect<T extends string>({ label, items, value, onChange, hideLabel }: Props<T>) {
  return (
    <Select
      items={items}
      value={value}
      onValueChange={(next, details) => {
        if (next != null && !Array.isArray(next)) onChange(next as T, details.source ?? "")
      }}
    >
      <SelectLabel className={hideLabel ? "sr-only" : "field-label"}>{label}</SelectLabel>
      <SelectTrigger className="select-trigger">
        <SelectValue />
        <ChevronDown size={15} aria-hidden="true" />
      </SelectTrigger>
      <SelectContent className="select-content">
        {items.map((item) => (
          <SelectItem key={item.value} value={item.value} className="select-item">
            {item.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
