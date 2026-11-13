import { describe, expect, it } from "vitest";
import type { Event } from "@/api/types";
import { runningRun, stoppedRun } from "@/test/fakes";
import { viewOf } from "@/features/auto/run";
import { chatReducer, chatStart, type ChatState } from "./state";
import { sinceOf, stalledOf, workingLabel, workingOf } from "./working";

const play = (events: Event[]): ChatState => events.reduce((held, event, at) => chatReducer(held, { type: "event", seq: at + 1, event }), chatStart("c1"));
const user: Event = { kind: "user", text: "a hook", selection: null };
const call = (id: string, name: string, input: Record<string, unknown> = {}): Event => ({ kind: "tool_call", call_id: id, name, input });
const done = (id: string): Event => ({ kind: "tool_result", call_id: id, text: "{}", is_error: false });
const ended: Event = { kind: "turn_ended" };

describe("workingOf", () => {
  it("is nothing before a turn and after it ends", () => {
    expect(workingOf(play([]), null)).toBeNull();
    expect(workingOf(play([user, { kind: "agent", text: "Done." }, ended]), null)).toBeNull();
  });

  it("is a turn while one runs, and the call that is running, which is the first open one", () => {
    expect(workingOf(play([user]), null)).toEqual({ kind: "turn", briefId: null });
    expect(workingOf(play([user, call("a", "build_variant"), call("b", "score_variant")]), null)).toEqual({ kind: "tool", name: "build_variant", briefId: null });
    expect(workingOf(play([user, call("a", "build_variant"), done("a")]), null)).toEqual({ kind: "turn", briefId: null });
  });

  it("is nothing while the stream reconnects, though the turn has not ended", () => {
    const dropped = chatReducer(play([user, call("a", "build_variant", { brief_id: "b2" })]), { type: "link", link: "reconnecting" });
    expect(workingOf(dropped, null)).toBeNull();
    expect(stalledOf(dropped)).toBe(true);
    expect(stalledOf(play([user, ended]))).toBe(false);
  });

  it("is on the brief the open call names, else the brief this turn last named, and an Auto tool's is the run's", () => {
    const run = viewOf(runningRun(1));
    expect(workingOf(play([user, call("a", "build_variant", { brief_id: "b2" })]), run)).toMatchObject({ briefId: "b2" });
    expect(workingOf(play([user, call("a", "build_variant", { brief_id: "b2" }), done("a")]), run)).toMatchObject({ briefId: "b2" });
    expect(workingOf(play([user, call("a", "propose_requirements", { brief_id: "b2" }), done("a"), call("b", "create_brief")]), run)).toMatchObject({ briefId: null });
    expect(workingOf(play([user, call("a", "auto_revise", { slot: 1 })]), run)).toMatchObject({ briefId: "b1" });
    expect(workingOf(play([user]), run)).toMatchObject({ briefId: null });
    expect(workingOf(play([user, call("a", "build_variant", { brief_id: "b2" }), done("a"), ended, user]), run)).toMatchObject({ briefId: null });
  });

  it("is nothing for a running Auto run between turns, since only a turn moves it on", () => {
    const idle = play([user, ended]);
    expect(workingOf(idle, viewOf(runningRun(1)))).toBeNull();
    expect(workingOf(idle, viewOf(stoppedRun("run_1", "all_pass", "done")))).toBeNull();
  });

  it("is nothing for a tool left open by a turn that failed", () => {
    expect(workingOf(play([user, call("a", "build_variant"), { kind: "turn_failed", message: "no key" }, ended]), null)).toBeNull();
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
