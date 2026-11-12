import type { PartWire, ShapeWire } from "@/api/types";
import type { Shapes } from "./engine";

/** The faces of a part that the stress check fixed and pressed on, as face indices of the part's mesh. */
export interface Where {
  support: readonly number[];
  load: readonly number[];
}

export type Role = keyof Where;

export const PART = "/variant/part";
const ROLE_ID: Record<Role, string> = { support: "/variant/support", load: "/variant/load" };
/** Two hues that stay apart for the common colour-blindnesses and from the part's yellow. */
export const ROLE_COLOUR: Record<Role, string> = { support: "#0072b2", load: "#cc79a7" };

/** The ids of every part that carries faces of the variant, so a click on any of them is a click on the part. */
export const FACE_PARTS: readonly string[] = [PART, ...Object.values(ROLE_ID)];

function trianglesOf(shape: ShapeWire, faces: ReadonlySet<number>, keep: boolean): Pick<ShapeWire, "triangles" | "triangles_per_face"> {
  const triangles: number[] = [];
  const perFace: number[] = [];
  let at = 0;
  shape.triangles_per_face.forEach((count, face) => {
    const held = faces.has(face) === keep;
    if (held) for (let i = at; i < at + 3 * count; i += 1) triangles.push(shape.triangles[i] ?? 0);
    perFace.push(held ? count : 0);
    at += 3 * count;
  });
  return { triangles, triangles_per_face: perFace };
}

/** The part drawn in three: the faces nobody pointed at in the part's own colour, and the support and
 * the load each as a part of their own with that role's colour. Every piece keeps the whole part's
 * vertices and a count for every face, empty where the face is not in it, so a face's index in a
 * piece is its index in the part and a click on any piece still names the face. */
export function splitFaces(shapes: Shapes, where: Where): Shapes {
  const [part, ...rest] = shapes.parts;
  if (part?.id !== PART) return shapes;
  const roles = (Object.keys(ROLE_ID) as Role[]).map((role) => ({ role, faces: new Set(where[role]) })).filter((one) => one.faces.size > 0);
  if (roles.length === 0) return shapes;
  const all = new Set(roles.flatMap((one) => [...one.faces]));
  const base: PartWire = { ...part, shape: { ...part.shape, ...trianglesOf(part.shape, all, false) } };
  const overlays = roles.map(
    ({ role, faces }): PartWire => ({
      ...part,
      id: ROLE_ID[role],
      name: role,
      color: ROLE_COLOUR[role],
      state: [1, 0],
      shape: {
        ...part.shape,
        ...trianglesOf(part.shape, faces, true),
        edges: [],
        segments_per_edge: [],
        edge_types: [],
        obj_vertices: [],
      },
    }),
  );
  return { ...shapes, parts: [base, ...overlays, ...rest] };
}
