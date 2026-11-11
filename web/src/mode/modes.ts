import type { Mode } from "@/api/types";

export interface ModeInfo {
  mode: Mode;
  label: string;
  hint: string;
}

const MODES: Record<Mode, Omit<ModeInfo, "mode">> = {
  plan: { label: "Plan", hint: "Turns your words into requirements. Nothing builds." },
  design: { label: "Design", hint: "Builds and revises when you ask." },
  auto: { label: "Auto", hint: "Revises on its own until every check passes or it needs you. Leaving Auto stops the run." },
};

export const PICKABLE: readonly ModeInfo[] = (Object.keys(MODES) as Mode[]).map((mode) => ({ mode, ...MODES[mode] }));

export function labelOf(mode: Mode | null): string {
  return mode === null ? "Mode" : MODES[mode].label;
}

export function nextMode(mode: Mode | null): Mode {
  const at = PICKABLE.findIndex((one) => one.mode === mode);
  return PICKABLE[(at + 1) % PICKABLE.length]?.mode ?? "plan";
}
