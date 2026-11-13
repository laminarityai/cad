import type { RunView } from "@/features/auto/run";
import type { ChatState } from "./state";

export type Working = { kind: "turn" } | { kind: "tool"; name: string } | { kind: "auto" };

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

export function workingOf(chat: Pick<ChatState, "lines" | "turn">, run: RunView | null): Working | null {
  if (chat.turn === "running") {
    const open = chat.lines.findLast((line) => line.kind === "tool" && line.result === null);
    return open?.kind === "tool" ? { kind: "tool", name: open.name } : { kind: "turn" };
  }
  return run?.status === "running" ? { kind: "auto" } : null;
}

export function workingLabel(working: Working): string {
  switch (working.kind) {
    case "tool":
      return NOW[working.name] ?? "Working";
    case "auto":
      return "Auto run working";
    case "turn":
      return "Working";
  }
}
