import { ManualClock, memoize } from "../src";

describe("memoize", () => {
  test("calls the function once per argument list", () => {
    let calls = 0;
    const add = memoize((a: number, b: number) => {
      calls++;
      return a + b;
    });
    expect(add(1, 2)).toBe(3);
    expect(add(1, 2)).toBe(3);
    expect(add(2, 1)).toBe(3);
    expect(calls).toBe(2);
  });

  test("respects capacity and ttl", () => {
    const clock = new ManualClock();
    let calls = 0;
    const square = memoize(
      (n: number) => {
        calls++;
        return n * n;
      },
      { capacity: 2, ttlMs: 50, clock },
    );
    square(1);
    square(2);
    square(3);
    square(1);
    expect(calls).toBe(4);
    clock.advance(50);
    square(1);
    expect(calls).toBe(5);
    expect(square.cache.size).toBe(1);
  });

  test("a custom key function", () => {
    let calls = 0;
    const byId = memoize(
      (user: { id: number; name: string }) => {
        calls++;
        return user.name.toUpperCase();
      },
      { key: (user) => String(user.id) },
    );
    expect(byId({ id: 1, name: "ana" })).toBe("ANA");
    expect(byId({ id: 1, name: "other" })).toBe("ANA");
    expect(calls).toBe(1);
  });

  test("errors are not cached", () => {
    let calls = 0;
    const flaky = memoize((n: number) => {
      calls++;
      if (calls === 1) throw new Error("boom");
      return n;
    });
    expect(() => flaky(1)).toThrow("boom");
    expect(flaky(1)).toBe(1);
    expect(flaky(1)).toBe(1);
    expect(calls).toBe(2);
  });

  test("undefined results are cached too", () => {
    let calls = 0;
    const nothing = memoize((_n: number): undefined => {
      calls++;
      return undefined;
    });
    nothing(1);
    nothing(1);
    expect(calls).toBe(1);
  });
});
