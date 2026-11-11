import { useCallback, useState } from "react";
import type { Picked } from "@/api/types";

export type Pick = { kind: "face"; index: number } | { kind: "edge"; index: number } | { kind: "part" };

export interface Selection {
  variantId: string;
  picks: readonly Pick[];
}

const same = (a: Pick, b: Pick) => a.kind === b.kind && (a.kind === "part" || (b.kind !== "part" && a.index === b.index));

/** A click replaces the selection, shift toggles one face or edge, and a part pick replaces everything. */
export function nextSelection(current: Selection | null, variantId: string, pick: Pick | null, shift: boolean): Selection | null {
  if (pick === null) return shift ? current : null;
  if (pick.kind === "part" || !shift) return { variantId, picks: [pick] };
  const held = current?.variantId === variantId ? current.picks.filter((one) => one.kind !== "part") : [];
  const picks = held.some((one) => same(one, pick)) ? held.filter((one) => !same(one, pick)) : [...held, pick];
  return picks.length === 0 ? null : { variantId, picks };
}

const indexes = (picks: readonly Pick[], kind: "face" | "edge") =>
  picks.flatMap((one) => (one.kind === kind ? [one.index] : [])).sort((a, b) => a - b);

export function toPicked(selection: Selection): Picked {
  return {
    variant_id: selection.variantId,
    faces: indexes(selection.picks, "face"),
    edges: indexes(selection.picks, "edge"),
    part: selection.picks.some((one) => one.kind === "part"),
  };
}

const count = (n: number, word: string) => `${String(n)} ${word}${n === 1 ? "" : "s"}`;

export function summaryOf(selection: Selection): string {
  if (selection.picks.some((one) => one.kind === "part")) return "Whole part";
  const faces = indexes(selection.picks, "face").length;
  const edges = indexes(selection.picks, "edge").length;
  return [faces > 0 ? count(faces, "face") : null, edges > 0 ? count(edges, "edge") : null].filter((one) => one !== null).join(", ");
}

/** The selection belongs to the variant on screen, so it is dropped when another variant is shown. */
export function useSelection(variantId: string | null) {
  const [held, setHeld] = useState<{ variantId: string | null; selection: Selection | null }>({ variantId, selection: null });
  if (held.variantId !== variantId) setHeld({ variantId, selection: null });
  const onPick = useCallback((pick: Pick | null, shift: boolean) => {
    setHeld((was) => (was.variantId === null ? was : { ...was, selection: nextSelection(was.selection, was.variantId, pick, shift) }));
  }, []);
  const clear = useCallback(() => {
    setHeld((was) => (was.selection === null ? was : { ...was, selection: null }));
  }, []);
  return { selection: held.variantId === variantId ? held.selection : null, onPick, clear };
}
