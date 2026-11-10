import { requestJson } from "@/api/client";
import type { ConversationCreated, ConversationState, Event, Mode, MessageSent, PersonStop } from "@/api/types";
import { FrameReader } from "./sse";

export type Link = "connecting" | "live" | "reconnecting" | "signed_out" | "not_found";

export interface Follower {
  onEvent(seq: number, event: Event): void;
  onLink(link: Link): void;
}

export interface ChatApi {
  create(): Promise<ConversationCreated>;
  send(conversationId: string, text: string): Promise<MessageSent>;
  setMode(conversationId: string, mode: Mode): Promise<ConversationState>;
  stop(runId: string): Promise<PersonStop>;
  /** Replays the conversation's transcript and follows it. Returns the function that closes it. */
  follow(conversationId: string, handlers: Follower): () => void;
}

const enc = encodeURIComponent;
const RETRY_MS = 1000;
const EVENT_KINDS: ReadonlySet<string> = new Set<Event["kind"]>([
  "user",
  "driver",
  "agent",
  "tool_call",
  "tool_result",
  "stop_report",
  "turn_failed",
  "turn_ended",
]);

const sleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((done) => {
    const timer = setTimeout(done, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      done();
    });
  });

/** Not `EventSource`: it hides the status, and the page must tell a conversation that is not in the
 * account (404) from a stream that dropped. */
async function follow(conversationId: string, handlers: Follower, signal: AbortSignal): Promise<void> {
  let after = 0;
  const closed = () => signal.aborted;
  while (!closed()) {
    handlers.onLink(after === 0 ? "connecting" : "reconnecting");
    try {
      const response = await fetch(`/v1/conversations/${enc(conversationId)}/stream?after=${String(after)}`, {
        credentials: "same-origin",
        headers: { accept: "text/event-stream" },
        signal,
      });
      if (response.status === 401 || response.status === 404) {
        handlers.onLink(response.status === 401 ? "signed_out" : "not_found");
        return;
      }
      if (!response.ok || response.body === null) throw new Error(`HTTP ${String(response.status)}`);
      handlers.onLink("live");
      const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
      const frames = new FrameReader();
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        for (const frame of frames.push(value)) {
          const seq = Number(frame.id);
          if (!EVENT_KINDS.has(frame.event) || !Number.isInteger(seq)) continue;
          after = Math.max(after, seq);
          handlers.onEvent(seq, JSON.parse(frame.data) as Event);
        }
      }
    } catch {
      if (closed()) return;
    }
    handlers.onLink("reconnecting");
    await sleep(RETRY_MS, signal);
  }
}

export const httpChat: ChatApi = {
  create: () => requestJson("POST", "/v1/conversations", {}),
  send: (conversationId, text) => requestJson("POST", `/v1/conversations/${enc(conversationId)}/messages`, { text }),
  setMode: (conversationId, mode) => requestJson("PUT", `/v1/conversations/${enc(conversationId)}/mode`, { mode }),
  stop: (runId) => requestJson("POST", `/v1/auto/${enc(runId)}/stop`),
  follow(conversationId, handlers) {
    const controller = new AbortController();
    void follow(conversationId, handlers, controller.signal);
    return () => {
      controller.abort();
    };
  },
};
