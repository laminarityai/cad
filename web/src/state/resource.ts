import { useCallback, useEffect, useReducer, useRef } from "react";
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

export interface Loaded<T> {
  resource: Resource<T>;
  /** Read again now. Calls that land while a read is out make one more read after it, not one each. */
  reload: () => void;
}

/** Load once per `key`. With `followMs`, load again that long after each load ends while the tab is
 * visible, and again the moment it becomes visible, so the data on screen follows the server. A
 * follow-up load that fails for any reason but sign-out or not-found keeps the data on screen, so a
 * server restart does not blank the page. */
export function useResource<T>(load: () => Promise<T>, key: string, followMs?: number): Loaded<T> {
  const [resource, dispatch] = useReducer(reduce<T>, { status: "loading" });
  const latest = useRef(load);
  const again = useRef<() => void>(() => undefined);
  useEffect(() => {
    latest.current = load;
  });
  useEffect(() => {
    const run = { live: true, ended: false, reading: false, queued: false };
    const live = () => run.live && !run.ended;
    const queued = () => run.queued;
    const once = async (first: boolean) => {
      try {
        const data = await latest.current();
        if (live()) dispatch({ type: "done", data });
      } catch (error) {
        if (live()) dispatch(first ? { type: "failed", error } : { type: "refresh_failed", error });
        if (final(error)) run.ended = true;
      }
    };
    const reread = async () => {
      if (!live()) return;
      if (run.reading) {
        run.queued = true;
        return;
      }
      run.reading = true;
      do {
        run.queued = false;
        await once(false);
      } while (live() && queued());
      run.reading = false;
    };
    again.current = () => void reread();
    const follow = async () => {
      dispatch({ type: "loading" });
      run.reading = true;
      await once(true);
      run.reading = false;
      if (queued()) await reread();
      while (live() && followMs !== undefined) {
        await sleep(followMs);
        if (live() && !document.hidden) await reread();
      }
    };
    const visible = () => {
      if (!document.hidden && followMs !== undefined) void reread();
    };
    document.addEventListener("visibilitychange", visible);
    void follow();
    return () => {
      run.live = false;
      again.current = () => undefined;
      document.removeEventListener("visibilitychange", visible);
    };
  }, [key, followMs]);
  const reload = useCallback(() => {
    again.current();
  }, []);
  return { resource, reload };
}
