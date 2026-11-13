import type { AutoRun, StopReason } from "@/api/types";

export type RunView =
  | { runId: string; status: "running"; builds: number; briefId: string }
  | { runId: string; status: "stopped"; builds: number; reason: StopKind; agentChecked: number; described: number; note: string; report: string };

export type StopKind = StopReason["kind"];

export const AUTO_TOOLS: ReadonlySet<string> = new Set(["auto_start", "auto_revise", "auto_ask"]);

const STOP_KINDS: ReadonlySet<string> = new Set<StopKind>(["all_pass", "needs_person", "account_limit", "stopped_by_person"]);

export const isStopKind = (kind: string): kind is StopKind => STOP_KINDS.has(kind);

export function reasonText(kind: StopKind, agentChecked = 0, described = 0): string {
  switch (kind) {
    case "all_pass": {
      const apart = [
        ...(agentChecked > 0 ? [`${String(agentChecked)} on the agent's check`] : []),
        ...(described > 0 ? [`${String(described)} on a load case the agent described`] : []),
      ];
      return apart.length > 0 ? `every checked requirement passes, ${apart.join(", ")}` : "every checked requirement passes";
    }
    case "needs_person":
      return "it needs you";
    case "account_limit":
      return "the account limit halted it";
    case "stopped_by_person":
      return "you stopped it";
  }
}

export function viewOf(run: AutoRun): RunView {
  if (run.state.kind === "running") {
    return { runId: run.run_id, status: "running", builds: run.state.builds.length, briefId: run.state.start.brief_id };
  }
  const { reason } = run.state;
  return {
    runId: run.run_id,
    status: "stopped",
    builds: run.state.builds.length,
    reason: reason.kind,
    agentChecked: reason.kind === "all_pass" ? reason.agent_checked.length : 0,
    described: reason.kind === "all_pass" ? (reason.described?.length ?? 0) : 0,
    note: reason.kind === "needs_person" ? reason.note : "",
    report: run.state.report,
  };
}

export function autoRunOf(text: string): AutoRun | null {
  try {
    const found = JSON.parse(text) as Partial<AutoRun> | null;
    const kind = found?.state?.kind;
    return typeof found?.run_id === "string" && (kind === "running" || kind === "stopped") ? (found as AutoRun) : null;
  } catch {
    return null;
  }
}

export function stoppedBy(run: RunView): RunView {
  return run.status === "stopped"
    ? run
    : { runId: run.runId, status: "stopped", builds: run.builds, reason: "stopped_by_person", agentChecked: 0, described: 0, note: "", report: "You stopped the Auto run. Nothing more builds under it." };
}
