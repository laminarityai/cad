import { describe, expect, it } from "vitest";
import type { Event } from "@/api/types";
import { runningRun, stoppedRun } from "@/test/fakes";
import { viewOf } from "@/features/auto/run";
import { chatReducer, chatStart, type ChatState } from "./state";
import { sinceOf, workingLabel, workingOf } from "./working";

const play = (events: Event[]): ChatState => events.reduce((held, event, at) => chatReducer(held, { type: "event", seq: at + 1, event }), chatStart("c1"));
const user: Event = { kind: "user", text: "a hook", selection: null };
const call = (id: string, name: string, input: Record<string, unknown> = {}): Event => ({ kind: "tool_call", call_id: id, name, input });
const done = (id: string): Event => ({ kind: "tool_result", call_id: id, text: "{}", is_error: false });
const ended: Event = { kind: "turn_ended" };

describe("workingOf", () => {
  it("is nothing before a turn and after it ends", () => {
    expect(workingOf(play([]), null, null)).toBeNull();
    expect(workingOf(play([user, { kind: "agent", text: "Done." }, ended]), null, null)).toBeNull();
  });

  it("is a turn while one runs, and the call that is running, which is the first open one", () => {
    expect(workingOf(play([user]), null, null)).toEqual({ kind: "turn", briefId: null });
    expect(workingOf(play([user, call("a", "build_variant"), call("b", "score_variant")]), null, null)).toEqual({ kind: "tool", name: "build_variant", briefId: null });
    expect(workingOf(play([user, call("a", "build_variant"), done("a")]), null, null)).toEqual({ kind: "turn", briefId: null });
  });

  it("is on the open call's brief, else this turn's latest named brief, else the run's, else the conversation's", () => {
    expect(workingOf(play([user, call("a", "build_variant", { brief_id: "b2" })]), null, "b1")).toMatchObject({ briefId: "b2" });
    expect(workingOf(play([user, call("a", "build_variant", { brief_id: "b2" }), done("a")]), null, "b1")).toMatchObject({ briefId: "b2" });
    expect(workingOf(play([user, call("a", "build_variant", { brief_id: "b2" }), done("a"), ended, user]), null, "b1")).toMatchObject({ briefId: "b1" });
    expect(workingOf(play([user]), viewOf(runningRun(1)), null)).toMatchObject({ briefId: "b1" });
  });

  it("is nothing for a running Auto run between turns, since only a turn moves it on", () => {
    const idle = play([user, ended]);
    expect(workingOf(idle, viewOf(runningRun(1)), null)).toBeNull();
    expect(workingOf(idle, viewOf(stoppedRun("run_1", "all_pass", "done")), null)).toBeNull();
  });

  it("is the run's checks when the run waits on them between turns", () => {
    const idle = play([user, ended]);
    expect(workingOf(idle, viewOf({ ...runningRun(1), settling: true }), null)).toEqual({ kind: "checks", briefId: "b1" });
  });

  it("is nothing for a tool left open by a turn that failed", () => {
    expect(workingOf(play([user, call("a", "build_variant"), { kind: "turn_failed", message: "no key" }, ended]), null, null)).toBeNull();
  });

  it("names a known tool in plain words and any other as working", () => {
    expect(workingLabel({ kind: "tool", name: "score_variant", briefId: null })).toBe("Checking an option");
    expect(workingLabel({ kind: "tool", name: "list_materials", briefId: null })).toBe("Working");
  });
});

describe("sinceOf", () => {
  it("is the send time only for the turn that message started, and only while it runs", () => {
    const running = play([user]);
    expect(sinceOf(running, { seq: 1, at: 5 })).toBe(5);
    expect(sinceOf(running, { seq: 7, at: 5 })).toBeNull();
    expect(sinceOf(running, null)).toBeNull();
    expect(sinceOf(play([user, ended]), { seq: 1, at: 5 })).toBeNull();
  });
});
