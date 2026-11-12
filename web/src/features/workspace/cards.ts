import { useServices } from "@/app/context";
import { useResources } from "@/state/resource";
import { restore, type DoneCheck, type ResultLine, type RunningCheck, type Scorecard } from "@/api/snapshot";
import type { Source } from "@/api/types";
import type { Axis, Extents } from "@/features/viewer/dimensions";
import type { Where } from "@/features/viewer/where";

const POLL_MS = 1500;

export interface Card {
  snapshot: Scorecard | null;
}

export interface CardKey {
  variantId: string;
  materialKey: string | null;
  briefId: string;
}

const entryOf = (one: CardKey) => `${one.variantId}|${one.materialKey ?? ""}|${one.briefId}`;

/** Polls each card instead of streaming it: a browser holds six connections per host, and the
 * chat stream and the meshes need theirs. A card shows once it has been read or has failed to be. */
export function useCards(keys: CardKey[]): Record<string, Card> {
  const { api } = useServices();
  const { resources } = useResources(
    keys.map(entryOf),
    async (entry) => {
      const [variantId = "", materialKey = "", briefId = ""] = entry.split("|");
      return restore(await api.scorecard(variantId, briefId, materialKey === "" ? null : materialKey));
    },
    POLL_MS,
  );
  const cards: Record<string, Card> = {};
  for (const [entry, resource] of Object.entries(resources)) {
    if (resource.status === "loading") continue;
    cards[entry.split("|")[0] ?? ""] = { snapshot: resource.status === "ok" ? resource.data : null };
  }
  return cards;
}

function short(statement: string): string {
  const first = statement.split(/(?<=[a-z0-9)])[.(]\s/)[0] ?? statement;
  return first.length > 70 ? `${first.slice(0, 68)}…` : first;
}

/** `agent` is a pass by an agent-written check the person approved, which our team has not reviewed. */
export type Status = "pass" | "fail" | "unknown" | "running" | "unchecked" | "researched" | "agent";

export interface Line {
  key: string;
  label: string;
  status: Status;
  value: string;
  why: string;
  formula: string;
  sources: Pick<Source, "url" | "title">[];
  /** The label a verdict carries when no reviewed check reached it. */
  tag?: string;
  /** The faces the stress check held and pushed on, for the row of a requirement that check decided. */
  where?: Where;
}

const CHECK_NAMES: Record<string, string> = {
  closed_solid: "One solid",
  interference: "No parts overlap",
  mass: "Mass",
  extents: "Size",
  fit: "Fit",
  fea: "Stiffness",
  holes: "Holes",
  min_wall: "Thinnest wall",
};

const isRunning = (one: ResultLine): one is RunningCheck => "kind" in one && one.kind === "pending";
const isDone = (one: ResultLine): one is DoneCheck => !("kind" in one);

function num(magnitude: number): string {
  return String(Number(magnitude.toPrecision(3)));
}

function valueOf(result: DoneCheck | undefined): string {
  if (!result) return "";
  const by = (name: string) => result.measured.find((one) => one.name === name)?.value;
  if (result.check_id === "mass") {
    const mass = by("mass");
    if (mass) return mass.unit === "kg" ? `${num(mass.magnitude * 1000)} g` : `${num(mass.magnitude)} ${mass.unit}`;
  }
  if (result.check_id === "extents") {
    const edges = ["x", "y", "z"].map((axis) => by(`extent:${axis}`)).filter((one) => one !== undefined);
    if (edges.length === 3) return `${edges.map((one) => num(one.magnitude)).join(" × ")} mm`;
  }
  if (result.check_id === "holes") {
    const sizes = result.measured.filter((one) => one.name.startsWith("hole_diameter:")).map((one) => one.value);
    if (sizes.length === 0) return "no round holes";
    const unit = sizes[0]?.unit ?? "mm";
    return `${String(sizes.length)} ${sizes.length === 1 ? "hole" : "holes"}: ${sizes.map((one) => num(one.magnitude)).join(", ")} ${unit}`;
  }
  if (result.check_id === "min_wall") {
    const wall = by("min_wall");
    if (wall) return `${num(wall.magnitude)} ${wall.unit}`;
  }
  if (result.check_id === "closed_solid") {
    const solids = by("solids");
    if (solids && solids.magnitude !== 1) return `${num(solids.magnitude)} solids`;
  }
  return "";
}

/** The size check's number for each axis, written as the Size row writes it, when the check passed on the
 * variant. Pending, unknown, failed and absent give null, so nothing is ever drawn from another source. */
export function passedExtents(snapshot: Scorecard | null | undefined): Extents | null {
  const result = snapshot?.results.find((one): one is DoneCheck => isDone(one) && one.check_id === "extents");
  if (result?.verdict !== "pass") return null;
  const label = (axis: Axis) => {
    const found = result.measured.find((one) => one.name === `extent:${axis}`)?.value;
    return found?.unit === "mm" ? `${num(found.magnitude)} mm` : null;
  };
  const [x, y, z] = [label("x"), label("y"), label("z")];
  return x !== null && y !== null && z !== null ? { x, y, z } : null;
}

function statusOf(verdict: string, researched: boolean): Status {
  if (verdict === "pass") return researched ? "researched" : "pass";
  return verdict === "fail" ? "fail" : "unknown";
}

/** The faces of the load case's own result: a requirement names the case, and each case has a result. */
function whereOf(results: ResultLine[], checkId: string, instance: string): Where | undefined {
  if (checkId !== "fea") return undefined;
  const found = results.find((one): one is DoneCheck => isDone(one) && one.check_id === checkId && one.instance === instance);
  const where = found?.where;
  return where && where.support.length + where.load.length > 0 ? where : undefined;
}

const DESCRIBED_TAG = "load case the agent described, not reviewed by our team";

export function linesOf(snapshot: Scorecard): { asked: Line[]; also: Line[] } {
  const results = snapshot.results;
  const done = (id: string) => results.find((one): one is DoneCheck => isDone(one) && one.check_id === id);
  const running = (id: string) => results.some((one) => isRunning(one) && one.check_id === id);
  const asked: Line[] = [];
  const covered = new Set<string>();
  if (snapshot.basis.kind === "against_brief") {
    for (const one of snapshot.basis.requirements) {
      const key = `req:${one.requirement_id}`;
      if (one.kind === "unverified") {
        asked.push({
          key,
          label: short(one.statement),
          status: "unchecked",
          value: "",
          why: one.statement,
          formula: "",
          sources: [],
        });
        continue;
      }
      if (one.kind === "agent_checked") {
        asked.push({
          key,
          label: short(one.statement),
          status: one.verdict === "pass" ? "agent" : statusOf(one.verdict, false),
          value: one.value ? quantity(one.value) : "",
          why: `${one.reason} ${one.title}: ${one.formula}, limit ${quantity(one.limit)}.`,
          formula: one.formula,
          sources: one.pages.map((url) => ({ url, title: url })),
          tag: one.label,
        });
        continue;
      }
      covered.add(one.check_id);
      const result = done(one.check_id);
      if (one.kind === "waiting" || running(one.check_id)) {
        asked.push({
          key,
          label: short(one.statement),
          status: "running",
          value: "",
          why: "",
          formula: "",
          sources: [],
        });
        continue;
      }
      const researched = "basis" in one && one.basis === "researched";
      const described = "load_case" in one && one.load_case === "described";
      const reason = "reason" in one ? one.reason : "";
      const where = "instance" in one ? whereOf(results, one.check_id, one.instance ?? "") : undefined;
      asked.push({
        key,
        label: short(one.statement),
        status: statusOf("verdict" in one ? one.verdict : "unknown", researched),
        value: valueOf(result),
        // The person confirmed these words, so the row keeps them whole beside its reason.
        why: described ? `${one.statement}. ${reason}` : reason,
        formula: result?.formula ?? "",
        sources: result?.sources ?? [],
        ...(described ? { tag: DESCRIBED_TAG } : {}),
        ...(where ? { where } : {}),
      });
    }
  }
  // A result with no verdict read a load nobody confirmed. Its assumed or awaiting row shows its measure.
  const also: Line[] = results
    .filter((one) => !covered.has(one.check_id))
    .filter((one): one is DoneCheck | RunningCheck => isDone(one) || isRunning(one))
    .map((one) => {
      const label = CHECK_NAMES[one.check_id] ?? one.check_id.replace(/_/g, " ");
      if (isRunning(one))
        return {
          key: `check:${one.check_id}`,
          label,
          status: "running" as const,
          value: "",
          why: "",
          formula: one.formula,
          sources: one.sources,
        };
      return {
        key: `check:${one.check_id}:${one.instance}`,
        label,
        status: statusOf(
          one.verdict,
          one.reads.some((read) => read.kind === "researched"),
        ),
        value: valueOf(one),
        why: one.reason,
        formula: one.formula,
        sources: one.sources,
      };
    });
  return { asked, also };
}

export interface Assumed {
  key: string;
  label: string;
  why: string;
  values: { measure: string; assumed: string; measured: string | null }[];
}

function quantity(one: { magnitude: number; unit: string }): string {
  return one.unit === "kg" ? `${num(one.magnitude * 1000)} g` : `${num(one.magnitude)} ${one.unit}`;
}

/** What the agent assumed, with the measure beside it. It has no status, so `summaryOf` never counts it. */
export function assumedOf(snapshot: Scorecard): Assumed[] {
  return snapshot.assumptions.map((one, index) => ({
    key: `assumed:${String(index)}`,
    label: short(one.statement),
    why: one.why,
    values: one.values.map((value) => ({
      measure: value.measure,
      assumed: quantity(value.assumed),
      measured: value.measured ? quantity(value.measured) : null,
    })),
  }));
}

export interface Awaiting {
  key: string;
  label: string;
  values: { measure: string; target: string; measured: string | null }[];
}

/** A target the person stated that waits for their Confirm, with the measure beside it. It has no
 * status, so `summaryOf` never counts it. */
export function awaitingOf(snapshot: Scorecard): Awaiting[] {
  return snapshot.awaiting.map((one) => ({
    key: `awaiting:${one.requirement_id}`,
    label: short(one.statement),
    values: one.values.map((value) => ({
      measure: value.measure,
      target: quantity(value.proposed),
      measured: value.measured ? quantity(value.measured) : null,
    })),
  }));
}

export function summaryOf(card: Card | undefined): {
  status: Status | "none";
  text: string;
} {
  if (!card?.snapshot) return { status: "none", text: card ? "Checking" : "" };
  const { asked, also } = linesOf(card.snapshot);
  const all = [...asked, ...also];
  if (all.some((one) => one.status === "running")) return { status: "running", text: "Checking" };
  const fails = all.filter((one) => one.status === "fail").length;
  if (fails > 0)
    return {
      status: "fail",
      text: `${String(fails)} fail${fails === 1 ? "s" : ""}`,
    };
  if (all.some((one) => one.status === "unknown")) return { status: "unknown", text: "Unknowns" };
  const agent = all.filter((one) => one.status === "agent").length;
  const described = all.filter((one) => one.tag === DESCRIBED_TAG).length;
  const apart = [
    ...(agent > 0 ? [`${String(agent)} on the agent's check`] : []),
    ...(described > 0 ? [`${String(described)} on a load case the agent described`] : []),
  ];
  const text = apart.length > 0 ? `All pass, ${apart.join(", ")}` : "All pass";
  return { status: agent > 0 ? "agent" : "pass", text };
}

export function sourcesOf(cards: Record<string, Card>): Source[] {
  const seen = new Map<string, Source>();
  for (const card of Object.values(cards)) {
    for (const result of card.snapshot?.results ?? []) for (const one of result.sources) seen.set(one.url, one);
  }
  return [...seen.values()];
}
