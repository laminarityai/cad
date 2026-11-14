import { describe, expect, it } from "vitest";
import type { AutoRun } from "@/api/types";
import { stoppedRun } from "@/test/fakes";
import { UNFINISHED, reasonText, viewOf } from "./run";

function allPassOn(agentChecked: string[]): AutoRun {
  const run = stoppedRun("run_1", "all_pass", "Every checked requirement passes.");
  if (run.state.kind !== "stopped" || run.state.reason.kind !== "all_pass") throw new Error("the fake run should have stopped on all pass");
  return { ...run, state: { ...run.state, reason: { ...run.state.reason, agent_checked: agentChecked } } };
}

describe("an Auto run that stops with every requirement passing", () => {
  it("says how many passes rest on the agent's check", () => {
    const view = viewOf(allPassOn(["r2"]));
    if (view.status !== "stopped") throw new Error("the run should read as stopped");
    expect(view.agentChecked).toBe(1);
    expect(reasonText(view.reason, view.agentChecked)).toBe("every checked requirement passes, 1 on the agent's check");
  });

  it("says how many passes rest on a load case the agent described", () => {
    const run = allPassOn([]);
    if (run.state.kind !== "stopped" || run.state.reason.kind !== "all_pass") throw new Error("the fake run should have stopped on all pass");
    const view = viewOf({ ...run, state: { ...run.state, reason: { ...run.state.reason, described: ["r4"] } } });
    if (view.status !== "stopped") throw new Error("the run should read as stopped");
    expect(reasonText(view.reason, view.agentChecked, view.described)).toBe("every checked requirement passes, 1 on a load case the agent described");
  });

  it("says nothing of the agent's check when none was counted", () => {
    const view = viewOf(allPassOn([]));
    if (view.status !== "stopped") throw new Error("the run should read as stopped");
    expect(reasonText(view.reason, view.agentChecked)).toBe("every checked requirement passes");
  });
});

describe("an Auto run the person stopped", () => {
  it("says a build that was still running is not counted", () => {
    const run = stoppedRun("run_1", "stopped_by_person", "The person stopped the run.");
    if (run.state.kind !== "stopped" || run.state.reason.kind !== "stopped_by_person") throw new Error("the fake run should have been stopped by the person");
    const view = viewOf({ ...run, state: { ...run.state, reason: { ...run.state.reason, unfinished: true } } });
    if (view.status !== "stopped") throw new Error("the run should read as stopped");
    expect(view.note).toBe(UNFINISHED);
    expect(viewOf(run)).toMatchObject({ note: "" });
  });
});
