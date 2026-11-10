import type { ReactNode } from "react";
import type { CardState } from "@/state/cards";
import { ScoreRow } from "./ScoreRow";
import { ghostsOf, pendingFrom, rowsOf, tally, type Row, type Rows } from "./rows";

const GROUP = "border-t border-border px-2.5 pb-0.5 pt-1.5 font-mono text-[10px] uppercase tracking-widest text-ink-3";

function Group({ title, rows, ghosts }: { title: string; rows: Row[]; ghosts: Record<string, string> }) {
  if (rows.length === 0) return null;
  return (
    <>
      <h4 className={GROUP}>{title}</h4>
      <ul>
        {rows.map((row) => (
          <ScoreRow key={row.key} row={row} ghost={ghosts[row.key]} />
        ))}
      </ul>
    </>
  );
}

function shown(card: CardState): Rows | null {
  if (card.snapshot) return rowsOf(card.snapshot);
  return card.previous ? pendingFrom(rowsOf(card.previous)) : null;
}

const CONNECTION = {
  connecting: "connecting",
  live: "live",
  reconnecting: "reconnecting",
  closed: "not live",
} as const;

export function Scorecard({ card, heading }: { card: CardState | undefined; heading: ReactNode }) {
  const rows = card ? shown(card) : null;
  const decided = rows ? (rows.requirements.length > 0 ? rows.requirements : rows.checks) : [];
  const counts = tally(decided);
  const snapshot = card?.snapshot ?? null;
  return (
    <section aria-label="Scorecard" className="border border-border bg-panel">
      <h3 className="flex items-baseline justify-between gap-2 border-b border-rule-2 px-2.5 py-1.5">
        <span className="font-mono text-[10.5px] uppercase tracking-wider text-ink-2">{heading}</span>
        {card ? (
          <span
            data-connection={card.connection}
            className="font-mono text-[10.5px] text-ink-3"
            aria-label={`updates ${CONNECTION[card.connection]}`}
          >
            {card.connection === "live" ? "● " : ""}
            {CONNECTION[card.connection]}
          </span>
        ) : null}
      </h3>
      {card?.refused ? <p className="px-2.5 py-2 text-xs text-fail">The server ended the stream: {card.refused}.</p> : null}
      {!rows ? (
        <p className="px-2.5 py-3 text-xs text-ink-2">Not scored yet. The card appears when the first check stores a result.</p>
      ) : (
        <>
          <p className="px-2.5 py-1.5 font-mono text-[11px] text-ink-2" data-summary>
            {counts.pass} pass · {counts.fail} fail · {counts.unknown} unknown · {counts.pending} pending
            {counts.unverified > 0 ? ` · ${String(counts.unverified)} not checked` : ""}
          </p>
          {snapshot?.basis.kind === "awaiting_confirmation" ? (
            <p className="px-2.5 pb-1.5 text-xs text-wait">No requirement is judged until you confirm them.</p>
          ) : null}
          <Group title="Requirements" rows={rows.requirements} ghosts={ghostsOf(card?.previous ?? null)} />
          <Group title="Checks" rows={rows.checks} ghosts={ghostsOf(card?.previous ?? null)} />
          {snapshot ? (
            <p className="border-t border-border px-2.5 py-1.5 font-mono text-[10.5px] text-ink-3">
              material {snapshot.material.key}
              {snapshot.research.length > 0 ? ` · ${String(snapshot.research.length)} value awaits research` : ""}
            </p>
          ) : null}
          {snapshot && snapshot.not_verified.length > 0 ? (
            <div className="border-t border-border px-2.5 py-1.5 text-xs text-ink-2">
              {snapshot.not_verified.map((one) => (
                <p key={one.requirement_id}>
                  {one.title}: {one.label}
                </p>
              ))}
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
