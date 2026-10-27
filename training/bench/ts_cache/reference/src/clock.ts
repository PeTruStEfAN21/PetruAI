export interface Clock {
  now(): number; // milliseconds
}

export const systemClock: Clock = { now: () => Date.now() };

/** A clock that only moves when told to, for tests and simulations. */
export class ManualClock implements Clock {
  constructor(private current = 0) {}

  now(): number {
    return this.current;
  }

  advance(ms: number): void {
    if (ms < 0) throw new Error("time only moves forward");
    this.current += ms;
  }
}
