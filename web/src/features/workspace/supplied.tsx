import type { Scorecard } from "@/api/snapshot";
import type { SuppliedPart } from "@/api/types";
import { SUPPLIED_COLOUR } from "@/features/viewer/supplied";

const short = (sha256: string) => sha256.slice(0, 12);

function from(part: SuppliedPart): string {
  return part.origin.kind === "upload" ? part.origin.file_name : `option ${short(part.origin.variant_id)}`;
}

function copies(part: SuppliedPart): string {
  const n = part.placements.length;
  if (n === 0) return "read, not placed";
  return n === 1 ? "1 copy" : `${String(n)} copies`;
}

function Line(props: { part: string | null; name: string; side: string; who: string; detail: string; colour: string | null }) {
  return (
    <li data-part={props.part ?? "made"} className="flex items-start gap-2.5 border-b border-rule-2 px-4 py-2 last:border-b-0">
      <span
        aria-hidden
        className="mt-1 inline-block size-3 shrink-0 rounded-sm ring-1 ring-rule"
        style={props.colour ? { backgroundColor: props.colour } : undefined}
      />
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline justify-between gap-2">
          <span className="truncate text-[15px]">{props.name}</span>
          <span className="shrink-0 font-mono text-[13px] tabular-nums text-ink-2">{props.side}</span>
        </span>
        <span className="block text-[13px] text-ink-2">{props.who}</span>
        <span className="block truncate font-mono text-[12px] text-ink-3">{props.detail}</span>
      </span>
    </li>
  );
}

/** Which shape is whose, from the signed build record: the agent made the option's body, which the checks
 * grade, and placed each part the person supplied, which no check grades. */
export function SuppliedRows({ snapshot }: { snapshot: Scorecard }) {
  return (
    <>
      <h3 className="px-4 pb-1 pt-2 text-[13px] font-medium text-ink-3">Parts</h3>
      <ul aria-label="Parts">
        <Line part={null} name="This option" side="checked" who="made by the agent" detail={`BREP ${short(snapshot.brep_sha256)}`} colour={null} />
        {snapshot.supplied.map((one) => (
          <Line
            key={one.part_id}
            part={one.part_id}
            name={one.name}
            side={copies(one)}
            who="supplied by you, placed by the agent · not checked"
            detail={`${from(one)} · BREP ${short(one.brep_sha256)}`}
            colour={SUPPLIED_COLOUR}
          />
        ))}
      </ul>
    </>
  );
}
