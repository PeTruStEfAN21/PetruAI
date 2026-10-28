import { Clock, systemClock } from "./clock";

export class TokenBucket {
  private readonly capacity: number;
  private readonly refillPerSecond: number;
  private readonly clock: Clock;
  private tokens: number;
  private lastRefill: number;

  constructor(capacity: number, refillPerSecond: number, clock?: Clock) {
    if (capacity <= 0) {
      throw new Error("capacity must be > 0");
    }
    if (refillPerSecond <= 0) {
      throw new Error("refillPerSecond must be > 0");
    }
    this.capacity = capacity;
    this.refillPerSecond = refillPerSecond;
    this.clock = clock ?? systemClock;
    this.tokens = capacity;
    this.lastRefill = this.clock.now();
  }

  private refill(): void {
    const now = this.clock.now();
    const elapsed = (now - this.lastRefill) / 1000;
    if (elapsed > 0) {
      this.tokens = Math.min(this.capacity, this.tokens + elapsed * this.refillPerSecond);
      this.lastRefill = now;
    }
  }

  tryRemove(n: number = 1): boolean {
    if (n < 0) {
      throw new Error("n must be >= 0");
    }
    this.refill();
    if (this.tokens >= n) {
      this.tokens -= n;
      return true;
    }
    return false;
  }

  available(): number {
    this.refill();
    return Math.floor(this.tokens);
  }

  msUntil(n: number): number {
    this.refill();
    if (this.tokens >= n) return 0;
    if (n > this.capacity) return Infinity;
    const needed = n - this.tokens;
    return Math.ceil((needed / this.refillPerSecond) * 1000);
  }
}
