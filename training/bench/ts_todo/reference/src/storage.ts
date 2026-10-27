import * as fs from "fs";
import * as path from "path";
import { TodoList } from "./todoList";

export const FORMAT_VERSION = 1;

export function loadList(file: string): TodoList {
  if (!fs.existsSync(file)) return new TodoList();
  const data = JSON.parse(fs.readFileSync(file, "utf8"));
  if (data.version !== FORMAT_VERSION) throw new Error(`unsupported file version: ${data.version}`);
  return TodoList.fromJSON(data);
}

export function saveList(file: string, list: TodoList): void {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify({ version: FORMAT_VERSION, ...list.toJSON() }, null, 2));
  fs.renameSync(tmp, file);
}
