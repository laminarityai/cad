import type { Event } from "@/api/types";
import type { Link } from "@/api/chat";

export type Line =
  | { seq: number; kind: "user"; text: string; selection: string | null }
  | { seq: number; kind: "agent" | "driver"; text: string }
  | { seq: number; kind: "tool"; callId: string; name: string; input: Record<string, unknown>; result: { text: string; isError: boolean } | null }
  | { seq: number; kind: "stop_report"; runId: string; reason: string; report: string }
  | { seq: number; kind: "failed"; message: string };

export interface ChatState {
  conversationId: string | null;
  lines: readonly Line[];
  seen: number;
  turn: "idle" | "running";
  link: Link;
  problem: string | null;
}

export type ChatAction =
  | { type: "open"; conversationId: string | null }
  | { type: "event"; seq: number; event: Event }
  | { type: "link"; link: Link }
  | { type: "problem"; message: string | null };

export function chatStart(conversationId: string | null): ChatState {
  return { conversationId, lines: [], seen: 0, turn: "idle", link: "connecting", problem: null };
}

function withEvent(lines: readonly Line[], seq: number, event: Event): readonly Line[] {
  switch (event.kind) {
    case "user":
      return [...lines, { seq, kind: "user", text: event.text, selection: event.selection?.summary ?? null }];
    case "agent":
    case "driver":
      return [...lines, { seq, kind: event.kind, text: event.text }];
    case "tool_call":
      return [...lines, { seq, kind: "tool", callId: event.call_id, name: event.name, input: event.input, result: null }];
    case "tool_result":
      return lines.map((line) =>
        line.kind === "tool" && line.callId === event.call_id ? { ...line, result: { text: event.text, isError: event.is_error } } : line,
      );
    case "stop_report":
      return [...lines, { seq, kind: "stop_report", runId: event.run_id, reason: event.reason, report: event.report }];
    case "turn_failed":
      return [...lines, { seq, kind: "failed", message: event.message }];
    case "turn_ended":
      return lines;
  }
}

/** A turn starts with the person's message or with the server telling the agent the person answered the page. */
const STARTS_TURN: ReadonlySet<Event["kind"]> = new Set(["user", "driver"]);

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "open":
      return chatStart(action.conversationId);
    case "event": {
      if (action.seq <= state.seen) return state;
      const lines = withEvent(state.lines, action.seq, action.event);
      const turn = STARTS_TURN.has(action.event.kind) ? "running" : action.event.kind === "turn_ended" ? "idle" : state.turn;
      return { ...state, lines, seen: action.seq, turn };
    }
    case "link":
      return { ...state, link: action.link };
    case "problem":
      return { ...state, problem: action.message };
  }
}
