import { LruCache, ManualClock } from "../src";

describe("LruCache", () => {
  test("rejects a capacity below 1", () => {
    expect(() => new LruCache<string, number>(0)).toThrow("capacity");
  });

  test("get, set, has, delete, size", () => {
    const cache = new LruCache<string, number>(3);
    cache.set("a", 1).set("b", 2);
    expect(cache.get("a")).toBe(1);
    expect(cache.get("zz")).toBeUndefined();
    expect(cache.has("b")).toBe(true);
    expect(cache.size).toBe(2);
    expect(cache.delete("b")).toBe(true);
    expect(cache.delete("b")).toBe(false);
    expect(cache.size).toBe(1);
  });

  test("evicts the least recently used entry", () => {
    const evicted: Array<[string, number]> = [];
    const cache = new LruCache<string, number>(2, { onEvict: (k, v) => evicted.push([k, v]) });
    cache.set("a", 1);
    cache.set("b", 2);
    cache.get("a");
    cache.set("c", 3);
    expect(cache.has("b")).toBe(false);
    expect(cache.keys()).toEqual(["c", "a"]);
    expect(evicted).toEqual([["b", 2]]);
  });

  test("updating a key refreshes it without evicting", () => {
    const cache = new LruCache<string, number>(2);
    cache.set("a", 1);
    cache.set("b", 2);
    cache.set("a", 10);
    cache.set("c", 3);
    expect(cache.keys()).toEqual(["c", "a"]);
    expect(cache.get("a")).toBe(10);
  });

  test("peek does not change the order", () => {
    const cache = new LruCache<string, number>(2);
    cache.set("a", 1);
    cache.set("b", 2);
    expect(cache.peek("a")).toBe(1);
    cache.set("c", 3);
    expect(cache.has("a")).toBe(false);
  });

  test("entries expire after the ttl", () => {
    const clock = new ManualClock(1000);
    const cache = new LruCache<string, string>(5, { ttlMs: 100, clock });
    cache.set("a", "x");
    clock.advance(99);
    expect(cache.get("a")).toBe("x");
    clock.advance(1);
    expect(cache.get("a")).toBeUndefined();
    expect(cache.has("a")).toBe(false);
    expect(cache.size).toBe(0);
  });

  test("a per-entry ttl overrides the default", () => {
    const clock = new ManualClock();
    const cache = new LruCache<string, number>(5, { ttlMs: 1000, clock });
    cache.set("short", 1, 10);
    cache.set("long", 2);
    clock.advance(500);
    expect(cache.keys()).toEqual(["long"]);
  });

  test("stats count hits, misses and evictions", () => {
    const clock = new ManualClock();
    const cache = new LruCache<string, number>(1, { ttlMs: 10, clock });
    cache.set("a", 1);
    cache.get("a");
    cache.get("b");
    cache.set("b", 2);
    clock.advance(10);
    cache.get("b");
    expect(cache.stats()).toEqual({ hits: 1, misses: 2, evictions: 1 });
    cache.clear();
    expect(cache.size).toBe(0);
  });
});
