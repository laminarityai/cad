import type { Api } from "@/api/client";
import type { Cut } from "@/features/viewer/section";
import type { BriefView, ConfirmationCard, ContextPartView, DocumentView, MemberView, Outcome, VariantSetView } from "@/api/types";

export type BriefState = "waiting" | "empty" | "ready";

export interface Revision {
  n: number;
  variantId: string;
  at: string;
}

export interface SlotBody {
  name: string;
  material: string;
  chosenBy: "you" | "agent";
}

export interface Slot {
  slot: number;
  label: string;
  differs: string;
  revisions: Revision[];
  /** The latest revision's bodies, empty for one body with no name. */
  bodies: SlotBody[];
}

export interface Material {
  key: string;
  name: string;
  chosenBy: "you" | "agent";
}

export interface Fit {
  name: string;
  variantId: string;
}

export interface Brief {
  id: string;
  words: string;
  title: string;
  state: BriefState;
  slots: Slot[];
  materialOf: Record<number, Material | null>;
  fits: Fit[];
}

export interface Part {
  id: string;
  name: string;
  size: string;
  state: Outcome;
  uploaded: boolean;
  leftOut: string | null;
}

export interface Doc {
  id: string;
  name: string;
  withheld: boolean;
}

export type Confirmation = ConfirmationCard | null;

export interface Workspace {
  projectId: string;
  title: string;
  briefs: Brief[];
  confirmation: Confirmation;
  parts: Part[];
  documents: Doc[];
  conversationId: string;
}

function materialOf(member: MemberView): Material | null {
  if (!member.material) return null;
  return {
    key: member.material.key,
    name: member.material_name ?? member.material.key,
    chosenBy: member.material.set_by.kind === "agent_argument" ? "agent" : "you",
  };
}

function slotsOf(set: VariantSetView | null): Slot[] {
  return (set?.members ?? []).map((member) => ({
    slot: member.slot,
    label: member.option?.label ?? `Option ${String(member.slot)}`,
    differs: member.option?.differs ?? "",
    revisions: member.revisions.map((one) => ({
      n: one.revision,
      variantId: one.variant_id,
      at: one.joined_at,
    })),
    bodies: member.body_materials.map((one) => ({ name: one.body, material: one.name, chosenBy: one.set_by.kind === "agent_argument" ? "agent" : "you" })),
  }));
}

function stateOf(brief: BriefView, confirmation: Confirmation, slots: Slot[]): BriefState {
  if (confirmation?.items.some((item) => item.brief_id === brief.brief_id)) return "waiting";
  return slots.length === 0 ? "empty" : "ready";
}

const mm = (size: readonly number[]) => `${size.map((one) => String(Number(one.toPrecision(3)))).join(" × ")} mm`;

function briefOf(brief: BriefView, at: number, set: VariantSetView | null, confirmation: Confirmation, parts: ContextPartView[]): Brief {
  const slots = slotsOf(set);
  return {
    id: brief.brief_id,
    words: brief.text,
    title: brief.name ?? `Part ${String(at + 1)}`,
    state: stateOf(brief, confirmation, slots),
    slots,
    materialOf: Object.fromEntries((set?.members ?? []).map((member) => [member.slot, materialOf(member)])),
    fits: parts.flatMap((one) => (one.brief_id === brief.brief_id && one.outcome === "confirmed" && one.variant_id ? [{ name: one.name, variantId: one.variant_id }] : [])),
  };
}

function partOf(one: ContextPartView): Part {
  const holes = one.holes === 0 ? [] : [`${String(one.holes)} hole${one.holes === 1 ? "" : "s"}`];
  const solids = one.solids === 1 ? [] : [`${String(one.solids)} solids`];
  return {
    id: one.part_id,
    name: one.name,
    size: [mm(one.size_mm), ...solids, ...holes].join(" · "),
    state: one.outcome,
    uploaded: one.origin === "upload",
    leftOut: one.left_out,
  };
}

export async function loadWorkspace(api: Api, projectId: string): Promise<Workspace> {
  const [project, card, conversation] = await Promise.all([api.project(projectId), api.confirmation(projectId), api.conversation(projectId)]);
  const confirmation = card.snapshot === null ? null : card;
  const read = await Promise.all(
    project.briefs.map(async (summary, at) => {
      const [brief, set] = await Promise.all([
        api.brief(summary.brief_id),
        api.variantSet(projectId, summary.brief_id),
      ]);
      return briefOf(brief, at, set, confirmation, project.context_parts);
    }),
  );
  return {
    projectId,
    title: read[0]?.title ?? "New project",
    briefs: read,
    confirmation,
    parts: project.context_parts.map(partOf),
    documents: project.documents.map((one: DocumentView) => ({ id: one.file_id, name: one.name, withheld: one.withheld })),
    conversationId: conversation.conversation_id,
  };
}

export interface View {
  briefId: string | null;
  slotOf: Record<string, number>;
  revisionOf: Record<string, number | null>;
  /** The section on each option's stage, by `stageKey`, so the Checks pane knows when it hides the faces. */
  cutOf: Record<string, Cut | null>;
  /** The body each option's stage shows alone, by `stageKey`, or null for the whole model. */
  bodyOf: Record<string, string | null>;
}

export const stageKey = (briefId: string, slot: number) => `${briefId}:${String(slot)}`;

export type ViewAction =
  | { type: "brief"; briefId: string }
  | { type: "slot"; briefId: string; slot: number }
  | { type: "revision"; key: string; n: number | null }
  | { type: "cut"; key: string; cut: Cut | null }
  | { type: "body"; key: string; body: string | null };

export const viewStart: View = { briefId: null, slotOf: {}, revisionOf: {}, cutOf: {}, bodyOf: {} };

export function viewReducer(view: View, action: ViewAction): View {
  switch (action.type) {
    case "brief":
      return { ...view, briefId: action.briefId };
    case "slot":
      return {
        ...view,
        slotOf: { ...view.slotOf, [action.briefId]: action.slot },
      };
    case "revision":
      return {
        ...view,
        revisionOf: { ...view.revisionOf, [action.key]: action.n },
      };
    case "cut":
      return { ...view, cutOf: { ...view.cutOf, [action.key]: action.cut } };
    case "body":
      return { ...view, bodyOf: { ...view.bodyOf, [action.key]: action.body } };
  }
}
