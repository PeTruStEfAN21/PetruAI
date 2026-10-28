import { Clock, systemClock } from "./clock";

interface LruCacheOptions<K, V> {
  ttlMs?: number;
  clock?: Clock;
  onEvict?: (key: K, value: V) => void;
}

interface Stats {
  hits: number;
  misses: number;
  evictions: number;
}

export class LruCache<K, V> {
  private readonly data: Map<K, { value: V; expiry: number | null }>;
  private readonly order: K[];
  private readonly capacity: number;
  private readonly ttlMs: number | undefined;
  private readonly clock: Clock;
  private readonly onEvict?: (key: K, value: V) => void;
  private hits = 0;
  private misses = 0;
  private evictions = 0;

  constructor(capacity: number, options?: LruCacheOptions<K, V>) {
    if (capacity < 1) {
      throw new Error("capacity must be >= 1");
    }
    this.capacity = capacity;
    this.ttlMs = options?.ttlMs;
    this.clock = options?.clock ?? systemClock;
    this.onEvict = options?.onEvict;
    this.data = new Map();
    this.order = [];
  }

  private evictOne(): void {
    if (this.order.length === 0) return;
    const key = this.order.pop()!;
    const entry = this.data.get(key);
    if (entry) {
      this.data.delete(key);
      this.evictions++;
      this.onEvict?.(key, entry.value);
    }
  }

  private removeExpired(): void {
    const now = this.clock.now();
    for (const [key, entry] of this.data) {
      if (entry.expiry !== null && now >= entry.expiry) {
        this.data.delete(key);
        const idx = this.order.indexOf(key);
        if (idx !== -1) this.order.splice(idx, 1);
      }
    }
  }

  private touch(key: K): void {
    const idx = this.order.indexOf(key);
    if (idx !== -1) {
      this.order.splice(idx, 1);
    }
    this.order.unshift(key);
  }

  get(key: K): V | undefined {
    this.removeExpired();
    const entry = this.data.get(key);
    if (entry === undefined) {
      this.misses++;
      return undefined;
    }
    this.hits++;
    this.touch(key);
    return entry.value;
  }

  peek(key: K): V | undefined {
    this.removeExpired();
    const entry = this.data.get(key);
    if (entry === undefined) return undefined;
    return entry.value;
  }

  has(key: K): boolean {
    this.removeExpired();
    return this.data.has(key);
  }

  set(key: K, value: V, ttlMs?: number): this {
    const expiry = ttlMs !== undefined ? this.clock.now() + ttlMs : (this.ttlMs !== undefined ? this.clock.now() + this.ttlMs : null);

    if (this.data.has(key)) {
      this.data.set(key, { value, expiry });
      this.touch(key);
      return this;
    }

    if (this.data.size >= this.capacity) {
      this.evictOne();
    }

    this.data.set(key, { value, expiry });
    this.order.unshift(key);
    return this;
  }

  delete(key: K): boolean {
    const entry = this.data.get(key);
    if (entry === undefined) return false;
    this.data.delete(key);
    const idx = this.order.indexOf(key);
    if (idx !== -1) this.order.splice(idx, 1);
    return true;
  }

  clear(): void {
    this.data.clear();
    this.order.length = 0;
  }

  get size(): number {
    return this.data.size;
  }

  keys(): K[] {
    this.removeExpired();
    return [...this.order];
  }

  stats(): Stats {
    return { hits: this.hits, misses: this.misses, evictions: this.evictions };
  }
}
