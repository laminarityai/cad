import type { Axis } from "./dimensions";
import type { Shapes } from "./engine";

/** The plane the person cuts the part with: it stands square to `axis` and sits `at` mm along it, in the
 * part's own frame. Everything beyond it is cut away. It is a control setting, never a size of the part. */
export interface Section {
  axis: Axis;
  at: number;
}

/** What the person has chosen. `at` is null until they move the slider, which means the middle of the part. */
export interface Cut {
  axis: Axis;
  at: number | null;
}

export interface Range {
  min: number;
  max: number;
}

export function rangeOf(bb: Shapes["bb"], axis: Axis): Range {
  return { min: bb[`${axis}min`], max: bb[`${axis}max`] };
}

/** The plane for a choice, kept inside the box so a part with another box (the next revision) still gets a cut. */
export function sectionOf(cut: Cut, bb: Shapes["bb"]): Section {
  const { min, max } = rangeOf(bb, cut.axis);
  const at = cut.at ?? (min + max) / 2;
  return { axis: cut.axis, at: Math.min(Math.max(at, min), max) };
}

/** The slider's step: 1, 2 or 5 times a power of ten, near a hundredth of the box, so a thin wall takes
 * several steps and a long part does not take hundreds. */
export function stepOf({ min, max }: Range): number {
  const raw = (max - min) / 100;
  if (!(raw > 0) || !Number.isFinite(raw)) return 1;
  const power = 10 ** Math.floor(Math.log10(raw));
  const lead = raw / power;
  return power * (lead >= 5 ? 5 : lead >= 2 ? 2 : 1);
}

/** The position as the slider's step writes it, for a label that says where the plane is. */
export function positionLabel(at: number, step: number): string {
  const places = Math.max(0, -Math.floor(Math.log10(step)));
  return `${at.toFixed(places)} mm`;
}
