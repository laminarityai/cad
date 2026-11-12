import { useEffect, useMemo, useState } from "react";
import { dimensionLines, pointsOf, type Extents, type ScreenPoint } from "./dimensions";
import type { Shapes, Track } from "./engine";

/** The size check's three numbers drawn on the part. `extents` holds the check's own numbers, and `bb` only
 * says where the lines go: no number on screen comes from the mesh. The lines follow the camera, and
 * stay off until the viewer can project. */
export function DimensionOverlay({ extents, bb, track }: { extents: Extents; bb: Shapes["bb"]; track: Track | null }) {
  // The scorecard is read again every few seconds, so the numbers are compared by value: a new object
  // with the same numbers must not start the projection, and its zoom, over.
  const { x, y, z } = extents;
  const lines = useMemo(() => dimensionLines({ x, y, z }, bb), [x, y, z, bb]);
  const [screen, setScreen] = useState<readonly (ScreenPoint | null)[] | null>(null);
  useEffect(() => {
    if (track === null) return;
    return track(pointsOf(lines), setScreen);
  }, [track, lines]);
  const drawn = lines.flatMap((one, at) => {
    const [a, b, from, to] = screen?.slice(4 * at, 4 * at + 4) ?? [];
    return a && b && from && to ? [{ ...one, a, b, from, to }] : [];
  });
  return (
    <div data-dimensions role="group" aria-label="Size check" className="pointer-events-none absolute inset-0 z-20">
      <svg aria-hidden className="absolute inset-0 size-full overflow-visible stroke-ink-2" fill="none" strokeWidth={1.5}>
        {drawn.map((one) => (
          <g key={one.axis}>
            <path d={`M${String(one.a.x)} ${String(one.a.y)}L${String(one.from.x)} ${String(one.from.y)}M${String(one.b.x)} ${String(one.b.y)}L${String(one.to.x)} ${String(one.to.y)}`} strokeWidth={1} strokeDasharray="3 3" />
            <line x1={one.from.x} y1={one.from.y} x2={one.to.x} y2={one.to.y} />
            {[one.from, one.to].map((end, i) => (
              <circle key={i} cx={end.x} cy={end.y} r={3} className="fill-ink-2" stroke="none" />
            ))}
          </g>
        ))}
      </svg>
      <p className="absolute left-3 top-3 rounded-md bg-panel/85 px-2.5 py-1 text-[13px] text-ink-2">Size check</p>
      {drawn.map((one) => (
        <span
          key={one.axis}
          data-dimension={one.axis}
          className="absolute -translate-x-1/2 -translate-y-1/2 whitespace-nowrap rounded bg-panel/90 px-1.5 py-0.5 text-[13px] tabular-nums text-ink"
          style={{ left: (one.from.x + one.to.x) / 2, top: (one.from.y + one.to.y) / 2 }}
        >
          {one.label}
        </span>
      ))}
    </div>
  );
}
