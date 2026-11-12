import type { Shapes } from "./engine";

export type Vec3 = readonly [number, number, number];
export type Axis = "x" | "y" | "z";

export const AXES: readonly Axis[] = ["x", "y", "z"];

/** The size check's number for each axis, already written as the Checks card writes it ("60 mm").
 * The viewer never holds a size as a number, so it cannot draw one it worked out itself. */
export type Extents = Record<Axis, string>;

/** Where a world point lands on the canvas, in CSS pixels from the canvas's top-left corner. */
export interface ScreenPoint {
  x: number;
  y: number;
}

/** One dimension line. `edge` is the edge of the mesh's box it runs along, and `from` and `to` are that
 * edge's ends pushed outward. The extension lines join each end of the edge to the matching end of the line. */
export interface DimLine {
  axis: Axis;
  label: string;
  edge: readonly [Vec3, Vec3];
  from: Vec3;
  to: Vec3;
}

/** The lines stand off the box by this share of its largest side. */
const OFFSET = 0.12;

/** The three lines of the part's size, along the bottom edges and the vertical edge that lie on the outline
 * for a camera at +x, -y and +z, which is where the viewer starts. The mesh's box only places them. Each
 * label is the check's. */
export function dimensionLines(extents: Extents, bb: Shapes["bb"]): DimLine[] {
  const sides = [bb.xmax - bb.xmin, bb.ymax - bb.ymin, bb.zmax - bb.zmin];
  const out = OFFSET * Math.max(...sides);
  if (![bb.xmin, bb.xmax, bb.ymin, bb.ymax, bb.zmin, bb.zmax, out].every(Number.isFinite)) return [];
  const line = (axis: Axis, a: Vec3, b: Vec3, push: Vec3): DimLine => ({
    axis,
    label: extents[axis],
    edge: [a, b],
    from: [a[0] + push[0], a[1] + push[1], a[2] + push[2]],
    to: [b[0] + push[0], b[1] + push[1], b[2] + push[2]],
  });
  return [
    line("x", [bb.xmin, bb.ymin, bb.zmin], [bb.xmax, bb.ymin, bb.zmin], [0, -out, -out]),
    line("y", [bb.xmax, bb.ymin, bb.zmin], [bb.xmax, bb.ymax, bb.zmin], [out, 0, -out]),
    line("z", [bb.xmin, bb.ymin, bb.zmin], [bb.xmin, bb.ymin, bb.zmax], [-out, -out, 0]),
  ];
}

/** The points the overlay asks the engine to project, four to a line: the edge's ends, then the line's. */
export const pointsOf = (lines: readonly DimLine[]): Vec3[] => lines.flatMap((one) => [...one.edge, one.from, one.to]);

type Matrix = ArrayLike<number>;

/** A world point on a canvas of the given size, from the camera's view and projection matrices (column-major,
 * as three.js keeps them), or null when it is behind the camera. */
export function toScreen(view: Matrix, projection: Matrix, point: Vec3, width: number, height: number): ScreenPoint | null {
  const [x, y, z] = point;
  const eye = [0, 1, 2].map((row) => (view[row] ?? 0) * x + (view[row + 4] ?? 0) * y + (view[row + 8] ?? 0) * z + (view[row + 12] ?? 0));
  const clip = [0, 1, 3].map((row) => (projection[row] ?? 0) * (eye[0] ?? 0) + (projection[row + 4] ?? 0) * (eye[1] ?? 0) + (projection[row + 8] ?? 0) * (eye[2] ?? 0) + (projection[row + 12] ?? 0));
  const w = clip[2] ?? 0;
  if (!(w > 0)) return null;
  return { x: (((clip[0] ?? 0) / w + 1) / 2) * width, y: ((1 - (clip[1] ?? 0) / w) / 2) * height };
}

/** Keeps the lines and their labels clear of the canvas's edge, and of the hint along its bottom. */
const MARGIN = 72;

/** How far to zoom out about the middle of the view for every point to sit inside the canvas by `MARGIN`:
 * 1 when they already do. Zooming scales each point's distance from the middle by the same factor. */
export function zoomToFit(points: readonly (ScreenPoint | null)[], width: number, height: number): number {
  const room = (half: number, away: number) => (away > 0 ? Math.max(half - MARGIN, 0) / away : 1);
  return points.reduce((zoom, at) => (at ? Math.min(zoom, room(width / 2, Math.abs(at.x - width / 2)), room(height / 2, Math.abs(at.y - height / 2))) : zoom), 1);
}
