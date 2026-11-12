import { useMemo, useState } from "react";
import type { Shapes } from "./engine";
import { splitFaces, type Where } from "./where";

/** A part that must fit is built in that part's frame, so the two draw together as they are. */
export function withFit(part: Shapes, fit: Shapes): Shapes {
  const ghost = fit.parts.map((one) => ({
    ...one,
    id: `/fit${one.id}`,
    name: `fit ${one.name}`,
    color: "#9aa7b4",
    alpha: 0.22,
  }));
  const bb = {
    xmin: Math.min(part.bb.xmin, fit.bb.xmin),
    xmax: Math.max(part.bb.xmax, fit.bb.xmax),
    ymin: Math.min(part.bb.ymin, fit.bb.ymin),
    ymax: Math.max(part.bb.ymax, fit.bb.ymax),
    zmin: Math.min(part.bb.zmin, fit.bb.zmin),
    zmax: Math.max(part.bb.zmax, fit.bb.zmax),
  };
  return { ...part, parts: [...part.parts, ...ghost], bb };
}

const sameWhere = (a: Where | null, b: Where | null) =>
  a === b || (a !== null && b !== null && a.support.join() === b.support.join() && a.load.join() === b.load.join());

/** `where` as the first object that held its faces. The scorecard is read again every few seconds and
 * each read makes a new object with the same faces, which must not count as a change. */
function useSameWhere(where: Where | null): Where | null {
  const [held, setHeld] = useState(where);
  if (!sameWhere(held, where)) setHeld(where);
  return sameWhere(held, where) ? held : where;
}

/** What the viewer draws: the part with the stress check's faces marked and the context part beside it.
 * The same object comes back while the mesh, the ghost and the marked faces are unchanged, because the
 * canvas draws the whole model again for each new object, and a redraw drops the person's section. */
export function useDrawn(part: Shapes | null, ghost: Shapes | null, where: Where | null): Shapes | null {
  const faces = useSameWhere(where);
  return useMemo(() => {
    if (part === null) return null;
    const marked = faces ? splitFaces(part, faces) : part;
    return ghost ? withFit(marked, ghost) : marked;
  }, [part, ghost, faces]);
}
