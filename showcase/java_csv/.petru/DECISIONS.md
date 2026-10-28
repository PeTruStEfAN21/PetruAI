# Decizii

Deciziile utilizatorului sunt finale. Intrările noi se adaugă la sfârșit; cea mai recentă câștigă.

- 2026-10-27: The test expects `Aggregate.sum("price")` to produce a column named `"sum_price"`, `Aggregate.avg("price")` → `"avg_price"`, `Aggregate.max("price")` → `"max_price"`. Should the aggregator name format always be `{prefix}_{column}`? -> Keep the API exactly as the tests use it; one class per file in package report.
- 2026-10-27: Each class in its own file under src/main/java/report/
- 2026-10-27: Java 21 standard library only (no external deps beyond JUnit 5 + AssertJ in test scope)
- 2026-10-27: Decimal formatting: HALF_UP rounding, at most 2 decimal places, no trailing zeros
- 2026-10-27: Numeric sort uses BigDecimal for exact decimal comparison
- 2026-10-27: groupBy preserves order of first appearance
- 2026-10-27: sortBy is stable (uses insertion order for equal keys)
- 2026-10-27: plan confirmat: CSV Reporting Library in Java 21 (8 pași)
