import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { runCli } from "../src/cli";

let dir: string;
let file: string;

beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), "todo-"));
  file = path.join(dir, "nested", "todos.json");
});

afterEach(() => {
  fs.rmSync(dir, { recursive: true, force: true });
});

const run = (...args: string[]) => runCli(args, file);

describe("cli", () => {
  test("add and list", () => {
    expect(run("add", "Buy milk")).toEqual({ code: 0, output: ["Added #1: Buy milk"] });
    expect(run("add", "Report", "--tag", "work", "--tag", "q4", "--priority", "high", "--due", "2026-11-01"))
      .toEqual({ code: 0, output: ["Added #2: Report"] });
    expect(run("list")).toEqual({
      code: 0,
      output: ["#1 [ ] Buy milk", "#2 [ ] Report !high #work #q4 due:2026-11-01"],
    });
  });

  test("state persists in the file", () => {
    run("add", "a");
    const data = JSON.parse(fs.readFileSync(file, "utf8"));
    expect(data.version).toBe(1);
    expect(data.todos).toHaveLength(1);
  });

  test("done, undo, redo across invocations", () => {
    run("add", "a");
    expect(run("done", "1")).toEqual({ code: 0, output: ["Completed #1"] });
    expect(run("list").output).toEqual(["#1 [x] a"]);
    expect(run("undo")).toEqual({ code: 0, output: ["Undone"] });
    expect(run("list").output).toEqual(["#1 [ ] a"]);
    expect(run("redo")).toEqual({ code: 0, output: ["Redone"] });
    expect(run("undo").code).toBe(0);
    expect(run("undo").code).toBe(0);
    expect(run("undo")).toEqual({ code: 0, output: ["Nothing to undo"] });
    expect(run("redo").output).toEqual(["Redone"]);
  });

  test("list with a filter", () => {
    run("add", "Buy milk", "--tag", "home");
    run("add", "Report", "--tag", "work");
    expect(run("list", "tag:work").output).toEqual(["#2 [ ] Report #work"]);
    expect(run("list", "is:done").output).toEqual(["No todos."]);
  });

  test("rm, reopen and rename", () => {
    run("add", "a");
    run("add", "b");
    expect(run("rm", "1").output).toEqual(["Removed #1"]);
    expect(run("rename", "2", "bee").output).toEqual(["Renamed #2"]);
    run("done", "2");
    expect(run("reopen", "2").output).toEqual(["Reopened #2"]);
    expect(run("list").output).toEqual(["#2 [ ] bee"]);
  });

  test("errors", () => {
    expect(run("done", "9")).toEqual({ code: 1, output: ["Error: todo #9 not found"] });
    expect(run("done", "x")).toEqual({ code: 1, output: ["Error: invalid id: x"] });
    expect(run("add")).toEqual({ code: 1, output: ["Error: title must not be empty"] });
    expect(run("list", "color:red")).toEqual({ code: 1, output: ["Error: unknown filter key: color"] });
    expect(run("fly")).toEqual({ code: 2, output: ["Error: unknown command: fly"] });
    expect(run()).toEqual({ code: 2, output: ["Usage: todo <add|list|done|reopen|rename|rm|undo|redo> ..."] });
  });
});
