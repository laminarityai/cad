import type { EdgeFacts, FaceFacts, Tessellated } from "@/api/types";
import type { Pick } from "./selection";

export type Topology = Tessellated["topology"];

/** What the viewer library works out from the drawn mesh for two picks. The angle is absent when
 * the library has no direction for one of them. */
export interface MeshReading {
  distance: number;
  angle: number | null;
}

export type Measure = (a: Pick, b: Pick) => MeshReading | null;

export const NOT_A_CHECK = "Measured on screen. Not a check.";

type Held = Exclude<Pick, { kind: "part" }>;

// Normals come rounded to four decimals, so planes tilted by less than this are parallel.
const PARALLEL = 1e-4;

const mm = (value: number) => `${value.toFixed(2)} mm`;

const FACE_NAMES: Record<string, string> = {
  PLANE: "Planar face",
  CYLINDER: "Cylindrical face",
  CONE: "Conical face",
  SPHERE: "Spherical face",
  TORUS: "Toroidal face",
};
const EDGE_NAMES: Record<string, string> = { LINE: "Straight edge", CIRCLE: "Circular edge" };

const nameOf = (names: Record<string, string>, type: string, fallback: string) => names[type] ?? `${fallback} (${type.toLowerCase()})`;

function faceFacts(face: FaceFacts): string[] {
  const radius = face.radius === null ? "" : ` · radius ${mm(face.radius)}`;
  return [nameOf(FACE_NAMES, face.type, "Face"), `Area ${face.area.toFixed(2)} mm²${radius}`];
}

function edgeFacts(edge: EdgeFacts): string[] {
  const radius = edge.radius === null ? "" : ` · radius ${mm(edge.radius)}`;
  return [nameOf(EDGE_NAMES, edge.type, "Edge"), `Length ${mm(edge.length)}${radius}`];
}

const factsOf = (pick: Held, topology: Topology) => (pick.kind === "face" ? topology.faces[pick.index] : topology.edges[pick.index]);

const isCurved = (pick: Held, topology: Topology) => {
  const facts = factsOf(pick, topology);
  return facts?.type !== (pick.kind === "face" ? "PLANE" : "LINE");
};

const sub = (a: readonly number[], b: readonly number[]) => a.map((value, i) => value - (b[i] ?? 0));
const dot = (a: readonly number[], b: readonly number[]) => a.reduce((sum, value, i) => sum + value * (b[i] ?? 0), 0);

/** The gap between two parallel planes: how far the second plane's centre lies along the first's normal. */
function planeGap(a: FaceFacts, b: FaceFacts): number | null {
  if (a.type !== "PLANE" || b.type !== "PLANE" || a.normal === null || b.normal === null) return null;
  const cross = [
    a.normal[1] * b.normal[2] - a.normal[2] * b.normal[1],
    a.normal[2] * b.normal[0] - a.normal[0] * b.normal[2],
    a.normal[0] * b.normal[1] - a.normal[1] * b.normal[0],
  ];
  if (Math.hypot(...cross) > PARALLEL) return null;
  return Math.abs(dot(sub(b.center, a.center), a.normal));
}

function oneLines(pick: Held, topology: Topology): string[] | null {
  const facts = factsOf(pick, topology);
  if (facts === undefined) return null;
  return "area" in facts ? faceFacts(facts) : edgeFacts(facts);
}

function pairLines(a: Held, b: Held, topology: Topology, measure: Measure): string[] | null {
  const first = a.kind === "face" ? topology.faces[a.index] : undefined;
  const second = b.kind === "face" ? topology.faces[b.index] : undefined;
  const gap = first && second ? planeGap(first, second) : null;
  const mesh = measure(a, b);
  if (gap !== null) {
    const closest = mesh !== null && mm(mesh.distance) !== mm(gap) ? [`Closest points ${mm(mesh.distance)}`] : [];
    return [`Gap between the planes ${mm(gap)}`, ...closest];
  }
  if (mesh === null) return null;
  const about = isCurved(a, topology) || isCurved(b, topology) ? "≈" : "";
  const angle = mesh.angle === null ? [] : [`Angle ${about}${mesh.angle.toFixed(1)}°`];
  return [`Closest points ${about}${mm(mesh.distance)}`, ...angle];
}

/** The lines of the readout for the selection, or null when it has none: three or more picks, the whole
 * part, or a pair the viewer cannot measure. One pick shows the kernel's facts. Two parallel planes show
 * the gap between them. Any other pair shows what the mesh gives, with "≈" when either pick is curved. */
export function readoutOf(picks: readonly Pick[], topology: Topology, measure: Measure): string[] | null {
  const held = picks.filter((one): one is Held => one.kind !== "part");
  if (held.length !== picks.length || held.length === 0 || held.length > 2) return null;
  const [a, b] = held;
  if (a === undefined) return null;
  const body = b === undefined ? oneLines(a, topology) : pairLines(a, b, topology, measure);
  return body === null ? null : [...body, NOT_A_CHECK];
}
