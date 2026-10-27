import { Clock, systemClock } from "./clock";

/** `capacity` tokens at most, refilled continuously at `refillPerSecond`; starts full. */
export class TokenBucket {
  private tokens: number;
  private last: number;

  constructor(
    private readonly capacity: number,
    private readonly refillPerSecond: number,
    private readonly clock: Clock = systemClock,
  ) {
    if (capacity <= 0) throw new Error("capacity must be positive");
    if (refillPerSecond <= 0) throw new Error("refill rate must be positive");
    this.tokens = capacity;
    this.last = clock.now();
  }

  available(): number {
    this.refill();
    return Math.floor(this.tokens);
  }

  tryRemove(count = 1): boolean {
    if (count < 0) throw new Error("count must not be negative");
    this.refill();
    if (this.tokens < count) return false;
    this.tokens -= count;
    return true;
  }

  /** Milliseconds until `count` tokens are available; Infinity when more than the capacity. */
  msUntil(count: number): number {
    if (count > this.capacity) return Infinity;
    this.refill();
    const missing = count - this.tokens;
    return missing <= 0 ? 0 : Math.ceil((missing * 1000) / this.refillPerSecond - 1e-9); // float noise
  }

  private refill(): void {
    const now = this.clock.now();
    this.tokens = Math.min(this.capacity, this.tokens + ((now - this.last) * this.refillPerSecond) / 1000);
    this.last = now;
  }
}
