import { useEffect, useReducer } from "react";
import { useServices } from "@/app/context";
import type { GeometryRead } from "@/api/types";
import type { Shapes } from "./engine";

export type MeshState =
  | { status: "loading" }
  | { status: "ready"; shapes: Shapes }
  | { status: "failed"; reason: string };

const POLL_MS = 1000;

function reduce(_: MeshState, next: MeshState): MeshState {
  return next;
}

/** Read one variant's mesh. The view says whether it is stored: a stored mesh is fetched once from its
 * immutable URL. Otherwise the geometry route starts the tessellation and answers pending until it is
 * done, so it is asked again every second. */
export function useMesh(variantId: string): MeshState {
  const { api } = useServices();
  const [state, set] = useReducer(reduce, { status: "loading" });
  useEffect(() => {
    const run = { live: true };
    const live = () => run.live;
    let timer: ReturnType<typeof setTimeout> | undefined;
    set({ status: "loading" });
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
  return state;
}
