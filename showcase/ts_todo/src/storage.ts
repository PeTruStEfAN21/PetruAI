import * as fs from "fs";
import * as path from "path";
import { TodoListState } from "./types";
import { TodoList } from "./todoList";

export function load(filePath: string): TodoList {
  if (fs.existsSync(filePath)) {
    const raw = fs.readFileSync(filePath, "utf8");
    const state: TodoListState = JSON.parse(raw);
    return TodoList.fromJSON(state);
  }
  return new TodoList();
}

export function save(list: TodoList, filePath: string): void {
  const dir = path.dirname(filePath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  const raw = JSON.stringify(list.toJSON(), null, 2);
  fs.writeFileSync(filePath, raw, "utf8");
}
