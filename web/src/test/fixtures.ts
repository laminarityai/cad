import type {
  BriefView,
  Checked,
  RequirementResult,
  Verdict,
  Waiting,
} from "@/api/types";
import type { DoneCheck, MeasuredCheck, RunningCheck, Scorecard } from "@/api/snapshot";

export const mass = (verdict: Verdict): Checked => ({
  kind: "checked",
  requirement_id: "r1",
  statement: "weigh at most 50 g",
  check_id: "mass",
  verdict,
  reason: "The mass check measured the part and compared it with the limit the person confirmed.",
  comparisons: [{ measure: "mass", comparator: "at_most", limit: { magnitude: 50, unit: "g" }, verdict }],
  basis: "checks",
  researched: [],
});

export const deflection = (): Waiting => ({
  kind: "waiting",
  requirement_id: "r2",
  statement: "bend at most 2 mm under 40 N",
  check_id: "fea",
});

export const deflectionDone = (): Checked => ({
  ...mass("fail"),
  requirement_id: "r2",
  statement: "bend at most 2 mm under 40 N",
  check_id: "fea",
});

export const massResult = (grams = 41.2): DoneCheck => ({
  check_id: "mass",
  verdict: "pass",
  measured: [{ name: "mass", value: { magnitude: grams, unit: "g" } }],
  formula: "density times volume",
  reason: "measured",
  sources: [],
  version: "v1",
  instance: "",
  reads: [],
});

export const feaMeasureOnly = (instance: string): MeasuredCheck => ({
  kind: "measure_only",
  label: "measured under a load you have not confirmed, no verdict",
  check_id: "fea",
  measured: [{ name: "max_displacement", value: { magnitude: 1.5, unit: "mm" } }],
  formula: "linear static",
  reason: "solved",
  sources: [],
  version: "v1",
  instance,
  reads: [],
});

export const feaPending = (): RunningCheck => ({
  kind: "pending",
  check_id: "fea",
  formula: "linear static",
  sources: [],
  version: "v1",
  instance: "",
  reads: [],
});

export function snapshot(
  variantId: string,
  requirements: RequirementResult[],
  results: Scorecard["results"],
  etag = variantId,
): Scorecard {
  return {
    variant_id: variantId,
    rebuilt_from: null,
    material_key: "prusament-pla",
    table_version: "t1",
    check_image_digest: "d1",
    brep_sha256: "b".repeat(64),
    step: { kind: "missing", reason: "none" },
    results,
    pending: results.flatMap((one) => ("kind" in one ? [one.check_id] : [])),
    basis: {
      kind: "against_brief",
      brief_id: "b1",
      decision_sha256: "c".repeat(64),
      requirements,
      unverified_requirements: [],
      agent_checked_requirements: [],
    },
    not_verified: [],
    assumptions: [],
    awaiting: [],
    material: { key: "prusament-pla", set_by: { kind: "agent_argument", statement: "The agent chose this material." } },
    research: [],
    research_problem: null,
    etag,
  };
}

export const brief = (confirmed: boolean): BriefView => ({
  brief_id: "b1",
  project_id: "p1",
  text: "A bracket that weighs at most 50 g.",
  name: confirmed ? "Bracket" : null,
  confirmed_proposal: confirmed ? 1 : null,
  proposals: [
    {
      brief_id: "b1",
      proposal: 1,
      status: confirmed ? "confirmed" : "proposed",
      requirements: [
        {
          requirement: {
            id: "r1",
            brief_id: "b1",
            target: { kind: "max_mass", mass: { magnitude: 50, unit: "g" } },
            origin: { kind: "brief_text", start: 12, end: 34 },
          },
          plain: "Weighs at most 50 g",
          check: "mass",
          status: confirmed ? "confirmed" : "proposed",
          edited_by_user: null,
        },
      ],
    },
  ],
});
