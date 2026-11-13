import { describe, expect, it } from "vitest";
import type { Event } from "@/api/types";
import { runningRun, stoppedRun } from "@/test/fakes";
import { viewOf } from "@/features/auto/run";
import { chatReducer, chatStart, type ChatState } from "./state";
import { workingLabel, workingOf } from "./working";

const play = (events: Event[]): ChatState => events.reduce((held, event, at) => chatReducer(held, { type: "event", seq: at + 1, event }), chatStart("c1"));
const user: Event = { kind: "user", text: "a hook", selection: null };
const call = (id: string, name: string): Event => ({ kind: "tool_call", call_id: id, name, input: {} });
const done = (id: string): Event => ({ kind: "tool_result", call_id: id, text: "{}", is_error: false });

describe("workingOf", () => {
  it("is nothing before a turn and after it ends", () => {
    expect(workingOf(play([]), null)).toBeNull();
    expect(workingOf(play([user, { kind: "agent", text: "Done." }, { kind: "turn_ended" }]), null)).toBeNull();
  });

  it("is a turn while one runs, and the tool that has not answered yet", () => {
    expect(workingOf(play([user]), null)).toEqual({ kind: "turn" });
    expect(workingOf(play([user, call("a", "build_variant")]), null)).toEqual({ kind: "tool", name: "build_variant" });
    expect(workingOf(play([user, call("a", "build_variant"), done("a")]), null)).toEqual({ kind: "turn" });
  });

  it("is a running Auto run between turns, and not a stopped one", () => {
    const idle = play([user, { kind: "turn_ended" }]);
    expect(workingOf(idle, viewOf(runningRun(1)))).toEqual({ kind: "auto" });
    expect(workingOf(idle, viewOf(stoppedRun("run_1", "all_pass", "done")))).toBeNull();
  });

  it("is nothing for a tool left open by a turn that failed", () => {
    expect(workingOf(play([user, call("a", "build_variant"), { kind: "turn_failed", message: "no key" }, { kind: "turn_ended" }]), null)).toBeNull();
  });

  it("names a known tool in plain words and any other as working", () => {
    expect(workingLabel({ kind: "tool", name: "score_variant" })).toBe("Checking an option");
    expect(workingLabel({ kind: "tool", name: "list_materials" })).toBe("Working");
  });
});
