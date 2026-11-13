import type { RunView } from "@/features/auto/run";
import type { ChatState, Line } from "./state";

export type Working = { kind: "turn"; briefId: string | null } | { kind: "tool"; name: string; briefId: string | null } | { kind: "checks"; briefId: string };

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
};

export const nowLabel = (name: string): string => NOW[name] ?? "Working";

type Call = Extract<Line, { kind: "tool" }>;

const briefOf = (call: Call): string | null => (typeof call.input.brief_id === "string" ? call.input.brief_id : null);

export function workingOf(chat: Pick<ChatState, "lines" | "turn" | "turnStartSeq">, run: RunView | null, conversationBrief: string | null): Working | null {
  const runBrief = run?.status === "running" ? run.briefId : null;
  if (chat.turn === "running") {
    const calls = chat.lines.filter((line): line is Call => line.kind === "tool" && line.seq > (chat.turnStartSeq ?? 0));
    const open = calls.find((call) => call.result === null);
    const briefId = (open ? briefOf(open) : null) ?? calls.map(briefOf).findLast((one) => one !== null) ?? runBrief ?? conversationBrief;
    return open ? { kind: "tool", name: open.name, briefId } : { kind: "turn", briefId };
  }
  return run?.status === "running" && run.settling ? { kind: "checks", briefId: run.briefId } : null;
}

export function workingLabel(working: Working): string {
  switch (working.kind) {
    case "tool":
      return nowLabel(working.name);
    case "checks":
      return "Auto run waiting on checks";
    case "turn":
      return "Working";
  }
}

export function sinceOf(chat: Pick<ChatState, "turn" | "turnStartSeq">, sent: { seq: number; at: number } | null): number | null {
  return chat.turn === "running" && sent !== null && sent.seq === chat.turnStartSeq ? sent.at : null;
}
