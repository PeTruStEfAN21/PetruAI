import { History, Snapshot } from "./history";
import { AddOptions, ISO_DATE, PRIORITIES, Todo, copyTodo } from "./types";

export interface TodoListData {
  todos: Todo[];
  undo: Snapshot[];
  redo: Snapshot[];
}

export class TodoList {
  private todos: Todo[];
  private history: History;

  constructor(todos: Todo[] = [], history: History = new History()) {
    this.todos = todos.map(copyTodo);
    this.history = history;
  }

  static fromJSON(data: TodoListData): TodoList {
    return new TodoList(data.todos ?? [], new History(data.undo ?? [], data.redo ?? []));
  }

  toJSON(): TodoListData {
    return { todos: this.all(), ...this.history.toJSON() };
  }

  all(): Todo[] {
    return [...this.todos].sort((a, b) => a.id - b.id).map(copyTodo);
  }

  get(id: number): Todo {
    return copyTodo(this.find(id));
  }

  add(title: string, options: AddOptions = {}): Todo {
    const clean = cleanTitle(title);
    if (options.due !== undefined && !ISO_DATE.test(options.due)) {
      throw new Error(`invalid due date: ${options.due} (use YYYY-MM-DD)`);
    }
    const priority = options.priority ?? "normal";
    if (!PRIORITIES.includes(priority)) throw new Error(`invalid priority: ${priority}`);
    const todo: Todo = {
      id: this.todos.reduce((max, t) => Math.max(max, t.id), 0) + 1,
      title: clean,
      done: false,
      tags: [...(options.tags ?? [])],
      priority,
    };
    if (options.due !== undefined) todo.due = options.due;
    this.change(() => this.todos.push(todo));
    return copyTodo(todo);
  }

  complete(id: number): void {
    this.find(id);
    this.change(() => (this.find(id).done = true));
  }

  reopen(id: number): void {
    this.find(id);
    this.change(() => (this.find(id).done = false));
  }

  rename(id: number, title: string): void {
    this.find(id);
    const clean = cleanTitle(title);
    this.change(() => (this.find(id).title = clean));
  }

  remove(id: number): void {
    this.find(id);
    this.change(() => (this.todos = this.todos.filter((t) => t.id !== id)));
  }

  undo(): boolean {
    const previous = this.history.undo(this.todos);
    if (previous) this.todos = previous;
    return previous !== undefined;
  }

  redo(): boolean {
    const next = this.history.redo(this.todos);
    if (next) this.todos = next;
    return next !== undefined;
  }

  /** Every change is validated before it runs, so only successful changes reach the history. */
  private change(apply: () => unknown): void {
    this.history.record(this.todos);
    apply();
  }

  private find(id: number): Todo {
    const todo = this.todos.find((t) => t.id === id);
    if (!todo) throw new Error(`todo #${id} not found`);
    return todo;
  }
}

function cleanTitle(title: string): string {
  const clean = (title ?? "").trim();
  if (!clean) throw new Error("title must not be empty");
  return clean;
}
