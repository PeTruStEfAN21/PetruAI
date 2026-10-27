import { applyFilter, parseFilter } from "../src/filter";
import { Todo } from "../src/types";

const todos: Todo[] = [
  { id: 1, title: "Buy Milk", done: false, tags: ["home"], priority: "normal" },
  { id: 2, title: "Write report", done: true, tags: ["work"], priority: "high", due: "2026-11-01" },
  { id: 3, title: "Plan trip", done: false, tags: ["home", "fun"], priority: "low", due: "2026-12-24" },
  { id: 4, title: "Review milk budget", done: false, tags: ["work"], priority: "high", due: "2026-10-30" },
];

const ids = (query: string) => applyFilter(todos, parseFilter(query)).map((t) => t.id);

describe("filter", () => {
  test("empty query keeps everything", () => {
    expect(ids("")).toEqual([1, 2, 3, 4]);
  });

  test("words match the title, case-insensitive, all of them", () => {
    expect(ids("milk")).toEqual([1, 4]);
    expect(ids("MILK budget")).toEqual([4]);
  });

  test("tag, status and priority", () => {
    expect(ids("tag:home")).toEqual([1, 3]);
    expect(ids("tag:home tag:fun")).toEqual([3]);
    expect(ids("is:done")).toEqual([2]);
    expect(ids("is:open priority:high")).toEqual([4]);
  });

  test("due dates", () => {
    expect(ids("due:<2026-11-01")).toEqual([4]);
    expect(ids("due:>2026-11-01")).toEqual([3]);
    expect(ids("due:2026-11-01")).toEqual([2]);
    expect(ids("due:none")).toEqual([1]);
  });

  test("combined", () => {
    expect(ids("tag:work is:open milk")).toEqual([4]);
  });

  test("bad queries throw", () => {
    expect(() => parseFilter("color:red")).toThrow("unknown filter key: color");
    expect(() => parseFilter("is:maybe")).toThrow("is:");
    expect(() => parseFilter("priority:urgent")).toThrow("priority");
    expect(() => parseFilter("due:<soon")).toThrow("due");
  });
});
