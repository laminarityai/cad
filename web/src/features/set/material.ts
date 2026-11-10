import type { BriefView } from "@/api/types";

const PROJECT_PREFIX = "project-";

/** The key every score of this brief must use: the material of the made_of requirement the person
 * confirmed, named as the server's `MaterialsTable.row_key` names it. Null when none is confirmed. */
export function pinnedMaterial(brief: BriefView, listedKeys: readonly string[]): string | null {
  const confirmed = brief.proposals.find((one) => one.proposal === brief.confirmed_proposal);
  for (const row of confirmed?.requirements ?? []) {
    const target = row.requirement.target;
    if (target.kind !== "made_of") continue;
    let named = target.material;
    while (named.startsWith(PROJECT_PREFIX)) named = named.slice(PROJECT_PREFIX.length);
    return listedKeys.includes(named) ? named : PROJECT_PREFIX + named;
  }
  return null;
}
