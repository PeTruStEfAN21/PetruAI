import { ISO_DATE, PRIORITIES, Priority, Todo } from "./types";

export interface Filter {
  words: string[];
  tags: string[];
  done?: boolean;
  priority?: Priority;
  due?: { op: "<" | ">" | "=" | "none"; date?: string };
}

export function parseFilter(query: string): Filter {
  const filter: Filter = { words: [], tags: [] };
  for (const term of query.split(/\s+/).filter(Boolean)) {
    const colon = term.indexOf(":");
    if (colon < 0) {
      filter.words.push(term.toLowerCase());
      continue;
    }
    const key = term.slice(0, colon);
    const value = term.slice(colon + 1);
    switch (key) {
      case "tag":
        filter.tags.push(value);
        break;
      case "is":
        if (value !== "done" && value !== "open") throw new Error(`is: must be done or open, not ${value}`);
        filter.done = value === "done";
        break;
      case "priority":
        if (!PRIORITIES.includes(value as Priority)) throw new Error(`invalid priority: ${value}`);
        filter.priority = value as Priority;
        break;
      case "due":
        filter.due = parseDue(value);
        break;
      default:
        throw new Error(`unknown filter key: ${key}`);
    }
  }
  return filter;
}

function parseDue(value: string): Filter["due"] {
  if (value === "none") return { op: "none" };
  const op: "<" | ">" | "=" = value[0] === "<" || value[0] === ">" ? value[0] : "=";
  const date = op === "=" ? value : value.slice(1);
  if (!ISO_DATE.test(date)) throw new Error(`invalid due date: ${date}`);
  return { op, date };
}

export function matches(todo: Todo, filter: Filter): boolean {
  const title = todo.title.toLowerCase();
  if (!filter.words.every((w) => title.includes(w))) return false;
  if (!filter.tags.every((t) => todo.tags.includes(t))) return false;
  if (filter.done !== undefined && todo.done !== filter.done) return false;
  if (filter.priority !== undefined && todo.priority !== filter.priority) return false;
  const due = filter.due;
  if (due) {
    if (due.op === "none") return todo.due === undefined;
    if (todo.due === undefined) return false;
    const date = due.date as string;
    if (due.op === "<") return todo.due < date;
    if (due.op === ">") return todo.due > date;
    return todo.due === date;
  }
  return true;
}

export function applyFilter(todos: Todo[], filter: Filter): Todo[] {
  return todos.filter((t) => matches(t, filter));
}
