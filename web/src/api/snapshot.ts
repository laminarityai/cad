import type { CheckResult, MeasureOnly, PendingCheck, ScorecardSnapshot } from "./types";

type Filled<T, K extends keyof T> = Omit<T, K> & Required<Pick<T, K>>;

type OnSnapshot = "not_verified" | "research_problem" | "research" | "assumptions" | "awaiting" | "bodies" | "body_materials" | "untested";
type OnResult = "reads" | "instance";

/** A scorecard with the fields the server leaves out when empty always present, which is what the
 * page reads. */
export type DoneCheck = Filled<CheckResult, OnResult>;
export type RunningCheck = Filled<PendingCheck, OnResult>;
export type MeasuredCheck = Filled<MeasureOnly, OnResult>;
export type ResultLine = DoneCheck | RunningCheck | MeasuredCheck;
export type Scorecard = Filled<Omit<ScorecardSnapshot, "results">, OnSnapshot> & {
  results: ResultLine[];
};

export function restore(wire: ScorecardSnapshot): Scorecard {
  return {
    ...wire,
    not_verified: wire.not_verified ?? [],
    research: wire.research ?? [],
    assumptions: wire.assumptions ?? [],
    awaiting: wire.awaiting ?? [],
    bodies: wire.bodies ?? [],
    body_materials: wire.body_materials ?? [],
    untested: wire.untested ?? [],
    research_problem: wire.research_problem ?? null,
    results: wire.results.map((one) => ({ ...one, reads: one.reads ?? [], instance: one.instance ?? "" })),
  };
}
