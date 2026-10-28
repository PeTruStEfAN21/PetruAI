# Decizii

Deciziile utilizatorului sunt finale. Intrările noi se adaugă la sfârșit; cea mai recentă câștigă.

- 2026-10-28: The project has no src/ directory yet. Should I create src/lib.rs and the module files (error.rs, document.rs, parser.rs, value.rs, interpolate.rs, writer.rs) from scratch? -> Keep the API exactly as the tests use it; modules error.rs, document.rs, parser.rs, value.rs, interpolate.rs and writer.rs, re-exported from lib.rs.
- 2026-10-28: For the `interpolate` method: when resolving `${section.key}` references, should it look up the raw (non-interpolated) value from the other section, or should it recursively interpolate that value too? The test shows `logs = ${paths.data}/logs` resolving to `/srv/data/logs`, which means it interpolates the referenced value. -> No external crates; keep sections and keys in Vecs so the file order is preserved.
- 2026-10-28: For `get_list`: when the value is empty string, should it return an empty Vec (as the test shows)? And for comma-separated values with spaces like "a, b ,c", should each element be trimmed? -> Work test-first against tests/ini_test.rs and run run_checks until cargo test passes.
- 2026-10-28: For the `merge` method: when a key exists in both the original and the override, should it replace the value (as the test shows for `server.host`), and when a key only exists in the override, should it be appended at the end of the section's keys? -> Your choice; keep it simple and use only what is already installed.
- 2026-10-28: No external crates; only std library
- 2026-10-28: Sections and keys stored in Vec<(String, String)> to preserve file order
- 2026-10-28: Interpolation resolves referenced values recursively (interpolating the target value)
- 2026-10-28: Merge replaces existing keys and appends new ones
- 2026-10-28: Empty get_list value returns empty Vec
- 2026-10-28: get_list trims each comma-separated element
- 2026-10-28: plan confirmat: Build INI file library in Rust (8 pași)
