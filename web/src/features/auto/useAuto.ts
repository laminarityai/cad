import { useCallback, useEffect, useRef, useState } from "react";
import { useServices } from "@/app/context";
import type { ConversationView } from "@/api/types";
import { said, useResource } from "@/state/resource";
import { viewOf, type RunView } from "./run";

export const CONVERSATION_FOLLOW_MS = 3000;

export interface Auto {
  run: RunView | null;
  /** The brief the conversation was started on, if it was started on one. */
  briefId: string | null;
  problem: string | null;
  stop(): Promise<void>;
  reload(): void;
}

function runToShow(view: ConversationView | null): RunView | null {
  if (view?.run == null) return null;
  const run = viewOf(view.run);
  const holds = view.stopped_run === run.runId || view.auto_run === run.runId;
  return run.status === "running" || holds ? run : null;
}

export function useAuto(conversationId: string): Auto {
  const { chat } = useServices();
  const { resource, reload } = useResource(() => chat.read(conversationId), `conversation:${conversationId}`, CONVERSATION_FOLLOW_MS);
  const view = resource.status === "ok" ? resource.data : null;
  const run = runToShow(view);
  const [problem, setProblem] = useState<string | null>(null);
  const held = useRef(run);
  useEffect(() => {
    held.current = run;
  });

  const stop = useCallback(async () => {
    const now = held.current;
    if (now?.status !== "running") return;
    try {
      await chat.stop(now.runId);
      setProblem(null);
    } catch (error) {
      setProblem(said(error));
    }
    reload();
  }, [chat, reload]);

  return { run, briefId: view?.brief_id ?? null, problem, stop, reload };
}
