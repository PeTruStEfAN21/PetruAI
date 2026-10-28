import { Todo } from "./types";

export interface Filter {
  words?: string[];
  tags?: string[];
  status?: "done" | "open";
  priority?: "low" | "normal" | "high";
  dueExact?: string;
  dueBefore?: string;
  dueAfter?: string;
  dueNone?: boolean;
}

function parseDate(dateStr: string): Date {
  const [year, month, day] = dateStr.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function isValidDate(dateStr: string): boolean {
  const date = parseDate(dateStr);
  return !isNaN(date.getTime());
}

export function parseFilter(query: string): Filter {
  const filter: Filter = {};
  const tokens = query.trim().split(/\s+/).filter(t => t.length > 0);

  for (const token of tokens) {
    if (token === "") continue;

    // Plain word: matches title (case-insensitive, all words must match)
    if (!token.includes(":")) {
      const words = token.toLowerCase().split(/\s+/);
      if (words.length > 0) {
        filter.words = words;
      }
      continue;
    }

    const colonIndex = token.indexOf(":");
    const key = token.substring(0, colonIndex);
    const value = token.substring(colonIndex + 1);

    // is:done or is:open
    if (key === "is") {
      if (value !== "done" && value !== "open") {
        throw new Error("is:");
      }
      filter.status = value;
      continue;
    }

    // tag:X
    if (key === "tag") {
      if (value === "") {
        throw new Error("tag:");
      }
      if (filter.tags) {
        filter.tags = [...filter.tags, value];
      } else {
        filter.tags = [value];
      }
      continue;
    }

    // priority:low|normal|high
    if (key === "priority") {
      if (!["low", "normal", "high"].includes(value)) {
        throw new Error("priority");
      }
      filter.priority = value as "low" | "normal" | "high";
      continue;
    }

    // due:none
    if (key === "due" && value === "none") {
      filter.dueNone = true;
      continue;
    }

    // due:<DATE (before)
    if (key === "due" && value.startsWith("<")) {
      const dateStr = value.substring(1);
      if (!dateStr || !isValidDate(dateStr)) {
        throw new Error("due");
      }
      filter.dueBefore = dateStr;
      continue;
    }

    // due:>DATE (after)
    if (key === "due" && value.startsWith(">")) {
      const dateStr = value.substring(1);
      if (!dateStr || !isValidDate(dateStr)) {
        throw new Error("due");
      }
      filter.dueAfter = dateStr;
      continue;
    }

    // due:DATE (exact)
    if (key === "due" && value.length > 0) {
      const dateStr = value;
      if (!isValidDate(dateStr)) {
        throw new Error("due");
      }
      filter.dueExact = dateStr;
      continue;
    }

    // Unknown key
    throw new Error(`unknown filter key: ${key}`);
  }

  return filter;
}

export function applyFilter(todos: Todo[], filter: Filter): Todo[] {
  return todos.filter(todo => {
    // Check words (title match)
    if (filter.words) {
      const titleLower = todo.title.toLowerCase();
      for (const word of filter.words) {
        if (!titleLower.includes(word)) {
          return false;
        }
      }
    }

    // Check tags (all given tags must match)
    const hasTags = filter.tags !== undefined;
    if (hasTags && todo.tags) {
      const allMatch = (filter.tags as string[]).every(ftag => todo.tags!.includes(ftag));
      if (!allMatch) {
        return false;
      }
    }

    // Check status
    if (filter.status === "done" && !todo.done) {
      return false;
    }
    if (filter.status === "open" && todo.done) {
      return false;
    }

    // Check priority
    if (filter.priority && todo.priority !== filter.priority) {
      return false;
    }

    // Check due dates
    if (filter.dueBefore) {
      const todoDate = todo.due ? parseDate(todo.due) : null;
      if (todoDate) {
        const filterDate = parseDate(filter.dueBefore);
        if (todoDate >= filterDate) {
          return false;
        }
      } else {
        return false;
      }
    }

    if (filter.dueAfter) {
      const todoDate = todo.due ? parseDate(todo.due) : null;
      if (todoDate) {
        const filterDate = parseDate(filter.dueAfter);
        if (todoDate <= filterDate) {
          return false;
        }
      } else {
        return false;
      }
    }

    if (filter.dueExact) {
      const todoDate = todo.due ? parseDate(todo.due) : null;
      if (todoDate) {
        const filterDate = parseDate(filter.dueExact);
        if (todoDate.getTime() !== filterDate.getTime()) {
          return false;
        }
      } else {
        return false;
      }
    }

    if (filter.dueNone) {
      if (todo.due) {
        return false;
      }
    }

    return true;
  });
}
