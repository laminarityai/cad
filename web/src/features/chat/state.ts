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
  turnStartSeq: number | null;
  link: Link;
  problem: string | null;
  /** The reply text heard so far, which the next stored event replaces. */
  partial: string | null;
}

export type ChatAction =
  | { type: "open"; conversationId: string | null }
  | { type: "event"; seq: number; event: Event }
  | { type: "partial"; text: string }
  | { type: "link"; link: Link }
  | { type: "problem"; message: string | null };

export function chatStart(conversationId: string | null): ChatState {
  return { conversationId, lines: [], seen: 0, turn: "idle", turnStartSeq: null, link: "connecting", problem: null, partial: null };
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
    case "web_search":
      return [...lines, { seq, kind: "tool", callId: event.call_id, name: "web_search", input: { query: event.query }, result: null }];
    case "web_search_result": {
      const text = event.error ?? event.pages.map((page) => `${page.title} · ${page.url}`).join("\n");
      return lines.map((line) => (line.kind === "tool" && line.callId === event.call_id ? { ...line, result: { text, isError: event.error !== null } } : line));
    }
    case "stop_report":
      return [...lines, { seq, kind: "stop_report", runId: event.run_id, reason: event.reason, report: event.report }];
    case "turn_failed":
      return [...lines, { seq, kind: "failed", message: event.message }];
    case "turn_ended":
      return lines;
  }
}

const STARTS_TURN: ReadonlySet<Event["kind"]> = new Set(["user", "driver"]);

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "open":
      return chatStart(action.conversationId);
    case "event": {
      if (action.seq <= state.seen) return state;
      const lines = withEvent(state.lines, action.seq, action.event);
      const next = { ...state, lines, seen: action.seq, partial: null };
      if (action.event.kind === "turn_ended") return { ...next, turn: "idle", turnStartSeq: null };
      if (state.turn === "idle" && STARTS_TURN.has(action.event.kind)) return { ...next, turn: "running", turnStartSeq: action.seq };
      return next;
    }
    case "partial":
      return { ...state, partial: action.text };
    case "link":
      return { ...state, link: action.link, partial: action.link === "live" ? state.partial : null };
    case "problem":
      return { ...state, problem: action.message };
  }
}

/** The lines to draw: the stored ones, then the reply heard so far as the agent's newest line. */
export function shownLines(state: ChatState): readonly Line[] {
  return state.partial === null ? state.lines : [...state.lines, { seq: state.seen + 0.5, kind: "agent", text: state.partial }];
}
