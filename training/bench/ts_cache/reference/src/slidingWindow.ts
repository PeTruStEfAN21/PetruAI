import { Clock, systemClock } from "./clock";

export interface Decision {
  allowed: boolean;
  remaining: number;
  retryAfterMs: number;
}

/** At most `limit` accepted requests per key in any `windowMs` interval (a log of accepted times). */
export class SlidingWindowLimiter {
  private log = new Map<string, number[]>();

  constructor(
    private readonly limit: number,
    private readonly windowMs: number,
    private readonly clock: Clock = systemClock,
  ) {
    if (limit < 1) throw new Error("limit must be at least 1");
    if (windowMs <= 0) throw new Error("window must be positive");
  }

  tryAcquire(key: string): Decision {
    const now = this.clock.now();
    const times = (this.log.get(key) ?? []).filter((t) => t > now - this.windowMs);
    this.log.set(key, times);
    if (times.length >= this.limit) {
      return { allowed: false, remaining: 0, retryAfterMs: times[0] + this.windowMs - now };
    }
    times.push(now);
    return { allowed: true, remaining: this.limit - times.length, retryAfterMs: 0 };
  }

  reset(key: string): void {
    this.log.delete(key);
  }
}
