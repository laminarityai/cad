import { useCallback, useEffect, useReducer, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { useServices } from "@/app/context";
import type { Mode } from "@/api/types";
import { nextMode } from "@/mode/modes";
import { lastConversation, loadSaved, rememberConversation, save } from "./saved";
import { chatReducer, chatStart, type ChatState } from "./state";

export const REBUILDS: ReadonlySet<string> = new Set(["build_variant", "auto_revise"]);

export interface Conversation {
  state: ChatState;
  send(text: string): Promise<boolean>;
  pick(mode: Mode): Promise<boolean>;
  cycle(): Promise<boolean>;
  stop(): Promise<boolean>;
}

const said = (error: unknown) => (error instanceof Error ? error.message : "the request failed");

export function useConversation(projectId: string, briefId: string, onRebuilt: () => void): Conversation {
  const { chat } = useServices();
  const [params, setParams] = useSearchParams();
  const conversationId = params.get("chat") ?? lastConversation(projectId, briefId);
  const [state, dispatch] = useReducer(chatReducer, conversationId, (id) =>
    chatStart(id, id === null ? null : loadSaved(id)),
  );
  const rebuilt = useRef(onRebuilt);
  const held = useRef(state);
  useEffect(() => {
    rebuilt.current = onRebuilt;
    held.current = state;
  });

  useEffect(() => {
    if (state.conversationId !== conversationId) {
      dispatch({ type: "open", conversationId, saved: conversationId === null ? null : loadSaved(conversationId) });
    }
  }, [conversationId, state.conversationId]);

  useEffect(() => {
    if (conversationId === null) return;
    const settled = loadSaved(conversationId)?.seen ?? 0;
    const calls = new Map<string, string>();
    return chat.follow(conversationId, {
      onEvent: (seq, event) => {
        if (event.kind === "tool_call") calls.set(event.call_id, event.name);
        dispatch({ type: "event", seq, event });
        if (seq > settled && event.kind === "tool_result" && !event.is_error && REBUILDS.has(calls.get(event.call_id) ?? "")) {
          rebuilt.current();
        }
      },
      onLink: (link) => {
        dispatch({ type: "link", link });
      },
    });
  }, [chat, conversationId]);

  useEffect(() => {
    if (state.conversationId !== null && state.conversationId === conversationId) {
      save(state.conversationId, { mode: state.mode, run: state.run, seen: state.seen });
    }
  }, [state.conversationId, conversationId, state.mode, state.run, state.seen]);

  const ensure = useCallback(async (): Promise<string> => {
    if (conversationId !== null) return conversationId;
    const made = await chat.create();
    save(made.conversation_id, { mode: made.mode, run: null, seen: 0 });
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
    (mode: Mode) =>
      attempt(async () => {
        dispatch({ type: "mode", state: await chat.setMode(await ensure(), mode) });
      }),
    [attempt, chat, ensure],
  );

  const cycle = useCallback(() => pick(nextMode(held.current.mode)), [pick]);

  const stop = useCallback(
    () =>
      attempt(async () => {
        const run = held.current.run;
        if (run?.status !== "running") return;
        dispatch({ type: "stopped", stop: await chat.stop(run.runId) });
      }),
    [attempt, chat],
  );

  return { state, send, pick, cycle, stop };
}
