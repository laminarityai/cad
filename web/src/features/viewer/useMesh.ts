import { useEffect, useReducer } from "react";
import { useServices } from "@/app/context";
import type { GeometryRead } from "@/api/types";
import type { Shapes } from "./engine";

export type MeshState =
  | { status: "loading"; lastDrawn: Shapes | null }
  | { status: "ready"; shapes: Shapes }
  | { status: "failed"; reason: string };

const POLL_MS = 250;

interface Held {
  variantId: string;
  state: MeshState;
}

const onScreen = (state: MeshState): Shapes | null =>
  state.status === "ready" ? state.shapes : state.status === "loading" ? state.lastDrawn : null;

function reduce(held: Held, next: Held): Held {
  return next.state.status === "loading" ? { variantId: next.variantId, state: { status: "loading", lastDrawn: onScreen(held.state) } } : next;
}

/** Read one variant's mesh. The view says whether it is stored: a stored mesh is fetched once from its
 * immutable URL. Otherwise the geometry route starts the tessellation and answers pending until it is
 * done, so it is asked again every POLL_MS. */
export function useMesh(variantId: string): MeshState {
  const { api } = useServices();
  const [held, put] = useReducer(reduce, { variantId, state: { status: "loading", lastDrawn: null } });
  useEffect(() => {
    const run = { live: true };
    const live = () => run.live;
    const set = (state: MeshState) => {
      put({ variantId, state });
    };
    let timer: ReturnType<typeof setTimeout> | undefined;
    set({ status: "loading", lastDrawn: null });
    const settle = (read: GeometryRead) => {
      if (read.kind === "tessellated") set({ status: "ready", shapes: read.shapes });
      else if (read.kind === "failed") set({ status: "failed", reason: read.reason });
      else timer = setTimeout(() => void ask(), POLL_MS);
    };
    const ask = async () => {
      try {
        const read = await api.geometry(variantId);
        if (live()) settle(read);
      } catch (error) {
        fail(error);
      }
    };
    const fail = (error: unknown) => {
      if (live()) set({ status: "failed", reason: error instanceof Error ? error.message : "The mesh did not load." });
    };
    const look = async () => {
      try {
        const view = await api.view(variantId);
        if (!live()) return;
        if (view.mesh_url !== null) {
          const mesh = await api.mesh(view.mesh_url);
          if (live()) set({ status: "ready", shapes: mesh.shapes });
        } else if (view.mesh === "failed") {
          set({ status: "failed", reason: "The mesh could not be made." });
        } else {
          await ask();
        }
      } catch (error) {
        fail(error);
      }
    };
    void look();
    return () => {
      run.live = false;
      clearTimeout(timer);
    };
  }, [api, variantId]);
  return held.variantId === variantId ? held.state : { status: "loading", lastDrawn: onScreen(held.state) };
}
