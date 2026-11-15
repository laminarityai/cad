import { useServices } from "@/app/context";
import type { Api } from "@/api/client";
import type { Component, PartPlacement } from "@/api/types";
import { sleep } from "@/lib/sleep";
import { useResources } from "@/state/resource";
import type { Shapes } from "./engine";

/** The colour of each copy of a part the person supplied, so it never reads as the agent's body. */
export const SUPPLIED_COLOUR = "#d98a2b";

/** A part the person supplied, as its mesh draws, with each place the build put a copy of it. */
export interface Placed {
  partId: string;
  shapes: Shapes;
  placements: readonly PartPlacement[];
}

type Quaternion = [number, number, number, number];
type Point = [number, number, number];

/** The supplied parts drawn, and how many the build placed that are not drawn because their mesh failed or
 * was still not made after MAX_POLLS reads. */
export interface Supplied {
  placed: readonly Placed[];
  missing: number;
}

const POLL_MS = 500;
// Past the tessellation's 60 s wall, so a mesh still pending then is not coming.
const MAX_POLLS = 150;
const NONE: Supplied = { placed: [], missing: 0 };

const times = ([ax, ay, az, aw]: Quaternion, [bx, by, bz, bw]: Quaternion): Quaternion => [
  aw * bx + ax * bw + ay * bz - az * by,
  aw * by - ax * bz + ay * bw + az * bx,
  aw * bz + ax * by - ay * bx + az * bw,
  aw * bw - ax * bx - ay * by - az * bz,
];

const about = (axis: 0 | 1 | 2, degrees: number): Quaternion => {
  const half = (degrees * Math.PI) / 360;
  const q: Quaternion = [0, 0, 0, Math.cos(half)];
  q[axis] = Math.sin(half);
  return q;
};

/** The rotation of build123d's `Location(at, rotate)`, as x, y, z, w: about X, then Y, then Z, each about
 * the part's own turned axes. */
export function quaternionOf([x, y, z]: PartPlacement["rotate"]): Quaternion {
  return times(times(about(0, x), about(1, y)), about(2, z));
}

function turn([qx, qy, qz, qw]: Quaternion, [x, y, z]: Point): Point {
  const tx = 2 * (qy * z - qz * y);
  const ty = 2 * (qz * x - qx * z);
  const tz = 2 * (qx * y - qy * x);
  return [x + qw * tx + (qy * tz - qz * ty), y + qw * ty + (qz * tx - qx * tz), z + qw * tz + (qx * ty - qy * tx)];
}

function corners(bb: Shapes["bb"], place: PartPlacement): Point[] {
  const q = quaternionOf(place.rotate);
  const [ax, ay, az] = place.at;
  return [bb.xmin, bb.xmax].flatMap((x) =>
    [bb.ymin, bb.ymax].flatMap((y) =>
      [bb.zmin, bb.zmax].map((z): Point => {
        const [px, py, pz] = turn(q, [x, y, z]);
        return [px + ax, py + ay, pz + az];
      }),
    ),
  );
}

/** The agent's body with every copy of each supplied part drawn where the build placed it, in
 * SUPPLIED_COLOUR, and the box widened to hold them. A mesh comes at the origin of the part's own frame, so
 * each copy's location is its placement. */
export function withSupplied(body: Shapes, placed: readonly Placed[]): Shapes {
  if (placed.length === 0) return body;
  const copies = placed.flatMap((one) =>
    one.placements.flatMap((place, n) =>
      one.shapes.parts.map((piece) => ({
        ...piece,
        id: `/supplied/${one.partId}/${String(n)}${piece.id}`,
        name: `supplied ${piece.name}`,
        color: SUPPLIED_COLOUR,
        alpha: 1,
        loc: [place.at, quaternionOf(place.rotate)] as typeof piece.loc,
      })),
    ),
  );
  const points = placed.flatMap((one) => one.placements.flatMap((place) => corners(one.shapes.bb, place)));
  const xs = points.map((one) => one[0]);
  const ys = points.map((one) => one[1]);
  const zs = points.map((one) => one[2]);
  const bb = {
    xmin: Math.min(body.bb.xmin, ...xs),
    xmax: Math.max(body.bb.xmax, ...xs),
    ymin: Math.min(body.bb.ymin, ...ys),
    ymax: Math.max(body.bb.ymax, ...ys),
    zmin: Math.min(body.bb.zmin, ...zs),
    zmax: Math.max(body.bb.zmax, ...zs),
  };
  return { ...body, parts: [...body.parts, ...copies], bb };
}

/** Reading the view starts each placed part's mesh not yet made, so while one is pending the view is read
 * again every POLL_MS, at most MAX_POLLS times. A part whose mesh failed is left out. */
async function readPlaced(api: Api, variantId: string, listed: readonly Component[], signal: AbortSignal): Promise<Supplied> {
  let components = listed;
  for (let polls = 0; polls < MAX_POLLS && components.some((one) => one.mesh === "pending"); polls++) {
    await sleep(POLL_MS, signal);
    signal.throwIfAborted();
    components = (await api.view(variantId)).components;
  }
  const meshed = components.flatMap((one) => (one.mesh_url === null ? [] : [{ ...one, url: one.mesh_url }]));
  const placed = await Promise.all(meshed.map(async (one) => ({ partId: one.part_id, shapes: (await api.mesh(one.url)).shapes, placements: one.placements })));
  return { placed, missing: components.length - placed.length };
}

/** The supplied parts `variantId`'s build placed, from the `components` its view listed, or none while they
 * load or when they could not be read: the agent's body draws either way. */
export function usePlaced(variantId: string, components: readonly Component[]): Supplied {
  const { api } = useServices();
  const keys = components.length > 0 ? [variantId] : [];
  const { resources } = useResources(keys, (id, signal) => readPlaced(api, id, components, signal));
  const resource = resources[variantId];
  return resource?.status === "ok" ? resource.data : NONE;
}
