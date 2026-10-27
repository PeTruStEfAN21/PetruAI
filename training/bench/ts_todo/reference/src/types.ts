export type Priority = "low" | "normal" | "high";

export const PRIORITIES: readonly Priority[] = ["low", "normal", "high"];

export interface Todo {
  id: number;
  title: string;
  done: boolean;
  tags: string[];
  priority: Priority;
  due?: string; // YYYY-MM-DD
}

export interface AddOptions {
  tags?: string[];
  priority?: Priority;
  due?: string;
}

export const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

export function copyTodo(todo: Todo): Todo {
  return { ...todo, tags: [...todo.tags] };
}
