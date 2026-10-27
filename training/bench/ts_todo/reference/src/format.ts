import { Todo } from "./types";

export function formatTodo(todo: Todo): string {
  let line = `#${todo.id} [${todo.done ? "x" : " "}] ${todo.title}`;
  if (todo.priority !== "normal") line += ` !${todo.priority}`;
  for (const tag of todo.tags) line += ` #${tag}`;
  if (todo.due) line += ` due:${todo.due}`;
  return line;
}
