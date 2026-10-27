import { ManualClock, SlidingWindowLimiter, TokenBucket } from "../src";

describe("TokenBucket", () => {
  test("starts full and refills over time", () => {
    const clock = new ManualClock();
    const bucket = new TokenBucket(5, 2, clock);
    expect(bucket.available()).toBe(5);
    expect(bucket.tryRemove(5)).toBe(true);
    expect(bucket.tryRemove()).toBe(false);
    clock.advance(499);
    expect(bucket.tryRemove()).toBe(false);
    clock.advance(1);
    expect(bucket.tryRemove()).toBe(true);
    clock.advance(10_000);
    expect(bucket.available()).toBe(5);
  });

  test("a failed removal takes nothing", () => {
    const clock = new ManualClock();
    const bucket = new TokenBucket(3, 1, clock);
    expect(bucket.tryRemove(4)).toBe(false);
    expect(bucket.available()).toBe(3);
  });

  test("msUntil tells how long to wait", () => {
    const clock = new ManualClock();
    const bucket = new TokenBucket(4, 4, clock);
    bucket.tryRemove(4);
    expect(bucket.msUntil(1)).toBe(250);
    expect(bucket.msUntil(2)).toBe(500);
    clock.advance(100);
    expect(bucket.msUntil(1)).toBe(150);
    expect(bucket.msUntil(0)).toBe(0);
    expect(bucket.msUntil(5)).toBe(Infinity);
  });

  test("validates its arguments", () => {
    expect(() => new TokenBucket(0, 1)).toThrow();
    expect(() => new TokenBucket(1, 0)).toThrow();
    expect(() => new TokenBucket(1, 1).tryRemove(-1)).toThrow();
  });
});

describe("SlidingWindowLimiter", () => {
  test("allows up to the limit per key within the window", () => {
    const clock = new ManualClock();
    const limiter = new SlidingWindowLimiter(2, 1000, clock);
    expect(limiter.tryAcquire("a")).toEqual({ allowed: true, remaining: 1, retryAfterMs: 0 });
    clock.advance(300);
    expect(limiter.tryAcquire("a")).toEqual({ allowed: true, remaining: 0, retryAfterMs: 0 });
    clock.advance(200);
    expect(limiter.tryAcquire("a")).toEqual({ allowed: false, remaining: 0, retryAfterMs: 500 });
    expect(limiter.tryAcquire("b").allowed).toBe(true);
  });

  test("old requests leave the window", () => {
    const clock = new ManualClock();
    const limiter = new SlidingWindowLimiter(2, 1000, clock);
    limiter.tryAcquire("a");
    clock.advance(600);
    limiter.tryAcquire("a");
    clock.advance(400);
    expect(limiter.tryAcquire("a")).toEqual({ allowed: true, remaining: 0, retryAfterMs: 0 });
    expect(limiter.tryAcquire("a")).toEqual({ allowed: false, remaining: 0, retryAfterMs: 600 });
  });

  test("rejected requests do not count", () => {
    const clock = new ManualClock();
    const limiter = new SlidingWindowLimiter(1, 100, clock);
    limiter.tryAcquire("k");
    for (let i = 0; i < 5; i++) limiter.tryAcquire("k");
    clock.advance(100);
    expect(limiter.tryAcquire("k").allowed).toBe(true);
  });

  test("reset forgets a key", () => {
    const clock = new ManualClock();
    const limiter = new SlidingWindowLimiter(1, 1000, clock);
    limiter.tryAcquire("k");
    limiter.reset("k");
    expect(limiter.tryAcquire("k").allowed).toBe(true);
  });
});
