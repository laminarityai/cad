/* Throwaway prototype (proto/project-workspace). The page's view model: one project is the page.
 *
 *   Workspace
 *     project      the job, named from its first brief's words, never by id
 *     briefs[]     each brief: its words, its state, the material and who chose it, its set
 *       slots[]    one tab each: a short label, a one-line difference, its revisions (old to new)
 *         revisions[]  each one a variant id the viewer and the scorecard read
 *     asks         everything waiting on the person, drawn as one card in the chat
 *     files        context parts, uploads and the sources checks cite
 *     conversation the one chat of the project, the same for every brief
 *
 * Everything here is read from /v1 except what the server cannot say yet, which is marked MOCK. */
import type { Api } from "@/api/client";
import { requestJson } from "@/api/client";
import type { BriefView, VariantSetView, WaitingView } from "@/api/types";

export type BriefState = "drafting" | "waiting" | "building" | "ready";

export interface Revision {
  n: number;
  variantId: string;
  at: string;
  /** MOCK: no revision carries a note yet. The agent would write one with each build. */
  note: string | null;
}

export interface Slot {
  slot: number;
  /** MOCK: the agent's short name for the option. Today it exists only in chat text. */
  label: string;
  /** MOCK: the one-line difference from the other options. */
  differs: string;
  revisions: Revision[];
}

export interface Material {
  key: string;
  name: string;
  chosenBy: "you" | "agent";
}

export interface Brief {
  id: string;
  words: string;
  title: string;
  state: BriefState;
  material: Material | null;
  slots: Slot[];
  /** The parts this brief must fit, drawn ghosted with each option (#206). */
  fits: Fit[];
}

export interface Fit {
  name: string;
  variantId: string;
}

/* MOCK: the real read lists a brief's confirmed context parts with the variant each came from. The
 * box's part is still waiting on the copy; it is drawn as if confirmed. */
const FITS: Record<string, Fit[]> = {
  "63b2e3ae7a3ab713": [{ name: "Desk-clip box", variantId: "3a55c72eb48a3dc3" }],
};

export interface AskRow {
  id: string;
  kind: "requirement" | "part";
  text: string;
  quote: string;
}

export interface Ask {
  briefId: string;
  briefTitle: string;
  rows: AskRow[];
}

export type ProjectFile =
  | { kind: "part"; name: string; facts: string; state: "waiting" | "confirmed"; from: "built" | "upload" }
  | { kind: "upload"; name: string; type: "cad" | "document" | "image" | "text"; size: string; state: "reading" | "ready" }
  | { kind: "source"; title: string; url: string };

export interface Workspace {
  projectId: string;
  title: string;
  briefs: Brief[];
  asks: Ask[];
  files: ProjectFile[];
  conversationId: string | null;
}

/* MOCK labels, copied from the agent's own words in the operator's chat (seq 64). The real build
 * takes them from an agent-supplied label on build_variant. */
const LABELS: Record<string, { label: string; differs: string }> = {
  "3a55c72eb48a3dc3": { label: "Open box", differs: "60 × 40 × 30, 2 mm walls" },
  "27c2d5123a01c996": { label: "Flat lid", differs: "plate on the rim" },
  e4c5fd81fa49bb3a: { label: "Recessed lid", differs: "plugs in, flush with the rim" },
  "026445a319ce2b10": { label: "Separate lid", differs: "prints flat on its own" },
  "2ce31a3eb940337d": { label: "Lid on rim", differs: "box + lid, 32 mm tall" },
};

const NOTES: Record<string, string> = {
  "27c2d5123a01c996": "First try: flat plate on the rim",
  e4c5fd81fa49bb3a: "Plugs in, flush with the rim",
  "026445a319ce2b10": "2 mm plate",
  "928167d0fb6c61e6": "3 mm plate, from “make this thicker”",
};

const MATERIAL_NAMES: Record<string, string> = { "prusament-pla": "Prusament PLA" };

function titleOf(words: string): string {
  const trimmed = words.replace(/^(can you|please|i want|i need)\s+/i, "").replace(/[.?!]+$/, "");
  const short = trimmed.split(/,| with | for /)[0] ?? trimmed;
  const capital = short.charAt(0).toUpperCase() + short.slice(1);
  return capital.length > 32 ? `${capital.slice(0, 30)}…` : capital;
}

function materialOf(brief: BriefView): Material {
  const confirmed = brief.proposals.find((one) => one.proposal === brief.confirmed_proposal);
  for (const row of confirmed?.requirements ?? []) {
    const target = row.requirement.target as { kind: string; material?: string };
    if (target.kind === "made_of" && target.material) {
      return { key: target.material, name: MATERIAL_NAMES[target.material] ?? target.material, chosenBy: "you" };
    }
  }
  /* #200: the agent chooses when the brief names none. Here it scored the lid with this one. */
  return { key: "prusament-pla", name: "Prusament PLA", chosenBy: "agent" };
}

function slotsOf(set: VariantSetView | null): Slot[] {
  if (!set) return [];
  return set.members.map((member) => {
    /* An option keeps its name across revisions: the newest revision that has one names it. */
    const named = [member.variant_id, ...member.revisions.map((one) => one.variant_id).reverse()].find((id) => id in LABELS);
    const latest = (named ? LABELS[named] : undefined) ?? { label: `Option ${String(member.slot)}`, differs: "" };
    return {
      slot: member.slot,
      label: latest.label,
      differs: latest.differs,
      revisions: member.revisions.map((one) => ({
        n: one.revision,
        variantId: one.variant_id,
        at: one.joined_at,
        note: NOTES[one.variant_id] ?? null,
      })),
    };
  });
}

function stateOf(brief: BriefView, waiting: WaitingView, slots: Slot[]): BriefState {
  if (waiting.items.some((item) => item.brief_id === brief.brief_id)) return "waiting";
  if (brief.confirmed_proposal === null) return "drafting";
  return slots.length === 0 ? "building" : "ready";
}

const PART_ID = /context part (part-[0-9a-f]+)/;

/** The server's headline names a context part by id. The person never sees an id. */
function plainHeadline(headline: string, partName: string): string {
  return headline.replace(PART_ID, partName).replace(/^At most (.*) clear of /, "At most $1 gap to ");
}

function asksOf(waiting: WaitingView, titles: Record<string, string>, partNames: string): Ask[] {
  const byBrief = new Map<string, Ask>();
  waiting.items.forEach((item, at) => {
    const ask = byBrief.get(item.brief_id) ?? { briefId: item.brief_id, briefTitle: titles[item.brief_id] ?? "", rows: [] };
    item.rows.forEach((row, index) => {
      const part = item.kind === "context_part";
      /* #200: the material is the agent's pick, shown as a label the person changes in chat. It is
       * never a row to confirm. */
      if (/^Made of /.test(row.headline)) return;
      ask.rows.push({
        id: `${String(at)}:${String(index)}`,
        kind: part ? "part" : "requirement",
        text: part ? (row.headline.split(",")[0] ?? row.headline) : plainHeadline(row.headline, partNames),
        quote: row.quote,
      });
    });
    byBrief.set(item.brief_id, ask);
  });
  return [...byBrief.values()];
}

function partsOf(waiting: WaitingView): ProjectFile[] {
  return waiting.items
    .filter((item) => item.kind === "context_part")
    .flatMap((item) =>
      item.rows.map((row) => {
        const [name = row.headline, ...rest] = row.headline.split(",");
        const box = /(\d+) by (\d+) by (\d+) mm/.exec(rest.join(","));
        return {
          kind: "part" as const,
          name: name.trim(),
          facts: box ? `${box[1] ?? ""} × ${box[2] ?? ""} × ${box[3] ?? ""} mm` : "",
          state: "waiting" as const,
          from: "built" as const,
        };
      }),
    );
}

/** The waiting list names a context part by its name and a requirement names it by id. With one
 * part waiting, that id is that part; the real read lists parts by id. */
function partNamesOf(waiting: WaitingView): string {
  const item = waiting.items.find((one) => one.kind === "context_part");
  return (item?.rows[0]?.headline.split(",")[0] ?? "the part").trim();
}

export async function loadWorkspace(api: Api, projectId: string): Promise<Workspace> {
  const [project, waiting, conversation] = await Promise.all([
    api.project(projectId),
    api.waiting(projectId),
    requestJson<{ conversation_id: string | null }>("GET", `/v1/projects/${encodeURIComponent(projectId)}/conversation`),
  ]);
  const briefs = await Promise.all(
    project.briefs.map(async (summary) => {
      const [brief, set] = await Promise.all([
        api.brief(summary.brief_id),
        summary.confirmed_proposal === null ? Promise.resolve(null) : api.variantSet(projectId, summary.brief_id),
      ]);
      return { brief, set };
    }),
  );
  const titles = Object.fromEntries(briefs.map(({ brief }) => [brief.brief_id, titleOf(brief.text)]));
  const partNames = partNamesOf(waiting);
  return {
    projectId,
    title: briefs[0] ? titleOf(briefs[0].brief.text) : "New project",
    briefs: briefs.map(({ brief, set }) => {
      const slots = slotsOf(set);
      return {
        id: brief.brief_id,
        words: brief.text,
        title: titles[brief.brief_id] ?? "",
        state: stateOf(brief, waiting, slots),
        material: materialOf(brief),
        slots,
        fits: FITS[brief.brief_id] ?? [],
      };
    }),
    asks: asksOf(waiting, titles, partNames),
    files: partsOf(waiting),
    conversationId: conversation.conversation_id,
  };
}

/* What the person has chosen on the page. None of it is in the URL. */
export interface View {
  briefId: string | null;
  slotOf: Record<string, number>;
  /** null shows the newest revision of the slot. */
  revisionOf: Record<string, number | null>;
  highlight: Highlight | null;
  pointing: boolean;
}

export interface Highlight {
  variantId: string;
  x: number;
  y: number;
  label: string;
}

export type ViewAction =
  | { type: "brief"; briefId: string }
  | { type: "slot"; briefId: string; slot: number }
  | { type: "revision"; key: string; n: number | null }
  | { type: "point"; on: boolean }
  | { type: "highlight"; highlight: Highlight | null };

export const viewStart: View = { briefId: null, slotOf: {}, revisionOf: {}, highlight: null, pointing: false };

export function viewReducer(view: View, action: ViewAction): View {
  switch (action.type) {
    case "brief":
      return { ...view, briefId: action.briefId, highlight: null, pointing: false };
    case "slot":
      return { ...view, slotOf: { ...view.slotOf, [action.briefId]: action.slot }, highlight: null };
    case "revision":
      return { ...view, revisionOf: { ...view.revisionOf, [action.key]: action.n }, highlight: null };
    case "point":
      return { ...view, pointing: action.on };
    case "highlight":
      return { ...view, highlight: action.highlight, pointing: false };
  }
}
