import { applyFilter, parseFilter } from "./filter";
import { formatTodo } from "./format";
import { loadList, saveList } from "./storage";
import { TodoList } from "./todoList";
import { AddOptions, Priority } from "./types";

export interface CliResult {
  code: number;
  output: string[];
}

const USAGE = "Usage: todo <add|list|done|reopen|rename|rm|undo|redo> ...";

class UsageError extends Error {}

function parseId(text: string | undefined): number {
  if (text === undefined || !/^\d+$/.test(text)) throw new Error(`invalid id: ${text ?? ""}`);
  return Number(text);
}

function parseAdd(args: string[]): { title: string; options: AddOptions } {
  const words: string[] = [];
  const options: AddOptions = {};
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === "--tag") (options.tags ??= []).push(args[++i]);
    else if (arg === "--priority") options.priority = args[++i] as Priority;
    else if (arg === "--due") options.due = args[++i];
    else words.push(arg);
  }
  return { title: words.join(" "), options };
}

type Command = (list: TodoList, args: string[]) => { output: string[]; changed: boolean };

const COMMANDS: Record<string, Command> = {
  add: (list, args) => {
    const { title, options } = parseAdd(args);
    const todo = list.add(title, options);
    return { output: [`Added #${todo.id}: ${todo.title}`], changed: true };
  },
  list: (list, args) => {
    const found = applyFilter(list.all(), parseFilter(args.join(" ")));
    return { output: found.length ? found.map(formatTodo) : ["No todos."], changed: false };
  },
  done: (list, args) => {
    const id = parseId(args[0]);
    list.complete(id);
    return { output: [`Completed #${id}`], changed: true };
  },
  reopen: (list, args) => {
    const id = parseId(args[0]);
    list.reopen(id);
    return { output: [`Reopened #${id}`], changed: true };
  },
  rename: (list, args) => {
    const id = parseId(args[0]);
    list.rename(id, args.slice(1).join(" "));
    return { output: [`Renamed #${id}`], changed: true };
  },
  rm: (list, args) => {
    const id = parseId(args[0]);
    list.remove(id);
    return { output: [`Removed #${id}`], changed: true };
  },
  undo: (list) => (list.undo() ? { output: ["Undone"], changed: true } : { output: ["Nothing to undo"], changed: false }),
  redo: (list) => (list.redo() ? { output: ["Redone"], changed: true } : { output: ["Nothing to redo"], changed: false }),
};

export function runCli(argv: string[], file: string): CliResult {
  const [name, ...args] = argv;
  try {
    if (name === undefined) throw new UsageError(USAGE);
    const command = COMMANDS[name];
    if (!command) throw new UsageError(`Error: unknown command: ${name}`);
    const list = loadList(file);
    const { output, changed } = command(list, args);
    if (changed) saveList(file, list);
    return { code: 0, output };
  } catch (err) {
    if (err instanceof UsageError) return { code: 2, output: [err.message] };
    return { code: 1, output: [`Error: ${(err as Error).message}`] };
  }
}
