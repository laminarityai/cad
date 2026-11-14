import { AUTO_TOOLS, type RunView } from "@/features/auto/run";
import type { ChatState, Line } from "./state";

export type Working = { kind: "turn"; briefId: string | null } | { kind: "tool"; name: string; briefId: string | null };

const NOW: Record<string, string> = {
  build_variant: "Building an option",
  auto_revise: "Building the next revision",
  score_variant: "Checking an option",
  propose_requirements: "Writing the requirements",
  propose_context_part: "Adding a part to fit",
  create_brief: "Starting the part",
  ask_to_confirm: "Waiting for your Confirm",
  submit_research: "Researching a value",
  write_check: "Writing a check",
  search_knowledge: "Looking it up",
  web_search: "Searching the web",
  ask_questions: "Writing a few questions",
};

export const nowLabel = (name: string): string => NOW[name] ?? "Working";

type Call = Extract<Line, { kind: "tool" }>;

type Turn = Pick<ChatState, "lines" | "turn" | "turnStartSeq" | "link">;

export const STALLED = "The server is not answering. The page is reconnecting.";

/** A turn runs, but the stream dropped, so nothing on the page knows whether it still moves. */
export const stalledOf = (chat: Turn): boolean => chat.turn === "running" && chat.link === "reconnecting";

function created(call: Call): string | null {
  if (call.name !== "create_brief" || call.result === null || call.result.isError) return null;
  try {
    const said = (JSON.parse(call.result.text) as { brief_id?: unknown } | null)?.brief_id;
    return typeof said === "string" ? said : null;
  } catch {
    return null;
  }
}

function briefOf(call: Call, runBrief: string | null): string | null {
  if (typeof call.input.brief_id === "string") return call.input.brief_id;
  const made = created(call);
  if (made !== null) return made;
  return AUTO_TOOLS.has(call.name) ? runBrief : null;
}

export function workingOf(chat: Turn, run: RunView | null): Working | null {
  if (chat.turn !== "running" || stalledOf(chat)) return null;
  const runBrief = run?.status === "running" ? run.briefId : null;
  const calls = chat.lines.filter((line): line is Call => line.kind === "tool" && line.seq > (chat.turnStartSeq ?? 0));
  const open = calls.find((call) => call.result === null);
  if (open) return { kind: "tool", name: open.name, briefId: briefOf(open, runBrief) };
  return { kind: "turn", briefId: calls.map((call) => briefOf(call, runBrief)).findLast((one) => one !== null) ?? null };
}

export function workingLabel(working: Working): string {
  return working.kind === "tool" ? nowLabel(working.name) : "Working";
}

export function sinceOf(chat: Pick<ChatState, "turn" | "turnStartSeq">, sent: { seq: number; at: number } | null): number | null {
  return chat.turn === "running" && sent !== null && sent.seq === chat.turnStartSeq ? sent.at : null;
}
