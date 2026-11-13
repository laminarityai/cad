import { useState } from "react";
import { useServices } from "@/app/context";
import type { Api } from "@/api/client";
import { sleep } from "@/lib/sleep";
import { said, useResources } from "@/state/resource";
import type { Shapes } from "./engine";
import type { Topology } from "./readout";

export type MeshState =
  | { status: "loading"; lastDrawn: Shapes | null }
  | { status: "ready"; shapes: Shapes; topology: Topology }
  | { status: "failed"; reason: string };

const POLL_MS = 250;

/** The view says whether the mesh is stored: a stored mesh is fetched once from its immutable URL.
 * Otherwise the geometry route starts the tessellation and answers pending until it is done, so it is
 * asked again every POLL_MS until `signal` aborts. A refusal is rethrown as a plain error so the page
 * shows the server's words, whatever kind it was. */
async function readMesh(api: Api, variantId: string, signal: AbortSignal): Promise<{ shapes: Shapes; topology: Topology }> {
  try {
    const view = await api.view(variantId);
    if (view.mesh_url !== null) {
      const { shapes, topology } = await api.mesh(view.mesh_url);
      return { shapes, topology };
    }
    if (view.mesh === "failed") throw new Error("The mesh could not be made.");
    for (;;) {
      const read = await api.geometry(variantId);
      if (read.kind === "tessellated") return { shapes: read.shapes, topology: read.topology };
      if (read.kind === "failed") throw new Error(read.reason);
      await sleep(POLL_MS, signal);
      signal.throwIfAborted();
    }
  } catch (error) {
    throw new Error(said(error), { cause: error });
  }
}

export function useMesh(variantId: string): MeshState;
export function useMesh(variantId: string | null): MeshState | null;
export function useMesh(variantId: string | null): MeshState | null {
  const { api } = useServices();
  const { resources } = useResources(variantId === null ? [] : [variantId], (id, signal) => readMesh(api, id, signal));
  const [drawn, setDrawn] = useState<Shapes | null>(null);
  const resource = variantId === null ? null : (resources[variantId] ?? { status: "loading" });
  const onScreen = resource?.status === "ok" ? resource.data.shapes : resource?.status === "loading" ? drawn : null;
  if (onScreen !== drawn) setDrawn(onScreen);
  if (resource === null) return null;
  if (resource.status === "ok") return { status: "ready", shapes: resource.data.shapes, topology: resource.data.topology };
  if (resource.status === "loading") return { status: "loading", lastDrawn: drawn };
  return { status: "failed", reason: resource.status === "error" ? resource.message : "The mesh did not load." };
}
