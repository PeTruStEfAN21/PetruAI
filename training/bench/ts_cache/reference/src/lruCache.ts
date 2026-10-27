import { Clock, systemClock } from "./clock";

export interface LruOptions<K, V> {
  ttlMs?: number;
  clock?: Clock;
  onEvict?: (key: K, value: V) => void;
}

export interface CacheStats {
  hits: number;
  misses: number;
  evictions: number;
}

interface Entry<V> {
  value: V;
  expiresAt: number;
}

/** A Map keeps insertion order: the first key is the least recently used one. */
export class LruCache<K, V> {
  private entries = new Map<K, Entry<V>>();
  private counters: CacheStats = { hits: 0, misses: 0, evictions: 0 };
  private readonly clock: Clock;

  constructor(
    private readonly capacity: number,
    private readonly options: LruOptions<K, V> = {},
  ) {
    if (!Number.isInteger(capacity) || capacity < 1) throw new Error("capacity must be a positive integer");
    this.clock = options.clock ?? systemClock;
  }

  get size(): number {
    this.purgeExpired();
    return this.entries.size;
  }

  get(key: K): V | undefined {
    const entry = this.live(key);
    if (!entry) {
      this.counters.misses++;
      return undefined;
    }
    this.counters.hits++;
    this.entries.delete(key);
    this.entries.set(key, entry);
    return entry.value;
  }

  peek(key: K): V | undefined {
    return this.live(key)?.value;
  }

  has(key: K): boolean {
    return this.live(key) !== undefined;
  }

  set(key: K, value: V, ttlMs: number | undefined = this.options.ttlMs): this {
    this.entries.delete(key);
    this.entries.set(key, { value, expiresAt: ttlMs === undefined ? Infinity : this.clock.now() + ttlMs });
    while (this.entries.size > this.capacity) {
      const [oldest, entry] = this.entries.entries().next().value as [K, Entry<V>];
      this.entries.delete(oldest);
      this.counters.evictions++;
      this.options.onEvict?.(oldest, entry.value);
    }
    return this;
  }

  delete(key: K): boolean {
    return this.entries.delete(key);
  }

  clear(): void {
    this.entries.clear();
  }

  /** Live keys, most recently used first. */
  keys(): K[] {
    this.purgeExpired();
    return [...this.entries.keys()].reverse();
  }

  stats(): CacheStats {
    return { ...this.counters };
  }

  private live(key: K): Entry<V> | undefined {
    const entry = this.entries.get(key);
    if (entry && entry.expiresAt <= this.clock.now()) {
      this.entries.delete(key); // expiry is not an eviction
      return undefined;
    }
    return entry;
  }

  private purgeExpired(): void {
    for (const key of [...this.entries.keys()]) this.live(key);
  }
}
