import { useCallback, useEffect, useReducer } from "react";
import { NotFound, SignedOut } from "@/api/client";

export type Resource<T> =
  | { status: "loading" }
  | { status: "ok"; data: T }
  | { status: "signed_out" }
  | { status: "not_found" }
  | { status: "error"; message: string };

type Action<T> = { type: "loading" } | { type: "done"; data: T } | { type: "failed"; error: unknown };

function reduce<T>(_: Resource<T>, action: Action<T>): Resource<T> {
  switch (action.type) {
    case "loading":
      return { status: "loading" };
    case "done":
      return { status: "ok", data: action.data };
    case "failed":
      if (action.error instanceof SignedOut) return { status: "signed_out" };
      if (action.error instanceof NotFound) return { status: "not_found" };
      return {
        status: "error",
        message: action.error instanceof Error ? action.error.message : "the request failed",
      };
  }
}

/** Load once per `key`, and again when `reload` runs. A reload keeps the data on screen. */
export function useResource<T>(load: () => Promise<T>, key: string): [Resource<T>, () => void] {
  const [state, dispatch] = useReducer(reduce<T>, { status: "loading" });
  const run = useCallback(
    (quiet: boolean) => {
      let live = true;
      if (!quiet) dispatch({ type: "loading" });
      load().then(
        (data) => {
          if (live) dispatch({ type: "done", data });
        },
        (error: unknown) => {
          if (live) dispatch({ type: "failed", error });
        },
      );
      return () => {
        live = false;
      };
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` names what `load` closes over
    [key],
  );
  useEffect(() => run(false), [run]);
  return [state, () => void run(true)];
}
