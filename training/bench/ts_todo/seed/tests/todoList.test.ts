import { TodoList } from "../src/todoList";

describe("TodoList", () => {
  test("adds todos with defaults and sequential ids", () => {
    const list = new TodoList();
    const a = list.add("Buy milk");
    const b = list.add("Write report", { tags: ["work"], priority: "high", due: "2026-11-02" });
    expect(a).toEqual({ id: 1, title: "Buy milk", done: false, tags: [], priority: "normal" });
    expect(b).toEqual({
      id: 2, title: "Write report", done: false, tags: ["work"], priority: "high", due: "2026-11-02",
    });
    expect(list.all().map((t) => t.id)).toEqual([1, 2]);
  });

  test("rejects empty titles and bad dates", () => {
    const list = new TodoList();
    expect(() => list.add("   ")).toThrow("title");
    expect(() => list.add("x", { due: "tomorrow" })).toThrow("due");
  });

  test("completes, reopens, renames and removes", () => {
    const list = new TodoList();
    list.add("a");
    list.add("b");
    list.complete(1);
    expect(list.get(1).done).toBe(true);
    list.reopen(1);
    expect(list.get(1).done).toBe(false);
    list.rename(2, "  bee ");
    expect(list.get(2).title).toBe("bee");
    list.remove(1);
    expect(list.all().map((t) => t.title)).toEqual(["bee"]);
    expect(list.add("c").id).toBe(3);
  });

  test("unknown ids throw not found", () => {
    const list = new TodoList();
    expect(() => list.get(7)).toThrow("todo #7 not found");
    expect(() => list.complete(7)).toThrow("not found");
    expect(() => list.remove(7)).toThrow("not found");
  });

  test("returned todos are copies", () => {
    const list = new TodoList();
    list.add("a", { tags: ["x"] });
    const copy = list.get(1);
    copy.title = "changed";
    copy.tags.push("y");
    expect(list.get(1)).toEqual({ id: 1, title: "a", done: false, tags: ["x"], priority: "normal" });
  });

  test("undo and redo every kind of change", () => {
    const list = new TodoList();
    list.add("a");
    list.add("b");
    list.complete(1);
    list.remove(2);
    expect(list.undo()).toBe(true);
    expect(list.all().map((t) => t.title)).toEqual(["a", "b"]);
    expect(list.undo()).toBe(true);
    expect(list.get(1).done).toBe(false);
    expect(list.redo()).toBe(true);
    expect(list.get(1).done).toBe(true);
    expect(list.undo()).toBe(true);
    expect(list.undo()).toBe(true);
    expect(list.undo()).toBe(true);
    expect(list.all()).toEqual([]);
    expect(list.undo()).toBe(false);
  });

  test("a new change clears redo", () => {
    const list = new TodoList();
    list.add("a");
    list.undo();
    list.add("b");
    expect(list.redo()).toBe(false);
    expect(list.all().map((t) => t.title)).toEqual(["b"]);
  });

  test("failed changes are not recorded", () => {
    const list = new TodoList();
    list.add("a");
    expect(() => list.complete(9)).toThrow();
    expect(list.undo()).toBe(true);
    expect(list.undo()).toBe(false);
  });

  test("history is capped at 50 steps", () => {
    const list = new TodoList();
    for (let i = 0; i < 60; i++) list.add(`t${i}`);
    let undone = 0;
    while (list.undo()) undone++;
    expect(undone).toBe(50);
    expect(list.all()).toHaveLength(10);
  });

  test("round-trips through JSON with its history", () => {
    const list = new TodoList();
    list.add("a");
    list.add("b");
    list.complete(2);
    const again = TodoList.fromJSON(JSON.parse(JSON.stringify(list.toJSON())));
    expect(again.all()).toEqual(list.all());
    expect(again.undo()).toBe(true);
    expect(again.get(2).done).toBe(false);
  });
});
