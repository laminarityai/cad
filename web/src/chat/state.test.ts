import { describe, expect, it } from "vitest";
import type { Event } from "@/api/types";
import { runningRun } from "@/test/fakes";
import { chatReducer, chatStart, type ChatAction, type ChatState } from "./state";

const play = (state: ChatState, events: Event[], from = 1): ChatState =>
  events.reduce((held, event, at) => chatReducer(held, { type: "event", seq: from + at, event } satisfies ChatAction), state);

const call = (id: string, name: string): Event => ({ kind: "tool_call", call_id: id, name, input: {} });
const result = (id: string, text: string, isError = false): Event => ({ kind: "tool_result", call_id: id, text, is_error: isError });
const report = (reason: string): Event => ({ kind: "stop_report", run_id: "run_1", reason, report: "the server's report" });

describe("chatReducer", () => {
  it("merges a tool result into its call and follows the turn from the user's message to its end", () => {
    let state = play(chatStart("c1", null), [{ kind: "user", text: "make the wall 4 mm" }, call("a", "build_variant")]);
    expect(state.turn).toBe("running");
    state = play(state, [result("a", "{}"), { kind: "agent", text: "Done." }, { kind: "turn_ended" }], 3);
    expect(state.turn).toBe("idle");
    expect(state.lines.map((one) => one.kind)).toEqual(["user", "tool", "agent"]);
    expect(state.lines[1]).toMatchObject({ name: "build_variant", result: { text: "{}", isError: false } });
  });

  it("ignores an event it has seen, so a resumed stream adds nothing twice", () => {
    const once = play(chatStart("c1", null), [{ kind: "agent", text: "hi" }]);
    expect(chatReducer(once, { type: "event", seq: 1, event: { kind: "agent", text: "hi" } })).toBe(once);
  });

  it("reads a run from the auto tool's result and keeps Auto", () => {
    const state = play({ ...chatStart("c1", null), mode: "auto" }, [call("a", "auto_start"), result("a", JSON.stringify(runningRun(2)))]);
    expect(state.mode).toBe("auto");
    expect(state.run).toEqual({ runId: "run_1", status: "running", revisions: 2, settling: false });
  });

  it.each(["all_pass", "needs_person", "account_limit", "stopped_by_person"])(
    "moves Auto to Design when a run stops for %s",
    (reason) => {
      const state = play({ ...chatStart("c1", null), mode: "auto", run: { runId: "run_1", status: "running", revisions: 1, settling: false } }, [report(reason)]);
      expect(state.mode).toBe("design");
      expect(state.run).toMatchObject({ status: "stopped", reason });
    },
  );

  it("changes neither the mode nor the run for events a reload replays", () => {
    const saved = { mode: "design" as const, run: null, seen: 5 };
    const state = play(chatStart("c1", saved), [{ kind: "user", text: "go" }, call("a", "auto_start"), result("a", JSON.stringify(runningRun(1))), report("all_pass")]);
    expect(state.mode).toBe("design");
    expect(state.run).toBeNull();
    expect(state.lines).toHaveLength(3);
  });

  it("leaves a mode alone when a stop report arrives after the person left Auto", () => {
    const left = chatReducer(
      { ...chatStart("c1", null), mode: "auto", run: { runId: "run_1", status: "running", revisions: 1, settling: false } },
      { type: "mode", state: { conversation_id: "c1", mode: "plan", auto_run: null } },
    );
    expect(left.run).toMatchObject({ status: "stopped", reason: "stopped_by_person" });
    const late = play(left, [report("stopped_by_person")]);
    expect(late.mode).toBe("plan");
    expect(late.run).toBe(left.run);
  });
});
