import { useEffect, useReducer } from "react";
import { NotFound, SignedOut } from "@/api/client";

export type Resource<T> =
  | { status: "loading" }
  | { status: "ok"; data: T }
  | { status: "signed_out" }
  | { status: "not_found" }
  | { status: "error"; message: string };

type Action<T> =
  | { type: "loading" }
  | { type: "done"; data: T }
  | { type: "failed"; error: unknown }
  | { type: "refresh_failed"; error: unknown };

function failed<T>(error: unknown): Resource<T> {
  if (error instanceof SignedOut) return { status: "signed_out" };
  if (error instanceof NotFound) return { status: "not_found" };
  return { status: "error", message: error instanceof Error ? error.message : "the request failed" };
}

function reduce<T>(state: Resource<T>, action: Action<T>): Resource<T> {
  switch (action.type) {
    case "loading":
      return { status: "loading" };
    case "done":
      return { status: "ok", data: action.data };
    case "failed":
      return failed(action.error);
    case "refresh_failed": {
      const next = failed<T>(action.error);
      return state.status === "ok" && next.status === "error" ? state : next;
    }
  }
}

const final = (error: unknown) => error instanceof SignedOut || error instanceof NotFound;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Load once per `key`. With `followMs`, load again that long after each load ends, while the tab is
 * visible, so the data on screen follows the server. A follow-up load that fails for any reason but
 * sign-out or not-found keeps the data on screen, so a server restart does not blank the page. */
export function useResource<T>(load: () => Promise<T>, key: string, followMs?: number): Resource<T> {
  const [state, dispatch] = useReducer(reduce<T>, { status: "loading" });
  useEffect(() => {
    const run = { live: true };
    const live = () => run.live;
    const follow = async () => {
      dispatch({ type: "loading" });
      try {
        const data = await load();
        if (live()) dispatch({ type: "done", data });
      } catch (error) {
        if (live()) dispatch({ type: "failed", error });
        if (final(error)) return;
      }
      while (live() && followMs !== undefined) {
        await sleep(followMs);
        if (!live() || document.hidden) continue;
        try {
          const data = await load();
          if (live()) dispatch({ type: "done", data });
        } catch (error) {
          if (live()) dispatch({ type: "refresh_failed", error });
          if (final(error)) return;
        }
      }
    };
    void follow();
    return () => {
      run.live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` names what `load` closes over
  }, [key, followMs]);
  return state;
}
