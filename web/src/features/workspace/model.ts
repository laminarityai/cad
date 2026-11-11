import type { Api } from "@/api/client";
import type { BriefView, ConfirmationCard, ContextPartView, MemberView, Outcome, VariantSetView } from "@/api/types";

export type BriefState = "drafting" | "waiting" | "building" | "ready";

export interface Revision {
  n: number;
  variantId: string;
  at: string;
}

export interface Slot {
  slot: number;
  label: string;
  differs: string;
  revisions: Revision[];
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
  name: string;
  size: string;
  state: Outcome;
}

export type Confirmation = ConfirmationCard | null;

export interface Workspace {
  projectId: string;
  title: string;
  briefs: Brief[];
  confirmation: Confirmation;
  parts: Part[];
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
  }));
}

function stateOf(brief: BriefView, confirmation: Confirmation, slots: Slot[]): BriefState {
  if (confirmation?.items.some((item) => item.brief_id === brief.brief_id)) return "waiting";
  if (brief.confirmed_proposal === null && slots.length === 0) return "drafting";
  return slots.length === 0 ? "building" : "ready";
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
    fits: parts.filter((one) => one.brief_id === brief.brief_id && one.outcome === "confirmed").map((one) => ({ name: one.name, variantId: one.variant_id })),
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
    parts: project.context_parts.map((one) => ({
      name: one.name,
      size: mm(one.size_mm),
      state: one.outcome,
    })),
    conversationId: conversation.conversation_id,
  };
}

export interface View {
  briefId: string | null;
  slotOf: Record<string, number>;
  revisionOf: Record<string, number | null>;
}

export type ViewAction = { type: "brief"; briefId: string } | { type: "slot"; briefId: string; slot: number } | { type: "revision"; key: string; n: number | null };

export const viewStart: View = { briefId: null, slotOf: {}, revisionOf: {} };

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
  }
}
