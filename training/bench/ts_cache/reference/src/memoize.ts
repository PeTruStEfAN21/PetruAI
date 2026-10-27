import { Clock } from "./clock";
import { LruCache } from "./lruCache";

export interface MemoizeOptions<A extends unknown[]> {
  capacity?: number;
  ttlMs?: number;
  clock?: Clock;
  key?: (...args: A) => string;
}

export type Memoized<A extends unknown[], R> = ((...args: A) => R) & { cache: LruCache<string, R> };

const DEFAULT_CAPACITY = 1000;

export function memoize<A extends unknown[], R>(fn: (...args: A) => R, options: MemoizeOptions<A> = {}): Memoized<A, R> {
  const cache = new LruCache<string, R>(options.capacity ?? DEFAULT_CAPACITY, {
    ttlMs: options.ttlMs,
    clock: options.clock,
  });
  const keyOf = options.key ?? ((...args: A) => JSON.stringify(args));
  const wrapped = (...args: A): R => {
    const key = keyOf(...args);
    if (cache.has(key)) return cache.get(key) as R;
    const result = fn(...args); // a throw leaves nothing in the cache
    cache.set(key, result);
    return result;
  };
  return Object.assign(wrapped, { cache });
}
