import type {
  BriefView,
  GeometryRead,
  MaterialListings,
  ProjectList,
  ProjectView,
  Tessellated,
  VariantSetView,
  VariantView,
} from "./types";

export class SignedOut extends Error {
  constructor() {
    super("signed out");
    this.name = "SignedOut";
  }
}

export class NotFound extends Error {
  constructor(what: string) {
    super(`not found: ${what}`);
    this.name = "NotFound";
  }
}

export class Refused extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "Refused";
  }
}

export interface Api {
  projects(): Promise<ProjectList>;
  project(projectId: string): Promise<ProjectView>;
  brief(briefId: string): Promise<BriefView>;
  variantSet(projectId: string, briefId: string, materialKey?: string): Promise<VariantSetView>;
  materials(): Promise<MaterialListings>;
  view(variantId: string): Promise<VariantView>;
  mesh(meshUrl: string): Promise<Tessellated>;
  geometry(variantId: string): Promise<GeometryRead>;
}

export type { GeometryRead };

export async function requestJson<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? { accept: "application/json" } : { accept: "application/json", "content-type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (response.status === 401) throw new SignedOut();
  if (response.status === 404) throw new NotFound(path);
  if (!response.ok) {
    const said = (await response.json().catch(() => null)) as { error?: string } | null;
    throw new Refused(response.status, said?.error ?? `HTTP ${String(response.status)}`);
  }
  return (await response.json()) as T;
}

const getJson = <T>(path: string) => requestJson<T>("GET", path);

const enc = encodeURIComponent;

export const httpApi: Api = {
  projects: () => getJson("/v1/projects"),
  project: (projectId) => getJson(`/v1/projects/${enc(projectId)}`),
  brief: (briefId) => getJson(`/v1/briefs/${enc(briefId)}`),
  variantSet: (projectId, briefId, materialKey) =>
    getJson(
      `/v1/projects/${enc(projectId)}/briefs/${enc(briefId)}/set` +
        (materialKey ? `?material_key=${enc(materialKey)}` : ""),
    ),
  materials: () => getJson("/v1/materials"),
  view: (variantId) => getJson(`/v1/variants/${enc(variantId)}`),
  mesh: (meshUrl) => getJson(meshUrl),
  geometry: (variantId) => getJson(`/v1/variants/${enc(variantId)}/geometry`),
};
