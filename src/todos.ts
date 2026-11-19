export type ListId = "inkorg" | "jobb" | "hem" | "inkop"

export interface Todo {
  id: string
  text: string
  done: boolean
  important: boolean
  list: ListId
  createdAt: number
}

export const LISTS: { value: ListId; label: string }[] = [
  { value: "inkorg", label: "Inkorg" },
  { value: "jobb", label: "Jobb" },
  { value: "hem", label: "Hem" },
  { value: "inkop", label: "Inköp" },
]

export const listLabel = (id: ListId) => LISTS.find((list) => list.value === id)?.label ?? id

export type Action =
  | { type: "add"; todo: Todo }
  | { type: "setDone"; id: string; done: boolean }
  | { type: "setImportant"; id: string; important: boolean }
  | { type: "remove"; id: string }
  | { type: "clearDone" }
  | { type: "replace"; todos: Todo[] }

export function reducer(todos: Todo[], action: Action): Todo[] {
  switch (action.type) {
    case "add":
      return [action.todo, ...todos]
    case "setDone":
      return todos.map((t) => (t.id === action.id ? { ...t, done: action.done } : t))
    case "setImportant":
      return todos.map((t) => (t.id === action.id ? { ...t, important: action.important } : t))
    case "remove":
      return todos.filter((t) => t.id !== action.id)
    case "clearDone":
      return todos.filter((t) => !t.done)
    case "replace":
      return action.todos
  }
}

let counter = 0
export function newTodo(text: string, list: ListId, important: boolean): Todo {
  counter += 1
  return {
    id: `${Date.now().toString(36)}-${counter}`,
    text: text.trim(),
    done: false,
    important,
    list,
    createdAt: Date.now(),
  }
}

export type StatusFilter = "alla" | "kvar" | "klara"

export interface View {
  status: StatusFilter
  list: ListId | "alla"
  importantFirst: boolean
}

export function visibleTodos(todos: Todo[], view: View): Todo[] {
  const shown = todos.filter(
    (t) =>
      (view.status === "alla" || (view.status === "klara" ? t.done : !t.done)) &&
      (view.list === "alla" || t.list === view.list),
  )
  if (!view.importantFirst) return shown
  return [...shown].sort((a, b) => Number(b.important) - Number(a.important))
}

const STORAGE_KEY = "vcui.todos.v1"

const EXAMPLES: [string, ListId, boolean][] = [
  ["Köp havremjölk", "inkop", false],
  ["Boka tvättstugan", "hem", false],
  ["Skicka offert till Nordljus", "jobb", true],
  ["Ring tandläkaren", "inkorg", false],
]

export function loadTodos(): Todo[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw) as Todo[]
  } catch {
    // Storage can be unavailable or hold something else; start fresh.
  }
  return EXAMPLES.map(([text, list, important], index) => ({
    ...newTodo(text, list, important),
    done: index === 3,
  }))
}

export function saveTodos(todos: Todo[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(todos))
  } catch {
    // Not fatal: the list just won't survive a restart.
  }
}
