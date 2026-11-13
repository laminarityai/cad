import { Loading } from "@/components/ui/busy";
import { cn } from "@/lib/utils";
import { reasonText, type RunView } from "./run";

export function RunStatus(props: { run: RunView | null; problem: string | null; onStop: () => void }) {
  const { run, problem, onStop } = props;
  const running = run?.status === "running";
  return (
    <>
      {problem !== null ? (
        <p role="alert" className="text-[14px] text-fail">
          {problem}
        </p>
      ) : null}
      {run === null ? null : (
        <section
          aria-label="Auto run"
          data-run={run.status}
          className={cn("flex flex-wrap items-center gap-3 rounded-xl border bg-panel-2 px-3.5 py-2.5", running ? "border-accent" : "border-rule")}
        >
          <div className="min-w-0 flex-1 basis-44">
            <h3 className="text-[13px] text-ink-3">Auto run</h3>
            {run.status === "running" ? (
              <Loading
                elapsed
                label={`Running · ${run.revisions === 0 ? "no revision settled yet" : `${String(run.revisions)} ${run.revisions === 1 ? "revision" : "revisions"} tried`}${run.settling ? " · waiting on checks" : ""}`}
              />
            ) : (
              <>
                <p role="status" className="text-[15px]">
                  Stopped · {reasonText(run.reason, run.agentChecked, run.described)}
                </p>
                {run.note !== "" ? <p className="pt-0.5 text-[14px] text-ink-2">{run.note}</p> : null}
              </>
            )}
          </div>
          {running ? (
            <button
              type="button"
              onClick={onStop}
              className="flex items-center gap-2 rounded-lg bg-stop px-4 py-2 text-[15px] font-semibold text-stop-ink outline-none focus-visible:ring-2 focus-visible:ring-ring max-[480px]:w-full max-[480px]:justify-center"
            >
              <span aria-hidden className="size-2.5 rounded-[2px] bg-current" />
              Stop
            </button>
          ) : null}
        </section>
      )}
    </>
  );
}
