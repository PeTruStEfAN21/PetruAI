export interface Clock {
  now(): number;
}

export const systemClock: Clock = {
  now(): number {
    return Date.now();
  },
};

export class ManualClock implements Clock {
  private _now: number;

  constructor(start: number = 0) {
    this._now = start;
  }

  now(): number {
    return this._now;
  }

  advance(ms: number): void {
    this._now += ms;
  }
}
