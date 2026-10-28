# ts_cache

Built by the PetruAI team: Qwen3.6-35B-A3B leading, Qwen3.5-4B assisting, both run locally.

## Task

Build a small caching and rate-limiting library in TypeScript (no runtime dependencies) under src/, exported from src/index.ts. The acceptance tests are tests/lruCache.test.ts, tests/limiters.test.ts and tests/memoize.test.ts (jest through ts-jest); do not change them, package.json or tsconfig.json. `npm test` and `npx tsc --noEmit -p .` must both pass.

Modules (one per class) and API:
- src/clock.ts: `Clock` {now(): ms}, `systemClock`, `ManualClock(start = 0)` with advance(ms). Every time-based class takes an optional clock.
- src/lruCache.ts: `LruCache<K, V>(capacity, {ttlMs?, clock?, onEvict?(key, value)})`: get (refreshes recency), peek (does not), has, set(key, value, ttlMs?) returning this, delete, clear, `size` getter, keys() most recent first, stats() {hits, misses, evictions}. Capacity < 1 throws. Expired entries are invisible and removed; expiry is not an eviction; onEvict is called only for capacity evictions.
- src/tokenBucket.ts: `TokenBucket(capacity, refillPerSecond, clock?)`, starts full, refills continuously: tryRemove(n = 1) (a failed removal takes nothing; negative throws), available() (whole tokens), msUntil(n) (0 if available now, Infinity above capacity).
- src/slidingWindow.ts: `SlidingWindowLimiter(limit, windowMs, clock?)`: tryAcquire(key) -> {allowed, remaining, retryAfterMs}; a request at time t stays in the window until t + windowMs; rejected requests are not counted; reset(key).
- src/memoize.ts: `memoize(fn, {capacity?, ttlMs?, clock?, key?})` -> a function with a `cache` property (an LruCache); the default key is JSON.stringify of the arguments; thrown errors are not cached, undefined results are.

## Result

- Acceptance tests: passed
- Time: 30 min as a team, 18 min for the 35B alone
- Pieces handed to the assistant: 2

## Who wrote what

| File | Written by |
|---|---|
| `.gitignore` | not recorded |
| `.petru/DECISIONS.md` | not recorded |
| `package-lock.json` | not recorded |
| `package.json` | given with the task |
| `src/clock.ts` | not recorded |
| `src/index.ts` | not recorded |
| `src/lruCache.ts` | not recorded |
| `src/memoize.ts` | not recorded |
| `src/slidingWindow.ts` | not recorded |
| `src/tokenBucket.ts` | not recorded |
| `tests/limiters.test.ts` | given with the task |
| `tests/lruCache.test.ts` | given with the task |
| `tests/memoize.test.ts` | given with the task |
| `tsconfig.json` | given with the task |

Who wrote the other files was not recorded: this run's conversation was summarised.
