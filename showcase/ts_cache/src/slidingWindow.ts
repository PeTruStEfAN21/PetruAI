import { Clock, systemClock } from "./clock";

interface AcquireResult {
  allowed: boolean;
  remaining: number;
  retryAfterMs: number;
}

export class SlidingWindowLimiter {
  private readonly limit: number;
  private readonly windowMs: number;
  private readonly clock: Clock;
  private readonly windows: Map<string, number[]>;

  constructor(limit: number, windowMs: number, clock?: Clock) {
    this.limit = limit;
    this.windowMs = windowMs;
    this.clock = clock ?? systemClock;
    this.windows = new Map();
  }

  private prune(key: string): void {
    const timestamps = this.windows.get(key);
    if (!timestamps) return;
    const now = this.clock.now();
    const cutoff = now - this.windowMs;
    while (timestamps.length > 0 && timestamps[0] <= cutoff) {
      timestamps.shift();
    }
  }

  tryAcquire(key: string): AcquireResult {
    this.prune(key);
    const timestamps = this.windows.get(key) ?? [];
    this.windows.set(key, timestamps);

    if (timestamps.length < this.limit) {
      timestamps.push(this.clock.now());
      return {
        allowed: true,
        remaining: this.limit - timestamps.length,
        retryAfterMs: 0,
      };
    }

    const oldest = timestamps[0];
    const retryAfterMs = oldest + this.windowMs - this.clock.now();
    return {
      allowed: false,
      remaining: 0,
      retryAfterMs: Math.max(0, retryAfterMs),
    };
  }

  reset(key: string): void {
    this.windows.delete(key);
  }
}
