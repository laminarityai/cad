import type { Selection } from "./selection";
import { summaryOf } from "./selection";

const HINT = "Click a face or edge to point at it. Shift-click adds, double-click picks the whole part.";

/** What the canvas says about the selection: the readout of its measurements, then the hint. The status
 * region stays on the page while it is empty, so a screen reader hears each readout that appears in it. */
export function SelectionNote({ selection, readout }: { selection: Selection | null; readout: readonly string[] | null }) {
  return (
    <div className="pointer-events-none absolute bottom-3 left-3 z-30 flex max-w-[70%] flex-col items-start gap-1.5">
      <div role="status" data-readout aria-label="Measurements of the selection">
        {readout ? (
          <ul className="rounded-md bg-panel/85 px-2.5 py-1 text-[13px] leading-snug text-ink">
            {readout.map((line, at) => (
              <li key={line} className={at === readout.length - 1 ? "text-ink-3" : "tabular-nums"}>
                {line}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      <p data-pick-hint className="rounded-md bg-panel/85 px-2.5 py-1 text-[13px] text-ink-2">
        {selection ? `${summaryOf(selection)} selected · Esc clears` : HINT}
      </p>
    </div>
  );
}
