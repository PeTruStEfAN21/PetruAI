export interface Todo {
  id: number;
  title: string;
  done: boolean;
  tags: string[];
  priority: "low" | "normal" | "high";
  due?: string;
}

export interface HistoryEntry {
  type: "add" | "complete" | "reopen" | "rename" | "remove";
  todoId?: number;
  todo?: Todo;
  oldTitle?: string;
}

export interface TodoListState {
  version: number;
  todos: Todo[];
  history: HistoryEntry[];
  redoStack: HistoryEntry[];
}
