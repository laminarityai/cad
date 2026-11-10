import type { ConversationState, Event, Mode, PersonStop } from "@/api/types";
import { AUTO_TOOLS, autoRunOf, isStopKind, stoppedBy, viewOf, type RunView } from "@/mode/run";
import type { Link } from "./api";

export type Line =
  | { seq: number; kind: "user" | "agent" | "driver"; text: string }
  | { seq: number; kind: "tool"; callId: string; name: string; input: Record<string, unknown>; result: { text: string; isError: boolean } | null }
  | { seq: number; kind: "stop_report"; runId: string; reason: string; report: string }
  | { seq: number; kind: "failed"; message: string };

export interface ChatState {
  conversationId: string | null;
  lines: readonly Line[];
  seen: number;
  settled: number;
  turn: "idle" | "running";
  mode: Mode | null;
  run: RunView | null;
  link: Link;
  problem: string | null;
}

export interface Saved {
  mode: Mode | null;
  run: RunView | null;
  seen: number;
}

export type ChatAction =
  | { type: "open"; conversationId: string | null; saved: Saved | null }
  | { type: "event"; seq: number; event: Event }
  | { type: "link"; link: Link }
  | { type: "mode"; state: ConversationState }
  | { type: "stopped"; stop: PersonStop }
  | { type: "problem"; message: string | null };

export function chatStart(conversationId: string | null, saved: Saved | null): ChatState {
  return {
    conversationId,
    lines: [],
    seen: 0,
    settled: saved?.seen ?? 0,
    turn: "idle",
    mode: saved?.mode ?? null,
    run: saved?.run ?? null,
    link: "connecting",
    problem: null,
  };
}

function withEvent(lines: readonly Line[], seq: number, event: Event): readonly Line[] {
  switch (event.kind) {
    case "user":
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

/** ADR-0010: every stop of a run moves its conversation from Auto to Design. */
function afterStop(state: ChatState, run: RunView): Pick<ChatState, "mode" | "run"> {
  return { mode: state.mode === "auto" ? "design" : state.mode, run };
}

function conversationAfter(state: ChatState, lines: readonly Line[], event: Event): Pick<ChatState, "mode" | "run"> {
  if (event.kind === "tool_result" && !event.is_error) {
    const call = lines.find((line) => line.kind === "tool" && line.callId === event.call_id);
    const run = call?.kind === "tool" && AUTO_TOOLS.has(call.name) ? autoRunOf(event.text) : null;
    if (run === null) return state;
    const view = viewOf(run);
    return view.status === "stopped" ? afterStop(state, view) : { mode: state.mode, run: view };
  }
  if (event.kind === "stop_report" && isStopKind(event.reason)) {
    const held = state.run;
    if (held?.runId === event.run_id && held.status === "stopped") return state;
    const view: RunView = {
      runId: event.run_id,
      status: "stopped",
      revisions: held?.revisions ?? 0,
      reason: event.reason,
      note: "",
      report: event.report,
    };
    return afterStop(state, view);
  }
  return state;
}

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "open":
      return chatStart(action.conversationId, action.saved);
    case "event": {
      if (action.seq <= state.seen) return state;
      const lines = withEvent(state.lines, action.seq, action.event);
      const turn = action.event.kind === "user" ? "running" : action.event.kind === "turn_ended" ? "idle" : state.turn;
      const moved = action.seq > state.settled ? conversationAfter(state, lines, action.event) : state;
      return { ...state, lines, seen: action.seq, turn, mode: moved.mode, run: moved.run };
    }
    case "link":
      return { ...state, link: action.link };
    case "mode": {
      const left = state.run?.status === "running" && action.state.mode !== "auto";
      return { ...state, mode: action.state.mode, run: left && state.run ? stoppedBy(state.run) : state.run, problem: null };
    }
    case "stopped":
      return { ...state, mode: action.stop.conversation.mode, run: viewOf(action.stop.run), problem: null };
    case "problem":
      return { ...state, problem: action.message };
  }
}
