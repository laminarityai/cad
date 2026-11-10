import type { Mode } from "@/api/types";
import { cn } from "@/lib/utils";
import { reasonText, type RunView } from "./run";

const WORD = "font-mono text-[10.5px] uppercase tracking-wider text-ink-2";

/** The Auto run: running with a Stop button, or stopped with the reason and the server's report.
 * It shows nothing until the conversation is in Auto mode or has had a run. */
export function RunStatus(props: { mode: Mode | null; run: RunView | null; onStop: () => void }) {
  const { mode, run, onStop } = props;
  if (run === null && mode !== "auto") return null;
  const running = run?.status === "running";
  return (
    <section
      aria-label="Auto run"
      data-run={run?.status ?? "none"}
      className={cn(
        "flex flex-wrap items-center gap-3 border border-border bg-panel px-3 py-2.5",
        running && "border-accent shadow-[inset_3px_0_0_var(--accent)]",
        run?.status === "stopped" && "shadow-[inset_3px_0_0_var(--ink-3)]",
      )}
    >
      <div className="min-w-0 flex-1 basis-52">
        <h3 className={WORD}>Auto run</h3>
        {run === null ? (
          <p className="font-mono text-[13px]">No run yet. Write what to build and Auto starts one.</p>
        ) : run.status === "running" ? (
          <p className="font-mono text-[13px]" role="status">
            Running · {run.revisions === 0 ? "no revision settled yet" : `${String(run.revisions)} ${run.revisions === 1 ? "revision" : "revisions"} tried`}
            {run.settling ? " · waiting on checks" : ""}
          </p>
        ) : (
          <>
            <p className="font-mono text-[13px]" role="status">
              Stopped · {reasonText(run.reason)}
            </p>
            {run.note !== "" ? <p className="pt-1 text-xs text-ink-2">{run.note}</p> : null}
            {run.report !== "" ? (
              <details className="pt-1 text-xs text-ink-2">
                <summary className="cursor-pointer">Report</summary>
                <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words pt-1 font-mono">{run.report}</pre>
              </details>
            ) : null}
          </>
        )}
      </div>
      {running ? (
        <button
          type="button"
          onClick={onStop}
          className="inline-flex items-center gap-2 bg-stop px-5 py-2.5 font-mono text-sm font-semibold tracking-wider text-stop-ink outline-none focus-visible:ring-2 focus-visible:ring-ring max-[480px]:w-full max-[480px]:justify-center"
        >
          <span aria-hidden className="size-2.5 bg-current" />
          Stop
        </button>
      ) : null}
    </section>
  );
}
