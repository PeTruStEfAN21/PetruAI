# ts_todo

Built by the PetruAI team: Qwen3.6-35B-A3B leading, Qwen3.5-4B assisting, both run locally.

## Task

Build a command-line todo manager in TypeScript (Node, no runtime dependencies) under src/. The acceptance tests are tests/todoList.test.ts, tests/filter.test.ts and tests/cli.test.ts (jest through ts-jest); do not change them, package.json or tsconfig.json. `npm test` and `npx tsc --noEmit -p .` must both pass.

Modules and API (see the tests for exact shapes and messages):
- src/types.ts: `Todo` {id, title, done, tags, priority: "low"|"normal"|"high", due?: "YYYY-MM-DD"}.
- src/todoList.ts: `class TodoList` with add(title, {tags, priority, due}) (ids are the highest id + 1; titles trimmed; empty title -> Error "title must not be empty"; a bad date -> an error mentioning "due"), get, all (sorted by id), complete, reopen, rename, remove (unknown id -> Error "todo #<id> not found"), undo()/redo() returning whether anything changed, history capped at 50 steps, a new change clears redo, failed changes are not recorded; returned todos are copies; toJSON() and static fromJSON() keep the history.
- src/filter.ts: `parseFilter(query)` and `applyFilter(todos, filter)`: plain words match the title (case-insensitive, all must match), tag:x (all given tags), is:done / is:open, priority:low|normal|high, due:<DATE, due:>DATE, due:DATE, due:none. Unknown keys -> Error "unknown filter key: <key>".
- src/storage.ts: load and save the list (todos plus undo/redo history) as JSON {"version": 1, ...}, creating folders.
- src/cli.ts: `runCli(argv, file) -> {code, output: string[]}` with the commands add (title words, --tag repeatable, --priority, --due), list [filter], done, reopen, rename, rm, undo, redo. List lines look like "#2 [ ] Report !high #work #q4 due:2026-11-01" (priority shown only when not normal); no match -> "No todos.". Errors -> code 1 and "Error: <message>"; an unknown command -> code 2; no command -> code 2 with the usage line from the test. Undo works across invocations because the history is saved in the file.

## Result

- Acceptance tests: passed
- Time: 35 min as a team, 60 min for the 35B alone
- Pieces handed to the assistant: 2

## Who wrote what

| File | Written by |
|---|---|
| `.gitignore` | not recorded |
| `.petru/DECISIONS.md` | not recorded |
| `package-lock.json` | not recorded |
| `package.json` | given with the task |
| `src/cli.ts` | not recorded |
| `src/filter.ts` | not recorded |
| `src/storage.ts` | not recorded |
| `src/todoList.ts` | not recorded |
| `src/types.ts` | not recorded |
| `tests/cli.test.ts` | given with the task |
| `tests/filter.test.ts` | given with the task |
| `tests/todoList.test.ts` | given with the task |
| `tsconfig.json` | given with the task |

Who wrote the other files was not recorded: this run's conversation was summarised.
