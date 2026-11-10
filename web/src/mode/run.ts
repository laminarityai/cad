import type { AutoRun, StopReason } from "@/api/types";

export type RunView =
  | { runId: string; status: "running"; revisions: number; settling: boolean }
  | { runId: string; status: "stopped"; revisions: number; reason: StopKind; note: string; report: string };

export type StopKind = StopReason["kind"];

export const AUTO_TOOLS: ReadonlySet<string> = new Set(["auto_start", "auto_revise", "auto_ask"]);

const STOP_KINDS: ReadonlySet<string> = new Set<StopKind>(["all_pass", "needs_person", "account_limit", "stopped_by_person"]);

export const isStopKind = (kind: string): kind is StopKind => STOP_KINDS.has(kind);

/** What the status line says about why a run stopped. */
export function reasonText(kind: StopKind): string {
  switch (kind) {
    case "all_pass":
      return "every checked requirement passes";
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
    return { runId: run.run_id, status: "running", revisions: run.state.history.length, settling: run.settling };
  }
  const { reason } = run.state;
  return {
    runId: run.run_id,
    status: "stopped",
    revisions: run.state.history.length,
    reason: reason.kind,
    note: reason.kind === "needs_person" ? reason.note : "",
    report: run.state.report,
  };
}

/** The `AutoRun` an auto tool returned, or null for text that is not one. */
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
    : { runId: run.runId, status: "stopped", revisions: run.revisions, reason: "stopped_by_person", note: "", report: "You stopped the Auto run. Nothing more builds under it." };
}
