import { TodoList } from "./todoList";
import { parseFilter, applyFilter } from "./filter";
import { load, save } from "./storage";

export interface CliResult {
  code: number;
  output: string[];
}

function formatTodo(todo: { id: number; title: string; done: boolean; tags: string[]; priority: "low" | "normal" | "high"; due?: string }): string {
  const status = todo.done ? "[x]" : "[ ]";
  let line = `#${todo.id} ${status} ${todo.title}`;
  if (todo.priority !== "normal") {
    line += ` !${todo.priority}`;
  }
  for (const tag of todo.tags) {
    line += ` #${tag}`;
  }
  if (todo.due) {
    line += ` due:${todo.due}`;
  }
  return line;
}

export function runCli(args: string[], filePath: string): CliResult {
  const list = load(filePath);
  const output: string[] = [];

  try {
    const cmd = args[0];

    switch (cmd) {
      case "add": {
        // Parse flags first, then collect remaining words as title
        const tags: string[] = [];
        let priority: "low" | "normal" | "high" | undefined;
        let due: string | undefined;
        const titleParts: string[] = [];
        let i = 1;
        while (i < args.length) {
          if (args[i] === "--tag" && i + 1 < args.length) {
            tags.push(args[i + 1]);
            i += 2;
          } else if (args[i] === "--priority" && i + 1 < args.length) {
            priority = args[i + 1] as "low" | "normal" | "high";
            i += 2;
          } else if (args[i] === "--due" && i + 1 < args.length) {
            due = args[i + 1];
            i += 2;
          } else {
            titleParts.push(args[i]);
            i++;
          }
        }
        const title = titleParts.join(" ");
        if (!title.trim()) {
          return { code: 1, output: ["Error: title must not be empty"] };
        }
        const todo = list.add(title.trim(), { tags, priority, due });
        output.push(`Added #${todo.id}: ${todo.title}`);
        save(list, filePath);
        return { code: 0, output };
      }

      case "list": {
        const query = args.slice(1).join(" ");
        let todos = list.all();
        if (query.trim()) {
          const filter = parseFilter(query);
          todos = applyFilter(todos, filter);
        }
        if (todos.length === 0) {
          output.push("No todos.");
        } else {
          for (const todo of todos) {
            output.push(formatTodo(todo));
          }
        }
        return { code: 0, output };
      }

      case "done": {
        const idStr = args[1];
        if (!idStr || isNaN(Number(idStr))) {
          return { code: 1, output: [`Error: invalid id: ${idStr ?? ""}`] };
        }
        const id = Number(idStr);
        list.complete(id);
        output.push(`Completed #${id}`);
        save(list, filePath);
        return { code: 0, output };
      }

      case "reopen": {
        const idStr = args[1];
        if (!idStr || isNaN(Number(idStr))) {
          return { code: 1, output: [`Error: invalid id: ${idStr ?? ""}`] };
        }
        const id = Number(idStr);
        list.reopen(id);
        output.push(`Reopened #${id}`);
        save(list, filePath);
        return { code: 0, output };
      }

      case "rename": {
        const idStr = args[1];
        if (!idStr || isNaN(Number(idStr))) {
          return { code: 1, output: [`Error: invalid id: ${idStr ?? ""}`] };
        }
        const id = Number(idStr);
        const newTitle = args.slice(2).join(" ");
        if (!newTitle.trim()) {
          return { code: 1, output: ["Error: title must not be empty"] };
        }
        list.rename(id, newTitle.trim());
        output.push(`Renamed #${id}`);
        save(list, filePath);
        return { code: 0, output };
      }

      case "rm": {
        const idStr = args[1];
        if (!idStr || isNaN(Number(idStr))) {
          return { code: 1, output: [`Error: invalid id: ${idStr ?? ""}`] };
        }
        const id = Number(idStr);
        list.remove(id);
        output.push(`Removed #${id}`);
        save(list, filePath);
        return { code: 0, output };
      }

      case "undo": {
        if (list.undo()) {
          output.push("Undone");
        } else {
          output.push("Nothing to undo");
        }
        save(list, filePath);
        return { code: 0, output };
      }

      case "redo": {
        if (list.redo()) {
          output.push("Redone");
        } else {
          output.push("Nothing to redo");
        }
        save(list, filePath);
        return { code: 0, output };
      }

      default:
        if (cmd) {
          return { code: 2, output: [`Error: unknown command: ${cmd}`] };
        }
        return { code: 2, output: ["Usage: todo <add|list|done|reopen|rename|rm|undo|redo> ..."] };
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { code: 1, output: [`Error: ${msg}`] };
  }
}
