import { confirmUrl } from "@/api/confirmation";
import type { BriefView } from "@/api/types";
import { Button } from "@/components/ui/button";

/** The requirements the person has not answered yet, each beside the words of the brief it came from. */
export function WaitingPanel({ brief, projectId }: { brief: BriefView; projectId: string }) {
  const rows = brief.proposals
    .filter((one) => one.status === "proposed")
    .flatMap((one) => one.requirements);
  return (
    <section aria-label="Waiting on you" className="border border-border bg-panel">
      <h3 className="flex items-baseline justify-between border-b border-rule-2 px-2.5 py-1.5">
        <span className="font-mono text-[10.5px] uppercase tracking-wider text-ink-2">Waiting on you</span>
        <span className="font-mono text-[10.5px] text-ink-3">{rows.length}</span>
      </h3>
      {rows.length === 0 ? (
        <p className="px-2.5 py-2 font-mono text-xs text-ink-3">Nothing waits on you.</p>
      ) : (
        <div className="p-2.5">
          <ul>
            {rows.map((row) => {
              const { start, end } = row.requirement.origin;
              return (
                <li key={row.requirement.id} className="border-t border-rule-2 py-1.5 first:border-t-0 first:pt-0">
                  <span className="font-mono text-xs">{row.plain}</span>
                  <blockquote className="mt-0.5 text-[12.5px] text-ink-2">
                    <mark className="bg-wait-bg px-0.5 text-ink">{brief.text.slice(start, end)}</mark>
                  </blockquote>
                </li>
              );
            })}
          </ul>
          <Button asChild variant="default" className="mt-2.5 w-full">
            <a href={confirmUrl(projectId)}>Review and confirm</a>
          </Button>
        </div>
      )}
    </section>
  );
}
