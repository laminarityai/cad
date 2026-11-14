import type { Area } from "@/api/types";
import { cn } from "@/lib/utils";

/** The areas the build code coloured, each with its swatch and name. `greyed` says why the model is drawn
 * grey instead, such as a check's marks on its faces, and dims the list while it is. Rows are keyed by their first face,
 * because the host lets no face sit in two areas. Colour is how the model looks, so the list says nothing about whether the design is good. */
export function AreaList({ areas, greyed }: { areas: readonly Area[]; greyed: string | null }) {
  if (areas.length === 0) return null;
  return (
    <div data-areas className="rounded-md bg-panel/85 px-2.5 py-1.5 text-[13px] text-ink-2">
      <ul aria-label="Colours of the model" className={cn("space-y-1", greyed && "opacity-50")}>
        {areas.map((area) => (
          <li key={area.faces[0]} data-area={area.name} className="flex items-center gap-2">
            <span aria-hidden className="inline-block size-3 rounded-sm ring-1 ring-rule" style={{ backgroundColor: area.colour }} />
            <span className="truncate">{area.name}</span>
          </li>
        ))}
      </ul>
      {greyed ? <p className="mt-1 text-ink-3">{greyed}</p> : null}
    </div>
  );
}
