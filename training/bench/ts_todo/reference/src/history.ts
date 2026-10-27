import { Todo, copyTodo } from "./types";

export const HISTORY_LIMIT = 50;

export type Snapshot = Todo[];

const snapshot = (todos: Todo[]): Snapshot => todos.map(copyTodo);

/** Undo and redo stacks of whole-list snapshots, capped at HISTORY_LIMIT steps. */
export class History {
  constructor(
    private undoStack: Snapshot[] = [],
    private redoStack: Snapshot[] = [],
  ) {}

  record(before: Todo[]): void {
    this.undoStack.push(snapshot(before));
    if (this.undoStack.length > HISTORY_LIMIT) this.undoStack.shift();
    this.redoStack = [];
  }

  undo(current: Todo[]): Snapshot | undefined {
    const previous = this.undoStack.pop();
    if (previous) this.redoStack.push(snapshot(current));
    return previous;
  }

  redo(current: Todo[]): Snapshot | undefined {
    const next = this.redoStack.pop();
    if (next) this.undoStack.push(snapshot(current));
    return next;
  }

  toJSON(): { undo: Snapshot[]; redo: Snapshot[] } {
    return { undo: this.undoStack.map(snapshot), redo: this.redoStack.map(snapshot) };
  }
}
