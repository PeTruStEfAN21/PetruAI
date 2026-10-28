import { Todo, HistoryEntry, TodoListState } from "./types";

const MAX_HISTORY = 50;

export class TodoList {
  private todos: Todo[] = [];
  private nextId: number = 1;
  private history: HistoryEntry[] = [];
  private redoStack: HistoryEntry[] = [];

  private pushHistory(entry: HistoryEntry): void {
    this.history.push(entry);
    if (this.history.length > MAX_HISTORY) {
      this.history = this.history.slice(this.history.length - MAX_HISTORY);
    }
    this.redoStack = [];
  }

  add(title: string, opts?: { tags?: string[]; priority?: "low" | "normal" | "high"; due?: string }): Todo {
    const trimmed = title.trim();
    if (!trimmed) {
      throw new Error("title must not be empty");
    }
    const due = opts?.due;
    if (due !== undefined) {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(due)) {
        throw new Error(`invalid due date: ${due}`);
      }
      const d = new Date(due);
      if (isNaN(d.getTime())) {
        throw new Error(`invalid due date: ${due}`);
      }
    }
    const todo: Todo = {
      id: this.nextId++,
      title: trimmed,
      done: false,
      tags: opts?.tags ?? [],
      priority: opts?.priority ?? "normal",
      due,
    };
    this.todos.push(todo);
    this.pushHistory({ type: "add", todoId: todo.id });
    return JSON.parse(JSON.stringify(todo));
  }

  get(id: number): Todo {
    const todo = this.todos.find((t) => t.id === id);
    if (!todo) {
      throw new Error(`todo #${id} not found`);
    }
    return JSON.parse(JSON.stringify(todo));
  }

  all(): Todo[] {
    return this.todos
      .slice()
      .sort((a, b) => a.id - b.id)
      .map((t) => JSON.parse(JSON.stringify(t)));
  }

  complete(id: number): void {
    const todo = this.todos.find((t) => t.id === id);
    if (!todo) {
      throw new Error(`todo #${id} not found`);
    }
    todo.done = true;
    this.pushHistory({ type: "complete", todoId: id });
  }

  reopen(id: number): void {
    const todo = this.todos.find((t) => t.id === id);
    if (!todo) {
      throw new Error(`todo #${id} not found`);
    }
    todo.done = false;
    this.pushHistory({ type: "reopen", todoId: id });
  }

  rename(id: number, newTitle: string): void {
    const todo = this.todos.find((t) => t.id === id);
    if (!todo) {
      throw new Error(`todo #${id} not found`);
    }
    const oldTitle = todo.title;
    todo.title = newTitle.trim();
    this.pushHistory({ type: "rename", todoId: id, oldTitle });
  }

  remove(id: number): void {
    const idx = this.todos.findIndex((t) => t.id === id);
    if (idx === -1) {
      throw new Error(`todo #${id} not found`);
    }
    const removed = this.todos.splice(idx, 1)[0];
    this.pushHistory({ type: "remove", todoId: id, todo: JSON.parse(JSON.stringify(removed)) });
  }

  undo(): boolean {
    if (this.history.length === 0) return false;
    const entry = this.history.pop()!;
    this.redoStack.push(entry);
    this.revert(entry);
    return true;
  }

  redo(): boolean {
    if (this.redoStack.length === 0) return false;
    const entry = this.redoStack.pop()!;
    this.history.push(entry);
    this.reapply(entry);
    return true;
  }

  private revert(entry: HistoryEntry): void {
    switch (entry.type) {
      case "add":
        this.todos = this.todos.filter((t) => t.id !== entry.todoId);
        this.nextId--;
        break;
      case "complete":
        const c = this.todos.find((t) => t.id === entry.todoId);
        if (c) c.done = false;
        break;
      case "reopen":
        const r = this.todos.find((t) => t.id === entry.todoId);
        if (r) r.done = true;
        break;
      case "rename":
        const n = this.todos.find((t) => t.id === entry.todoId);
        if (n) n.title = entry.oldTitle!;
        break;
      case "remove":
        if (entry.todo) {
          this.todos.push(entry.todo);
          this.todos.sort((a, b) => a.id - b.id);
        }
        break;
    }
  }

  private reapply(entry: HistoryEntry): void {
    switch (entry.type) {
      case "add":
        this.todos.push({
          id: entry.todoId!,
          title: "placeholder",
          done: false,
          tags: [],
          priority: "normal",
        });
        this.todos.sort((a, b) => a.id - b.id);
        this.nextId = Math.max(this.nextId, entry.todoId! + 1);
        break;
      case "complete":
        const c = this.todos.find((t) => t.id === entry.todoId);
        if (c) c.done = true;
        break;
      case "reopen":
        const r = this.todos.find((t) => t.id === entry.todoId);
        if (r) r.done = false;
        break;
      case "rename":
        const n = this.todos.find((t) => t.id === entry.todoId);
        if (n) n.title = entry.oldTitle!;
        break;
      case "remove":
        this.todos = this.todos.filter((t) => t.id !== entry.todoId);
        break;
    }
  }

  toJSON(): TodoListState {
    return {
      version: 1,
      todos: JSON.parse(JSON.stringify(this.todos)),
      history: JSON.parse(JSON.stringify(this.history)),
      redoStack: JSON.parse(JSON.stringify(this.redoStack)),
    };
  }

  static fromJSON(state: TodoListState): TodoList {
    const list = new TodoList();
    list.todos = JSON.parse(JSON.stringify(state.todos));
    list.history = JSON.parse(JSON.stringify(state.history));
    list.redoStack = JSON.parse(JSON.stringify(state.redoStack));
    if (list.todos.length > 0) {
      list.nextId = Math.max(...list.todos.map((t) => t.id)) + 1;
    }
    return list;
  }
}
