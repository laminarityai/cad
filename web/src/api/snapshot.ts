import type { CheckResult, PendingCheck, ScorecardSnapshot } from "./types";

type Filled<T, K extends keyof T> = Omit<T, K> & Required<Pick<T, K>>;

type OnSnapshot = "not_verified" | "research_problem" | "research" | "assumptions";
type OnResult = "reads" | "instance";

/** A scorecard with the fields the server leaves out when empty always present, which is what the
 * page reads: `reads`, `instance`, `research`, `assumptions`, `not_verified` and a null `research_problem`. */
export type DoneCheck = Filled<CheckResult, OnResult>;
export type RunningCheck = Filled<PendingCheck, OnResult>;
export type Scorecard = Filled<Omit<ScorecardSnapshot, "results">, OnSnapshot> & {
  results: (DoneCheck | RunningCheck)[];
};

export function restore(wire: ScorecardSnapshot): Scorecard {
  return {
    ...wire,
    not_verified: wire.not_verified ?? [],
    research: wire.research ?? [],
    assumptions: wire.assumptions ?? [],
    research_problem: wire.research_problem ?? null,
    results: wire.results.map((one) => ({ ...one, reads: one.reads ?? [], instance: one.instance ?? "" })),
  };
}
