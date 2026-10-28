# Decizii

Deciziile utilizatorului sunt finale. Intrările noi se adaugă la sfârșit; cea mai recentă câștigă.

- 2026-10-28: I see the tests import from "../src" (the index). Should src/index.ts re-export everything, or should each module be its own file? -> Keep the API exactly as the tests use it; one module per class under src/ and re-export everything from src/index.ts.
- 2026-10-28: Each module is a separate file under src/; src/index.ts re-exports everything
- 2026-10-28: ManualClock starts at 0 by default
- 2026-10-28: TokenBucket starts full, refills continuously, capacity and refillPerSecond must be > 0
- 2026-10-28: SlidingWindowLimiter tracks per-key timestamps, rejected requests don't count
- 2026-10-28: memoize default key is JSON.stringify of args; thrown errors are not cached, undefined results are
- 2026-10-28: plan confirmat: Build caching and rate-limiting library in TypeScript (7 pași)
