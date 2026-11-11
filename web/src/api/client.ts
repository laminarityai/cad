import { confirmUrl } from "./confirmation";
import type {
  BriefView,
  ConfirmationCard,
  GeometryRead,
  MaterialListings,
  ProjectConversation,
  ProjectList,
  ProjectView,
  ScorecardSnapshot,
  Tessellated,
  VariantSetView,
  VariantView,
  paths,
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
  conversation(projectId: string): Promise<ProjectConversation>;
  confirmation(projectId: string): Promise<ConfirmationCard>;
  answer(projectId: string, form: URLSearchParams): Promise<Answered>;
  scorecard(variantId: string, briefId: string, materialKey: string | null): Promise<ScorecardSnapshot>;
  variantSet(projectId: string, briefId: string, materialKey?: string): Promise<VariantSetView>;
  materials(): Promise<MaterialListings>;
  view(variantId: string): Promise<VariantView>;
  mesh(meshUrl: string): Promise<Tessellated>;
  geometry(variantId: string): Promise<GeometryRead>;
}

export interface Answered {
  status: number;
  text: string;
}

type Method = "get" | "post" | "put";
type Route<M extends Method> = { [P in keyof paths]: paths[P] extends Record<M, object> ? P : never }[keyof paths];
type Op<P extends keyof paths, M extends Method> = paths[P] extends Record<M, infer O> ? O : never;
type Params<O> = O extends { parameters: infer T } ? T : never;
type PathOf<O> = Params<O> extends { path: infer T } ? T : never;
type QueryOf<O> = NonNullable<Params<O> extends { query?: infer T } ? T : never>;
type BodyOf<O> = O extends { requestBody: { content: { "application/json": infer T } } } ? T : never;
type JsonOf<O> = O extends { responses: infer R } ? (R[Extract<keyof R, 200 | 201 | 202>] extends { content: { "application/json": infer T } } ? T : never) : never;
type StreamRoute = { [P in Route<"get">]: Op<P, "get"> extends { responses: { 200: { content: { "text/event-stream": unknown } } } } ? P : never }[Route<"get">];

type Options<O> = ([PathOf<O>] extends [never] ? unknown : { path: PathOf<O> }) &
  ([QueryOf<O>] extends [never] ? unknown : { query?: QueryOf<O> }) &
  ([BodyOf<O>] extends [never] ? unknown : { body: BodyOf<O> });
type Args<O> = Partial<Options<O>> extends Options<O> ? [options?: Options<O>] : [options: Options<O>];

interface Loose {
  path?: Record<string, string>;
  query?: Record<string, string | number | boolean | null | undefined>;
  body?: unknown;
}

/** The URL of a route in `paths`, its `{name}` parts filled in from `path` and its query from `query`. */
function urlOf(route: string, { path = {}, query = {} }: Loose): string {
  const filled = route.replace(/\{(\w+)\}/g, (_, name: string) => encodeURIComponent(path[name] ?? ""));
  const search = new URLSearchParams(Object.entries(query).flatMap(([name, value]) => (value === undefined || value === null ? [] : [[name, String(value)]]))).toString();
  return search === "" ? filled : `${filled}?${search}`;
}

async function fetchJson<T>(method: Uppercase<Method>, url: string, body?: unknown): Promise<T> {
  const response = await fetch(url, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? { accept: "application/json" } : { accept: "application/json", "content-type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (response.status === 401) throw new SignedOut();
  if (response.status === 404) throw new NotFound(url);
  if (!response.ok) {
    const said = (await response.json().catch(() => null)) as {
      error?: string;
    } | null;
    throw new Refused(response.status, said?.error ?? `HTTP ${String(response.status)}`);
  }
  return (await response.json()) as T;
}

/** The one way to call a route of the server. A route, its path and query parts or its body that
 * `paths` (generated from the server) does not have fails the type check. */
export function request<M extends Method, P extends Route<M>>(method: M, route: P, ...[options]: Args<Op<P, M>>): Promise<JsonOf<Op<P, M>>> {
  const given: Loose = options ?? {};
  return fetchJson(method.toUpperCase() as Uppercase<M>, urlOf(route, given), given.body);
}

/** The open response of a server-sent-event route. The caller reads it and tells 401 from 404. */
export function openStream<P extends StreamRoute>(route: P, signal: AbortSignal, ...[options]: Args<Op<P, "get">>): Promise<Response> {
  return fetch(urlOf(route, options ?? {}), { credentials: "same-origin", headers: { accept: "text/event-stream" }, signal });
}

async function postAnswer(projectId: string, form: URLSearchParams): Promise<Answered> {
  const response = await fetch(confirmUrl(projectId), {
    method: "POST",
    credentials: "same-origin",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: form.toString(),
  });
  const body = await response.text();
  const text = response.headers.get("content-type")?.includes("html") ? new DOMParser().parseFromString(body, "text/html").body.textContent : body;
  return { status: response.status, text: text.trim() };
}

export const httpApi: Api = {
  projects: () => request("get", "/v1/projects"),
  project: (project_id) => request("get", "/v1/projects/{project_id}", { path: { project_id } }),
  brief: (brief_id) => request("get", "/v1/briefs/{brief_id}", { path: { brief_id } }),
  conversation: (project_id) => request("get", "/v1/projects/{project_id}/conversation", { path: { project_id } }),
  confirmation: (project_id) => request("get", "/v1/projects/{project_id}/confirmation", { path: { project_id } }),
  answer: postAnswer,
  scorecard: (variant_id, brief_id, materialKey) =>
    request("get", "/v1/variants/{variant_id}/scorecard", { path: { variant_id }, query: { brief_id, material_key: materialKey || undefined } }),
  variantSet: (project_id, brief_id, material_key) => request("get", "/v1/projects/{project_id}/briefs/{brief_id}/set", { path: { project_id, brief_id }, query: { material_key: material_key || undefined } }),
  materials: () => request("get", "/v1/materials"),
  view: (variant_id) => request("get", "/v1/variants/{variant_id}", { path: { variant_id } }),
  mesh: (meshUrl) => fetchJson("GET", meshUrl),
  geometry: (variant_id) => request("get", "/v1/variants/{variant_id}/geometry", { path: { variant_id } }),
};
