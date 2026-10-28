import { LruCache } from "./lruCache";
import { Clock, systemClock } from "./clock";

export interface MemoizeOptions {
  capacity?: number;
  ttlMs?: number;
  clock?: Clock;
  key?: (args: any) => string;
}

export function memoize<TArgs extends unknown[], R>(
  fn: (...args: TArgs) => R,
  options?: MemoizeOptions
): {
  (...args: TArgs): R;
  cache: LruCache<string, R>;
} {
  const {
    capacity,
    ttlMs,
    clock = systemClock,
    key = (...args: unknown[]) => JSON.stringify(args),
  } = options || {};

  const cache = new LruCache<string, R>(capacity || 100, {
    ttlMs,
    clock,
  });

  const memoized = function (...args: TArgs): R {
    const cacheKey = key(args);

    if (cache.has(cacheKey)) {
      return cache.get(cacheKey)!;
    }

    try {
      const result = fn(...args);
      cache.set(cacheKey, result);
      return result;
    } catch (error) {
      throw error;
    }
  };

  (memoized as any).cache = cache;
  return memoized as any;
}
