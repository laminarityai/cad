import { openStream, request } from "./client";
import type { ConversationCreated, ConversationView, Event, MessageSent, Picked, PersonStop } from "@/api/types";
import { sleep } from "@/lib/sleep";
import { FrameReader } from "./sse";

export type Link = "connecting" | "live" | "reconnecting" | "signed_out" | "not_found";

export interface Follower {
  onEvent(seq: number, event: Event): void;
  onLink(link: Link): void;
}

export type Unfollow = () => void;

export interface ChatApi {
  create(projectId?: string): Promise<ConversationCreated>;
  read(conversationId: string): Promise<ConversationView>;
  send(conversationId: string, text: string, selection?: Picked): Promise<MessageSent>;
  stop(runId: string): Promise<PersonStop>;
  /** Every event after `after`, then each new one as it is said. */
  follow(conversationId: string, after: number, handlers: Follower): Unfollow;
}

const RETRY_MS = 1000;
const EVENT_KINDS: ReadonlySet<string> = new Set<Event["kind"]>(["user", "driver", "agent", "tool_call", "tool_result", "web_search", "web_search_result", "stop_report", "turn_failed", "turn_ended"]);

/** Not `EventSource`: it hides the status, and the page must tell a conversation that is not in the
 * account (404) from a stream that dropped. */
async function follow(conversationId: string, from: number, handlers: Follower, signal: AbortSignal): Promise<void> {
  let after = from;
  const closed = () => signal.aborted;
  while (!closed()) {
    handlers.onLink(after === from ? "connecting" : "reconnecting");
    try {
      const response = await openStream("/v1/conversations/{conversation_id}/stream", signal, { path: { conversation_id: conversationId }, query: { after } });
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
  create: (projectId) => request("post", "/v1/conversations", { body: projectId === undefined ? {} : { project_id: projectId } }),
  read: (conversation_id) => request("get", "/v1/conversations/{conversation_id}", { path: { conversation_id } }),
  send: (conversation_id, text, selection) =>
    request("post", "/v1/conversations/{conversation_id}/messages", { path: { conversation_id }, body: selection === undefined ? { text } : { text, selection } }),
  stop: (run_id) => request("post", "/v1/auto/{run_id}/stop", { path: { run_id } }),
  follow(conversationId, after, handlers) {
    const controller = new AbortController();
    void follow(conversationId, after, handlers, controller.signal);
    return () => {
      controller.abort();
    };
  },
};
