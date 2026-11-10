import { useCallback, useEffect, useReducer, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { useServices } from "@/app/context";
import type { ConversationView, Mode } from "@/api/types";
import { nextMode } from "@/mode/modes";
import { AUTO_TOOLS, viewOf, type RunView } from "@/mode/run";
import { useResource } from "@/state/resource";
import { useVisible } from "@/state/visible";
import { lastConversation, rememberConversation } from "./saved";
import { chatReducer, chatStart, type ChatState } from "./state";

export const REBUILDS: ReadonlySet<string> = new Set(["build_variant", "auto_revise"]);

export const CONVERSATION_FOLLOW_MS = 3000;

export interface Conversation {
  state: ChatState;
  mode: Mode | null;
  run: RunView | null;
  send(text: string): Promise<boolean>;
  pick(mode: Mode): Promise<boolean>;
  cycle(): Promise<boolean>;
  stop(): Promise<boolean>;
}

const said = (error: unknown) => (error instanceof Error ? error.message : "the request failed");

function runToShow(view: ConversationView | null): RunView | null {
  if (view?.run == null) return null;
  const run = viewOf(view.run);
  return view.mode === "auto" && run.status === "stopped" ? null : run;
}

export function useConversation(projectId: string, briefId: string, onRebuilt: () => void): Conversation {
  const { chat } = useServices();
  const [params, setParams] = useSearchParams();
  const conversationId = params.get("chat") ?? lastConversation(projectId, briefId);
  const [state, dispatch] = useReducer(chatReducer, conversationId, chatStart);
  const { resource, reload } = useResource(
    () => (conversationId === null ? Promise.resolve(null) : chat.read(conversationId)),
    `conversation:${conversationId ?? ""}`,
    conversationId === null ? undefined : CONVERSATION_FOLLOW_MS,
  );
  const view = resource.status === "ok" ? resource.data : null;
  const mode = view?.mode ?? null;
  const run = runToShow(view);
  const visible = useVisible();
  const rebuilt = useRef(onRebuilt);
  const held = useRef({ mode, run });
  const followed = useRef({ conversationId, seen: 0, calls: new Map<string, string>() });
  useEffect(() => {
    rebuilt.current = onRebuilt;
    held.current = { mode, run };
  });

  useEffect(() => {
    if (state.conversationId !== conversationId) dispatch({ type: "open", conversationId });
  }, [conversationId, state.conversationId]);

  useEffect(() => {
    if (conversationId === null || !visible) return;
    if (followed.current.conversationId !== conversationId) {
      followed.current = { conversationId, seen: 0, calls: new Map() };
    }
    const { calls } = followed.current;
    return chat.follow(conversationId, followed.current.seen, {
      onEvent: (seq, event) => {
        followed.current.seen = Math.max(followed.current.seen, seq);
        if (event.kind === "tool_call") calls.set(event.call_id, event.name);
        dispatch({ type: "event", seq, event });
        const tool = event.kind === "tool_result" && !event.is_error ? (calls.get(event.call_id) ?? "") : "";
        if (REBUILDS.has(tool)) rebuilt.current();
        if (AUTO_TOOLS.has(tool) || event.kind === "stop_report" || event.kind === "turn_ended") reload();
      },
      onLink: (link) => {
        dispatch({ type: "link", link });
      },
    });
  }, [chat, conversationId, reload, visible]);

  const ensure = useCallback(async (): Promise<string> => {
    if (conversationId !== null) return conversationId;
    const made = await chat.create(projectId, briefId);
    rememberConversation(projectId, briefId, made.conversation_id);
    setParams(
      (now) => {
        const next = new URLSearchParams(now);
        next.set("chat", made.conversation_id);
        return next;
      },
      { replace: true },
    );
    return made.conversation_id;
  }, [chat, conversationId, projectId, briefId, setParams]);

  const attempt = useCallback(
    async (body: () => Promise<void>): Promise<boolean> => {
      try {
        await body();
        dispatch({ type: "problem", message: null });
        return true;
      } catch (error) {
        dispatch({ type: "problem", message: said(error) });
        return false;
      }
    },
    [],
  );

  const send = useCallback(
    (text: string) =>
      attempt(async () => {
        await chat.send(await ensure(), text);
      }),
    [attempt, chat, ensure],
  );

  const pick = useCallback(
    (next: Mode) =>
      attempt(async () => {
        await chat.setMode(await ensure(), next);
        reload();
      }),
    [attempt, chat, ensure, reload],
  );

  const cycle = useCallback(() => pick(nextMode(held.current.mode)), [pick]);

  const stop = useCallback(
    () =>
      attempt(async () => {
        const now = held.current.run;
        if (now?.status !== "running") return;
        await chat.stop(now.runId);
        reload();
      }),
    [attempt, chat, reload],
  );

  return { state, mode, run, send, pick, cycle, stop };
}
