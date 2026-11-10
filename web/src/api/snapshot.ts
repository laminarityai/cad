import type { CheckResult, PendingCheck, ScorecardSnapshot } from "./types";

type Lean<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>;
type Filled<T, K extends keyof T> = Omit<T, K> & Required<Pick<T, K>>;

type OnSnapshot = "not_verified" | "research_problem" | "research";
type OnResult = "reads" | "instance";

/** A scorecard event as the server writes it. The server leaves out an empty `reads`, an empty
 * `instance`, an empty `research` and `not_verified` and a null `research_problem`. */
export type SnapshotOnTheWire = Lean<Omit<ScorecardSnapshot, "results">, OnSnapshot> & {
  results: (Lean<CheckResult, OnResult> | Lean<PendingCheck, OnResult>)[];
};

/** A scorecard with those fields always present, which is what the page reads. The type holds
 * whether or not the generated types mark the fields optional. */
export type DoneCheck = Filled<CheckResult, OnResult>;
export type RunningCheck = Filled<PendingCheck, OnResult>;
export type Scorecard = Filled<Omit<ScorecardSnapshot, "results">, OnSnapshot> & {
  results: (DoneCheck | RunningCheck)[];
};

export function restore(wire: SnapshotOnTheWire): Scorecard {
  return {
    ...wire,
    not_verified: wire.not_verified ?? [],
    research: wire.research ?? [],
    research_problem: wire.research_problem ?? null,
    results: wire.results.map((one) => ({ ...one, reads: one.reads ?? [], instance: one.instance ?? "" })),
  };
}
