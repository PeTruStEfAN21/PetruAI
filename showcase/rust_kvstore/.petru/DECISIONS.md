# Decizii

Deciziile utilizatorului sunt finale. Intrările noi se adaugă la sfârșit; cea mai recentă câștigă.

- 2026-10-28: For the `INCR` command: when the value is not an integer, should the store value remain unchanged (as the test shows `"ERROR value is not an integer"` for `INCR v` where v="y", and the store still has "y" for v)? -> Keep the API exactly as the tests use it; modules error.rs, layers.rs, store.rs, snapshot.rs and shell.rs, re-exported from lib.rs.
- 2026-10-28: For `INCR` with a non-integer value: the test expects the store to keep the original non-integer value (e.g., "y" stays "y" after `INCR v`). Should INCR leave the store unchanged on error? -> No external crates; a BTreeMap for committed data and a stack of change maps (Some = set, None = delete) for transactions.
- 2026-10-28: For the `KEYS` command in the shell: should it return keys sorted alphabetically? -> Work test-first against the two test files and run run_checks until cargo test passes.
- 2026-10-28: Use BTreeMap<String, String> for committed data (sorted keys).
- 2026-10-28: Use Vec<Option<String>> for transaction change maps (Some(value) = set, None = delete).
- 2026-10-28: Transaction stack is Vec<Vec<Option<String>>> for nested transactions.
- 2026-10-28: Snapshot escaping: backslash -> \\, tab -> \t, newline -> \n (both directions).
- 2026-10-28: INCR leaves store unchanged on non-integer error.
- 2026-10-28: KEYS command returns keys sorted alphabetically.
- 2026-10-28: Modules: error.rs, layers.rs, store.rs, snapshot.rs, shell.rs, lib.rs
- 2026-10-28: plan confirmat: In-memory key-value store in Rust (6 pași)
