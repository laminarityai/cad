import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import { NotFound, Refused, SignedOut } from "@/api/client";
import { sleep } from "@/lib/sleep";

export type Resource<T> =
  | { status: "loading" }
  | { status: "ok"; data: T; stale?: true }
  | { status: "signed_out" }
  | { status: "not_found" }
  | { status: "error"; message: string; kind: string | null };

type State<T> = Record<string, Resource<T>>;

type Action<T> =
  | { type: "begin"; keys: readonly string[] }
  | { type: "done"; key: string; data: T }
  | { type: "failed"; key: string; error: unknown };

const LOADING = { status: "loading" } as const;

export const said = (error: unknown) => (error instanceof Error ? error.message : "the request failed");

function failed<T>(error: unknown): Resource<T> {
  if (error instanceof SignedOut) return { status: "signed_out" };
  if (error instanceof NotFound) return { status: "not_found" };
  return { status: "error", message: said(error), kind: error instanceof Refused ? error.kind : null };
}

function reduce<T>(state: State<T>, action: Action<T>): State<T> {
  switch (action.type) {
    case "begin":
      return Object.fromEntries(action.keys.map((key) => [key, state[key] ?? LOADING]));
    case "done":
      return { ...state, [action.key]: { status: "ok", data: action.data } };
    case "failed": {
      const before = state[action.key];
      const next = failed<T>(action.error);
      return { ...state, [action.key]: before?.status === "ok" && next.status === "error" ? { ...before, stale: true } : next };
    }
  }
}

const final = (error: unknown) => error instanceof SignedOut || error instanceof NotFound;

export interface Loaded<T> {
  resource: Resource<T>;
  reload: () => void;
}

export interface LoadedSet<T> {
  resources: Readonly<Record<string, Resource<T>>>;
  reload: () => void;
}

/** Load each of `keys` once. With `followMs`, load again that long after each load ends while the tab
 * is visible, and again the moment it becomes visible, so the data on screen follows the server. A
 * load that fails for any reason but sign-out or not-found keeps the data already on screen, marked
 * `stale`, so a server restart does not blank the page and nothing claims the data is current. A key that stays in `keys` keeps its data while the others
 * change; a key that leaves is forgotten. `load` gets a signal that aborts when the keys change or the
 * page leaves. */
export function useResources<T>(keys: readonly string[], load: (key: string, signal: AbortSignal) => Promise<T>, followMs?: number): LoadedSet<T> {
  const joined = JSON.stringify([...new Set(keys)]);
  const [state, dispatch] = useReducer(reduce<T>, {});
  const latest = useRef(load);
  const again = useRef<() => void>(() => undefined);
  useEffect(() => {
    latest.current = load;
  });
  useEffect(() => {
    const own = JSON.parse(joined) as string[];
    const abort = new AbortController();
    let live = true;
    const track = (key: string) => {
      const run = { ended: false, reading: false, queued: false };
      const going = () => live && !run.ended;
      const queued = () => run.queued;
      const once = async () => {
        try {
          const data = await latest.current(key, abort.signal);
          if (going()) dispatch({ type: "done", key, data });
        } catch (error) {
          if (going()) dispatch({ type: "failed", key, error });
          if (final(error)) run.ended = true;
        }
      };
      const readCoalesced = async () => {
        if (!going()) return;
        if (run.reading) {
          run.queued = true;
          return;
        }
        run.reading = true;
        do {
          run.queued = false;
          await once();
        } while (going() && queued());
        run.reading = false;
      };
      const follow = async () => {
        run.reading = true;
        await once();
        run.reading = false;
        if (queued()) await readCoalesced();
        while (going() && followMs !== undefined) {
          await sleep(followMs, abort.signal);
          if (going() && !document.hidden) await readCoalesced();
        }
      };
      return { follow, readCoalesced };
    };
    dispatch({ type: "begin", keys: own });
    const tracked = own.map(track);
    again.current = () => {
      for (const one of tracked) void one.readCoalesced();
    };
    const visible = () => {
      if (!document.hidden && followMs !== undefined) again.current();
    };
    document.addEventListener("visibilitychange", visible);
    for (const one of tracked) void one.follow();
    return () => {
      live = false;
      abort.abort();
      again.current = () => undefined;
      document.removeEventListener("visibilitychange", visible);
    };
  }, [joined, followMs]);
  const reload = useCallback(() => {
    again.current();
  }, []);
  const resources = useMemo(() => Object.fromEntries((JSON.parse(joined) as string[]).map((key) => [key, state[key] ?? LOADING])), [joined, state]);
  return { resources, reload };
}

/** Load once per `key`, and follow it as `useResources` does. */
export function useResource<T>(load: (signal: AbortSignal) => Promise<T>, key: string, followMs?: number): Loaded<T> {
  const { resources, reload } = useResources([key], (_key, signal) => load(signal), followMs);
  return { resource: resources[key] ?? LOADING, reload };
}
