import { useServices } from "@/app/context";
import { useResources, type Resource } from "@/state/resource";
import { restore, type DoneCheck, type ResultLine, type RunningCheck, type Scorecard } from "@/api/snapshot";
import type { Source, Specimen } from "@/api/types";
import type { Axis, Extents } from "@/features/viewer/dimensions";
import type { Where } from "@/features/viewer/where";

const POLL_MS = 1500;

export type Card = { snapshot: Scorecard; stale?: true } | { snapshot: null; missing: "reading" | "not_scored" | "unread" };

const NOT_SCORED = "NotScored";

function cardOf(resource: Resource<Scorecard>): Card {
  switch (resource.status) {
    case "ok":
      return resource.stale ? { snapshot: resource.data, stale: true } : { snapshot: resource.data };
    case "loading":
      return { snapshot: null, missing: "reading" };
    case "error":
      return { snapshot: null, missing: resource.kind === NOT_SCORED ? "not_scored" : "unread" };
    case "signed_out":
    case "not_found":
      return { snapshot: null, missing: "unread" };
  }
}

export interface CardKey {
  variantId: string;
  materialKey: string | null;
  briefId: string;
}

const entryOf = (one: CardKey) => `${one.variantId}|${one.materialKey ?? ""}|${one.briefId}`;

/** Polls each card instead of streaming it: a browser holds six connections per host, and the
 * chat stream and the meshes need theirs. */
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
  for (const [entry, resource] of Object.entries(resources)) cards[entry.split("|")[0] ?? ""] = cardOf(resource);
  return cards;
}

function short(statement: string): string {
  const first = statement.split(/(?<=[a-z0-9)])[.(]\s/)[0] ?? statement;
  return first.length > 70 ? `${first.slice(0, 68)}…` : first;
}

/** `agent` is a pass by an agent-written check the person approved, which our team has not reviewed. */
export type Status = "pass" | "fail" | "unknown" | "running" | "not_answering" | "unchecked" | "researched" | "agent";

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
  specimen?: string;
}

const CHECK_NAMES: Record<string, string> = {
  closed_solid: "Closed solid",
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

/** A requirement on a body compares a measure named `<measure>:<body>`, so its row shows that body's number, and
 * nothing when the variant has no such body. */
function bodyOf(measures: readonly string[], measure: string): string | undefined {
  return measures.map((one) => (one.startsWith(`${measure}:`) ? one.slice(measure.length + 1) : "")).find((one) => /^[a-z]/i.test(one));
}

function valueOf(result: DoneCheck | undefined, measures: readonly string[] = []): string {
  if (!result) return "";
  const by = (name: string) => result.measured.find((one) => one.name === name)?.value;
  if (result.check_id === "mass") {
    const body = bodyOf(measures, "mass");
    const mass = by(body === undefined ? "mass" : `mass:${body}`);
    if (mass) return mass.unit === "kg" ? `${num(mass.magnitude * 1000)} g` : `${num(mass.magnitude)} ${mass.unit}`;
  }
  if (result.check_id === "extents") {
    const edges = ["x", "y", "z"].map((axis) => by(`extent:${axis}`)).filter((one) => one !== undefined);
    if (edges.length === 3) return `${edges.map((one) => num(one.magnitude)).join(" × ")} mm`;
  }
  if (result.check_id === "holes") {
    const body = bodyOf(measures, "hole_diameter");
    const prefix = body === undefined ? "hole_diameter:" : `hole_diameter:${body}:`;
    const named = (name: string) => name.startsWith(prefix) && /^\d+$/.test(name.slice(prefix.length));
    const sizes = result.measured.filter((one) => named(one.name)).map((one) => one.value);
    if (sizes.length === 0) return "no round holes";
    const unit = sizes[0]?.unit ?? "mm";
    return `${String(sizes.length)} ${sizes.length === 1 ? "hole" : "holes"}: ${sizes.map((one) => num(one.magnitude)).join(", ")} ${unit}`;
  }
  if (result.check_id === "min_wall") {
    const body = bodyOf(measures, "min_wall");
    const wall = by(body === undefined ? "min_wall" : `min_wall:${body}`);
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
function whereOf(result: DoneCheck | undefined, measures: readonly string[]): Where | undefined {
  if (result?.check_id !== "fea" || !result.where) return undefined;
  const { displacement, support, load } = result.where;
  const faces = displacement && measures.includes("max_displacement") ? displacement : { support, load };
  return faces.support.length + faces.load.length > 0 ? faces : undefined;
}

const DESCRIBED_TAG = "load case the agent described, not reviewed by our team";

function specimenText(specimen: Specimen): string {
  switch (specimen.form) {
    case "printed":
      if (specimen.direction === "X-Y") return "strength of prints pulled in the build plane (X-Y), not across layers";
      return specimen.direction === "Z" ? "strength of prints pulled across layers (Z)" : "strength of printed specimens, direction not stated";
    case "wrought":
      return `strength of wrought metal, ${specimen.condition ?? "temper not stated"}`;
    case "sheet":
      return "strength of plastic sheet, not printed";
  }
}

function specimenOf(result: DoneCheck | undefined): string | undefined {
  for (const read of result?.reads ?? []) if (read.kind === "cited" && read.specimen) return specimenText(read.specimen);
  return undefined;
}

function sentence(text: string): string {
  const said = `${text.charAt(0).toUpperCase()}${text.slice(1)}`;
  return /[.!?]$/.test(said) ? said : `${said}.`;
}

function withUnpassedCheckReason(reason: string, result: DoneCheck | undefined): string {
  return result && result.verdict !== "pass" ? `${reason} ${sentence(result.reason)}` : reason;
}

export const linesOfCard = (card: Extract<Card, { snapshot: Scorecard }>) => linesOf(card.snapshot, card.stale ? "not_answering" : "running");

export function linesOf(snapshot: Scorecard, busy: "running" | "not_answering" = "running"): { asked: Line[]; also: Line[] } {
  const results = snapshot.results;
  const done = (id: string, instance: string) => results.find((one): one is DoneCheck => isDone(one) && one.check_id === id && one.instance === instance);
  const running = (id: string, instance: string) => results.some((one) => isRunning(one) && one.check_id === id && one.instance === instance);
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
      const instance = "instance" in one ? (one.instance ?? "") : "";
      const result = done(one.check_id, instance);
      if (one.kind === "waiting" || running(one.check_id, instance)) {
        asked.push({
          key,
          label: short(one.statement),
          status: busy,
          value: "",
          why: "",
          formula: "",
          sources: [],
        });
        continue;
      }
      const researched = "basis" in one && one.basis === "researched";
      const described = "load_case" in one && one.load_case === "described";
      const reason = withUnpassedCheckReason("reason" in one ? one.reason : "", result);
      const measures = "comparisons" in one ? one.comparisons.map((comparison) => comparison.measure) : [];
      const where = whereOf(result, measures);
      const specimen = measures.includes("safety_factor") ? specimenOf(result) : undefined;
      asked.push({
        key,
        label: short(one.statement),
        status: statusOf("verdict" in one ? one.verdict : "unknown", researched),
        value: valueOf(result, measures),
        // The person confirmed these words, so the row keeps them whole beside its reason.
        why: described ? `${one.statement}. ${reason}` : reason,
        formula: result?.formula ?? "",
        sources: result?.sources ?? [],
        ...(described ? { tag: DESCRIBED_TAG } : {}),
        ...(where ? { where } : {}),
        ...(specimen ? { specimen } : {}),
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
          status: busy,
          value: "",
          why: "",
          formula: one.formula,
          sources: one.sources,
        };
      const specimen = specimenOf(one);
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
        ...(specimen ? { specimen } : {}),
      };
    });
  const untested = snapshot.untested.map((text, n): Line => ({ key: `untested:${String(n)}`, label: text, status: "unchecked", value: "", why: "", formula: "", sources: [] }));
  return { asked, also: [...also, ...untested] };
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
    values: [
      ...one.values.map((value) => ({
        measure: value.measure,
        target: quantity(value.proposed),
        measured: value.measured ? quantity(value.measured) : null,
      })),
      ...(one.holes ? [holesBand(one.holes)] : []),
    ],
  }));
}

type WaitingHoles = NonNullable<Scorecard["awaiting"][number]["holes"]>;

/** A holes target's band beside every diameter the check measured. It counts none of them into the
 * band: that is the judgment Confirm waits for. */
function holesBand(holes: WaitingHoles): Awaiting["values"][number] {
  const holeCount = holes.count === null ? "a hole" : `${String(holes.count)} holes`;
  const sizes = holes.measured.map(quantity);
  const listed = sizes.length > 1 ? `${sizes.slice(0, -1).join(", ")} and ${sizes[sizes.length - 1] ?? ""}` : sizes[0];
  return {
    measure: "hole diameters",
    target: `${holeCount} from ${quantity(holes.low)} to ${quantity(holes.high)}`,
    measured: listed ?? null,
  };
}

export const NOT_ANSWERING = "Not answering";

export const MISSING: Record<Extract<Card, { snapshot: null }>["missing"], string> = {
  reading: "Reading the checks",
  not_scored: "Not checked yet.",
  unread: "The checks could not be read.",
};

export function summaryOf(card: Card | undefined): {
  status: Status | "none";
  text: string;
} {
  if (!card) return { status: "none", text: "" };
  if (!card.snapshot) return { status: "none", text: MISSING[card.missing] };
  const { asked, also } = linesOfCard(card);
  const all = [...asked, ...also];
  if (all.some((one) => one.status === "running")) return { status: "running", text: "Checking" };
  if (all.some((one) => one.status === "not_answering")) return { status: "not_answering", text: NOT_ANSWERING };
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
