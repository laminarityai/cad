import { Link } from "react-router-dom";
import { confirmUrl } from "@/api/confirmation";
import type { WaitingView } from "@/api/types";
import { Button } from "@/components/ui/button";

/** Everything in the project the person has not answered yet, as its confirmation page lists it,
 * each under the brief it belongs to. */
export function WaitingPanel({ waiting, briefId, projectId }: { waiting: WaitingView; briefId: string; projectId: string }) {
  const count = waiting.items.reduce((sum, item) => sum + item.rows.length, 0);
  return (
    <section aria-label="Waiting on you" className="border border-border bg-panel">
      <h3 className="flex items-baseline justify-between border-b border-rule-2 px-2.5 py-1.5">
        <span className="font-mono text-[10.5px] uppercase tracking-wider text-ink-2">Waiting on you</span>
        <span className="font-mono text-[10.5px] text-ink-3">{count}</span>
      </h3>
      {waiting.items.length === 0 ? (
        <p className="px-2.5 py-2 font-mono text-xs text-ink-3">Nothing waits on you.</p>
      ) : (
        <div className="p-2.5">
          {waiting.items.map((item, index) => (
            <article key={`${item.kind}:${String(index)}`} aria-label={item.title} className="border-t border-rule-2 pt-2 first:border-t-0 first:pt-0 mt-2 first:mt-0">
              <p className="truncate text-[12.5px] text-ink-2" title={item.brief_text}>
                {item.brief_id === briefId ? (
                  <span className="font-mono text-[10.5px] uppercase tracking-wider text-ink-3">This brief</span>
                ) : (
                  <Link to={`/projects/${encodeURIComponent(projectId)}/briefs/${encodeURIComponent(item.brief_id)}`} className="font-mono text-[10.5px] text-ink-2 underline">
                    <span className="uppercase tracking-wider">Brief</span> {item.brief_id}
                  </Link>
                )}{" "}
                <q className="text-ink">{item.brief_text}</q>
              </p>
              <ul className="mt-1">
                {item.rows.map((row, at) => (
                  <li key={at} className="py-1">
                    <span className="font-mono text-xs">{row.headline}</span>
                    <blockquote className="mt-0.5 text-[12.5px] text-ink-2">
                      <mark className="bg-wait-bg px-0.5 text-ink">{row.quote}</mark>
                    </blockquote>
                  </li>
                ))}
              </ul>
            </article>
          ))}
          <Button asChild variant="default" className="mt-2.5 w-full">
            <a href={confirmUrl(projectId)}>Review and confirm</a>
          </Button>
        </div>
      )}
    </section>
  );
}
