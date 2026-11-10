import type { CheckResult, PendingCheck, ScorecardSnapshot } from "./types";

type Lean<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>;

/** A scorecard event as the server writes it. The server leaves out an empty `reads`, an empty
 * `instance`, an empty `research` and `not_verified` and a null `research_problem`, though the
 * generated types list them as required. */
export type SnapshotOnTheWire = Lean<
  Omit<ScorecardSnapshot, "results">,
  "not_verified" | "research_problem" | "research"
> & {
  results: (Lean<CheckResult, "reads" | "instance"> | Lean<PendingCheck, "reads" | "instance">)[];
};

export function restore(wire: SnapshotOnTheWire): ScorecardSnapshot {
  return {
    ...wire,
    not_verified: wire.not_verified ?? [],
    research: wire.research ?? [],
    research_problem: wire.research_problem ?? null,
    results: wire.results.map((one) => ({ ...one, reads: one.reads ?? [], instance: one.instance ?? "" })),
  };
}
