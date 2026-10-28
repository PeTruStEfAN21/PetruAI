# java_csv

Built by the PetruAI team: Qwen3.6-35B-A3B leading, Qwen3.5-4B assisting, both run locally.

## Task

Build a CSV reporting library in Java 21 (standard library only) in package `report` under src/main/java/report/. The acceptance tests are in src/test/java/report/ReportTest.java (JUnit 5 + AssertJ); do not change them or pom.xml. `mvn -q test` must pass.

API (exact strings are in the tests):
- `CsvParser.parse(String) -> List<List<String>>`: RFC 4180 style, LF or CRLF line ends, a final line break adds no row, quoted fields with "" for a quote and line breaks inside quotes, empty fields kept. Errors are `CsvException` (a RuntimeException) with the line number: "line 2: unterminated quote" (the line where the quote opened), "line 1: unexpected character after quote".
- `Table` (immutable): Table.fromCsv(text) (the first row is the header; "empty input"; a row with the wrong field count -> "line 3: expected 3 fields, got 2"), columns(), rowCount(), row(i), get(row, column), column(name) (unknown -> IllegalArgumentException "unknown column: color"), where(column, Predicate<String>), sortBy(column, numeric, descending) (stable; numeric compares as decimals).
- `Aggregate.groupBy(table, keyColumn, Aggregator...)` -> a Table with the key column then one column per aggregator, groups in order of first appearance. Aggregators: Aggregate.count() ("count"), sum(c) ("sum_c"), avg(c) ("avg_c"), max(c) ("max_c"). Numbers are exact decimals printed with at most 2 decimals (HALF_UP) and no trailing zeros: 12.5, 4.25, 2.13. A non-number -> IllegalArgumentException "not a number in v: abc".
- `TextTable.render(table)`: columns padded to their widest cell and joined with " | ", a rule of dashes joined with "-+-" under the header; columns whose values are all numbers are right-aligned (header too), others left-aligned; no trailing spaces; lines joined with "\n".
- `CsvWriter.write(table)`: header and rows, LF, final newline; a field is quoted only if it has a comma, quote, line break or leading/trailing space.

Split the code into classes: CsvException, CsvParser, Numbers, Table, Aggregate, TextTable, CsvWriter.

## Result

- Acceptance tests: failed
- Time: 60 min as a team, 51 min for the 35B alone
- Pieces handed to the assistant: 0

## Who wrote what

| File | Written by |
|---|---|
| `.petru/DECISIONS.md` | lead |
| `pom.xml` | given with the task |
| `src/main/java/report/Aggregate.java` | lead |
| `src/main/java/report/CsvException.java` | lead |
| `src/main/java/report/CsvParser.java` | lead |
| `src/main/java/report/CsvWriter.java` | lead |
| `src/main/java/report/Numbers.java` | lead |
| `src/main/java/report/Table.java` | lead |
| `src/main/java/report/TextTable.java` | lead |
| `src/test/java/report/ReportTest.java` | given with the task |
