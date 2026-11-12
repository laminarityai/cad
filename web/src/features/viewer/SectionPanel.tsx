import { Slider } from "@/components/ui/slider";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { AXES, type Axis } from "./dimensions";
import type { Shapes } from "./engine";
import { positionLabel, rangeOf, stepOf, type Cut } from "./section";

const isAxis = (value: unknown): value is Axis => AXES.some((axis) => axis === value);

/** The controls for the section: which axis the plane stands square to, and where it sits along it, from one
 * end of the part's box to the other. The position is the control's setting in mm, not a size of the part. */
export function SectionPanel({ cut, at, bb, onChange }: { cut: Cut; at: number; bb: Shapes["bb"]; onChange: (next: Cut) => void }) {
  const range = rangeOf(bb, cut.axis);
  const step = stepOf(range);
  return (
    <div data-section-panel role="group" aria-label="Section" className="absolute right-3 top-14 z-30 w-60 max-w-[calc(100%-1.5rem)] space-y-2 rounded-md bg-panel/90 px-3 py-2 text-[13px] text-ink-2 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <span id="section-axis">Cut across</span>
        <ToggleGroup
          aria-labelledby="section-axis"
          value={[cut.axis]}
          onValueChange={(next) => {
            const [axis] = next;
            if (isAxis(axis) && axis !== cut.axis) onChange({ axis, at: null });
          }}
          className="flex gap-1"
        >
          {AXES.map((axis) => (
            <ToggleGroupItem
              key={axis}
              value={axis}
              data-axis={axis}
              className="size-7 rounded-md border border-rule bg-panel-2 text-[13px] uppercase text-ink-3 data-[pressed]:border-accent data-[pressed]:text-ink"
            >
              {axis}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>
      <Slider
        label={`Position along ${cut.axis}`}
        valueText={`${cut.axis} = ${positionLabel(at, step)}`}
        min={range.min}
        max={range.max}
        step={step}
        largeStep={10 * step}
        value={at}
        onValueChange={(next) => {
          onChange({ axis: cut.axis, at: next });
        }}
      />
      <p data-section-at className="tabular-nums text-ink">
        Plane at {cut.axis} = {positionLabel(at, step)}
      </p>
    </div>
  );
}
