import { useCallback, useEffect, useRef, useState } from "react";
import { useServices } from "@/app/context";
import type { ConversationView, Mode } from "@/api/types";
import { said, useResource } from "@/state/resource";
import { nextMode } from "./modes";
import { viewOf, type RunView } from "./run";

export const CONVERSATION_FOLLOW_MS = 3000;

export interface Auto {
  mode: Mode | null;
  run: RunView | null;
  problem: string | null;
  pick(mode: Mode): Promise<void>;
  cycle(): Promise<void>;
  stop(): Promise<void>;
  reload(): void;
}

function runToShow(view: ConversationView | null): RunView | null {
  if (view?.run == null) return null;
  const run = viewOf(view.run);
  return view.mode === "auto" && run.status === "stopped" ? null : run;
}

/** The conversation's mode and Auto run, as the server holds them. Another tab's switch or Stop shows
 * within one follow, and the chat asks for a read at once when an Auto tool returns or a run reports. */
export function useAuto(conversationId: string): Auto {
  const { chat } = useServices();
  const { resource, reload } = useResource(() => chat.read(conversationId), `conversation:${conversationId}`, CONVERSATION_FOLLOW_MS);
  const view = resource.status === "ok" ? resource.data : null;
  const mode = view?.mode ?? null;
  const run = runToShow(view);
  const [problem, setProblem] = useState<string | null>(null);
  const held = useRef({ mode, run });
  useEffect(() => {
    held.current = { mode, run };
  });

  const attempt = useCallback(async (body: () => Promise<void>) => {
    try {
      await body();
      setProblem(null);
    } catch (error) {
      setProblem(said(error));
    }
  }, []);

  const pick = useCallback(
    (next: Mode) =>
      attempt(async () => {
        await chat.setMode(conversationId, next);
        reload();
      }),
    [attempt, chat, conversationId, reload],
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

  return { mode, run, problem, pick, cycle, stop, reload };
}
