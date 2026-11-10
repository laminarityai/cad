import type { Mode } from "@/api/types";

export interface ModeInfo {
  mode: Mode;
  label: string;
  hint: string;
}

/** The modes the person picks. Test mode exists on the server but has no entry here. */
export const PICKABLE: readonly ModeInfo[] = [
  { mode: "plan", label: "Plan", hint: "Turns your words into requirements. Nothing builds." },
  { mode: "design", label: "Design", hint: "Builds and revises when you ask." },
  { mode: "auto", label: "Auto", hint: "Revises on its own until every check passes or it needs you. Leaving Auto stops the run." },
];

export function labelOf(mode: Mode | null): string {
  if (mode === null) return "Mode";
  return PICKABLE.find((one) => one.mode === mode)?.label ?? `${mode.slice(0, 1).toUpperCase()}${mode.slice(1)}`;
}

/** The mode Shift+Tab moves to: the next one in the list, wrapping around. */
export function nextMode(mode: Mode | null): Mode {
  const at = PICKABLE.findIndex((one) => one.mode === mode);
  return PICKABLE[(at + 1) % PICKABLE.length]?.mode ?? "plan";
}
