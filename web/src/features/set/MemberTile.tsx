import { ViewerCanvas } from "@/features/viewer/ViewerCanvas";
import { useMesh } from "@/features/viewer/useMesh";
import { rowsOf, pendingFrom, type Row } from "@/features/scorecard/rows";
import type { MemberView } from "@/api/types";
import { cn } from "@/lib/utils";
import type { CardState } from "@/state/cards";

const SEGMENT: Record<string, string> = {
  pass: "bg-pass",
  fail: "bg-fail",
  unknown: "bg-unk",
  pending: "outline outline-1 -outline-offset-1 outline-dotted outline-ink-3 motion-safe:animate-[pulse-soft_1s_ease-in-out_infinite]",
  unverified: "bg-rule",
};

function segment(row: Row): string {
  return row.kind === "settled" ? row.verdict : row.kind;
}

function strip(card: CardState | undefined): Row[] {
  if (!card) return [];
  const rows = card.snapshot ? rowsOf(card.snapshot) : card.previous ? pendingFrom(rowsOf(card.previous)) : null;
  if (!rows) return [];
  return rows.requirements.length > 0 ? rows.requirements : rows.checks;
}

function Mesh({ variantId, slot }: { variantId: string; slot: number }) {
  const mesh = useMesh(variantId);
  if (mesh.status === "loading") return <p className="p-3 font-mono text-xs text-ink-3">Making the mesh…</p>;
  if (mesh.status === "failed") return <p className="p-3 font-mono text-xs text-fail">{mesh.reason}</p>;
  return <ViewerCanvas shapes={mesh.shapes} label={`Slot ${String(slot)} model`} />;
}

export function MemberTile(props: {
  member: MemberView;
  card: CardState | undefined;
  selected: boolean;
  onSelect: () => void;
}) {
  const { member, card, selected, onSelect } = props;
  const bars = strip(card);
  return (
    <article
      data-slot-tile={member.slot}
      aria-current={selected}
      className={cn(
        "flex min-h-0 flex-col border border-border bg-panel-2",
        selected && "outline outline-2 -outline-offset-2 outline-accent",
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={selected}
        className="flex flex-col gap-1.5 border-b border-rule-2 px-2.5 py-1.5 text-left"
      >
        <span className="flex items-baseline justify-between font-mono">
          <b className="text-[13px]">Slot {member.slot}</b>
          <span className="text-[10.5px] text-ink-3">revision {member.revision}</span>
        </span>
        <span className="flex h-[5px] gap-0.5" aria-hidden>
          {bars.length === 0 ? <i className="flex-1 bg-rule-2" /> : null}
          {bars.map((row) => (
            <i key={row.key} data-tone={segment(row)} className={cn("flex-1", SEGMENT[segment(row)])} />
          ))}
        </span>
      </button>
      <div className="relative min-h-0 flex-1 overflow-hidden">
        <Mesh variantId={member.variant_id} slot={member.slot} />
      </div>
    </article>
  );
}
