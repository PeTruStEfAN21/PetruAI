# Decizii

Deciziile utilizatorului sunt finale. Intrările noi se adaugă la sfârșit; cea mai recentă câștigă.

- 2026-10-28: For the `due:` filter with a date like `due:2026-11-01`, should it match todos that have exactly that due date AND also todos that have no due date? The test shows `due:2026-11-01` returns only [2] (which has that exact date), and `due:none` returns [1] (no due date). So `due:DATE` matches exact date only, correct? -> Keep the API exactly as the tests use it; one module per concern (types, history, todoList, filter, storage, format, cli) under src/.
- 2026-10-28: One module per concern: types, todoList, filter, storage, cli
- 2026-10-28: History capped at 50 steps, new changes clear redo, failed changes not recorded
- 2026-10-28: Returned todos are deep copies
- 2026-10-28: JSON format: {version: 1, todos: [...], history: [...], redoStack: [...]}
- 2026-10-28: plan confirmat: Build command-line todo manager in TypeScript (6 pași)
