# rust_ini

Built by the PetruAI team: Qwen3.6-35B-A3B leading, Qwen3.5-4B assisting, both run locally.

## Task

Build an INI file library in Rust (edition 2021, no external crates) as the library crate `ini`. The acceptance tests are in tests/ini_test.rs; do not change them or Cargo.toml. `cargo test` must pass.

Public API (re-exported from src/lib.rs; exact messages are in the tests):
- `Ini::parse(&str) -> Result<Ini, ParseError>`. Lines are trimmed; blank lines and lines starting with ; or # are skipped; `[name]` opens a section (name trimmed; reopening a section adds to it); `key = value` splits at the first =. Keys before any section go to the global section "". An unquoted value ends at a ; or # that follows whitespace (so http://x/#a is kept); a value starting with " is quoted, with \" and \\ escapes.
- `ParseError { line, kind: ParseErrorKind }` with kinds MissingEquals, UnclosedSection, EmptyKey, DuplicateKey(String), UnterminatedQuote; Display "line 2: expected key = value", "line 1: unclosed section header", "line 2: empty key", "line 4: duplicate key k", "line 1: unterminated quote".
- sections() in file order (the global one only when it has keys), keys(section) in order, get(section, key) -> Option<&str>, set (replaces in place or appends, creating the section at the end), remove -> bool, merge(&other) (other's keys override or are appended).
- get_int, get_bool (true/false, yes/no, on/off, 1/0, any case), get_list (comma separated, trimmed, empty value = empty list) returning `Result<_, ValueError>`; ValueError::Missing {section, key} ("missing server.tls"), ValueError::Invalid {section, key, value, expected: "integer" | "boolean"} ("server.host: expected integer, got 'example.org'"), ValueError::Cycle(String) ("interpolation cycle at a.x").
- interpolated(section, key) -> Result<String, ValueError>: replaces ${key} (same section) and ${section.key} recursively; detects cycles.
- Display writes the file back: global keys first, then each section after one blank line, "key = value" lines, a value quoted when it has leading/trailing spaces, a ; or #, or starts with a quote. Ini derives PartialEq and Debug, so parse(to_string()) == the original.

Split the code into modules: error, document (the Ini type), parser, value (typed getters), interpolate, writer.

## Result

- Acceptance tests: passed
- Time: 47 min as a team, 16 min for the 35B alone
- Pieces handed to the assistant: 3

## Who wrote what

| File | Written by |
|---|---|
| `.gitignore` | not recorded |
| `.petru/DECISIONS.md` | not recorded |
| `Cargo.lock` | not recorded |
| `Cargo.toml` | given with the task |
| `src/document.rs` | not recorded |
| `src/error.rs` | not recorded |
| `src/interpolate.rs` | not recorded |
| `src/lib.rs` | not recorded |
| `src/parser.rs` | not recorded |
| `src/value.rs` | not recorded |
| `src/writer.rs` | not recorded |
| `tests/ini_test.rs` | given with the task |

Who wrote the other files was not recorded: this run's conversation was summarised.
