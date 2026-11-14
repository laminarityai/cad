import type { Tessellated } from "@/api/types";
import { toScreen, zoomToFit, type Axis, type ScreenPoint, type Vec3 } from "./dimensions";
import type { MeshReading } from "./readout";
import type { Section } from "./section";
import type { Pick } from "./selection";
import { FACE_PARTS } from "./where";

type Vector3Tuple = [number, number, number];
type QuaternionTuple = [number, number, number, number];

export type Theme = "light" | "dark";
export type Shapes = Tessellated["shapes"];

export interface Mounted {
  show(shapes: Shapes): void;
  /** Highlights exactly these picks on the drawn mesh. */
  select(picks: readonly Pick[]): void;
  /** The library's closest-point distance and angle between two picks on the drawn mesh, or null when it cannot say. */
  measure(a: Pick, b: Pick): MeshReading | null;
  /** Tells `listener` where these world points land on the canvas, now and after each frame in which they
   * moved. A point behind the camera is null. Zooms out first when they would fall off the canvas.
   * Returns the call that stops it. */
  track(points: readonly Vec3[], listener: (screen: readonly (ScreenPoint | null)[]) => void): () => void;
  /** Cuts the part, and the context part beside it, square to an axis with the library's clipping planes, and
   * null puts the whole part back. The cut stays across `show()`. */
  section(plane: Section | null): void;
  stop(): void;
}

/** The viewer's `track`, which the overlay holds while the part is drawn. */
export type Track = Mounted["track"];

/** `pick` is what is under the cursor, or null for empty space or the fit ghost. */
export type OnPick = (pick: Pick | null, shift: boolean) => void;

export interface ViewerEngine {
  mount(element: HTMLElement, shapes: Shapes, theme: Theme, onPick: OnPick): Promise<Mounted>;
}

const LEAF = /^\/variant\/(?:part|support|load)\/(faces|edges)\/(?:faces|edges)_(\d+)$/;
const CLICK_SLOP_PX = 4;

export function pickOf(path: string): Pick | null {
  const [, group, index] = LEAF.exec(path) ?? [];
  if (index === undefined) return null;
  return { kind: group === "faces" ? "face" : "edge", index: Number(index) };
}

const same = (a: Shapes["bb"], b: Shapes["bb"]) => (Object.keys(a) as (keyof Shapes["bb"])[]).every((key) => a[key] === b[key]);

/** A number the library worked out, or null when the field is missing or not finite. */
function numberIn(row: unknown, key: string): number | null {
  if (typeof row !== "object" || row === null) return null;
  const value = (row as Record<string, unknown>)[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** The library keeps the side of the plane its normal points to. The viewer starts with its camera at +x, -y and
 * +z of the part, so x and z keep the low side and y keeps the high side, and the cut face looks at the camera. */
const CUT_NORMAL: readonly Vector3Tuple[] = [
  [-1, 0, 0],
  [0, 1, 0],
  [0, 0, -1],
];
const AXIS_AT: Record<Axis, 0 | 1 | 2> = { x: 0, y: 1, z: 2 };

export const EDGE = 0x2a3236;

export const threeCadViewer: ViewerEngine = {
  async mount(element, shapes, theme, onPick) {
    const lib = await import("three-cad-viewer");
    await import("three-cad-viewer/css");
    const box = () => ({ width: Math.max(element.clientWidth, 120), height: Math.max(element.clientHeight, 120) });
    const first = box();
    const display = new lib.Display(element, {
      cadWidth: first.width,
      height: first.height,
      treeWidth: 0,
      theme,
      tools: false,
      glass: true,
      pinning: false,
      measureTools: false,
      externalMeasurementBackend: false,
      selectTool: false,
      explodeTool: false,
      zscaleTool: false,
      zebraTool: false,
      studioTool: false,
    });
    const viewer = new lib.Viewer(display, { up: "Z" }, () => undefined);
    const fit = () => {
      const now = box();
      viewer.resizeCadView(now.width, 0, now.height, true);
    };
    const draw = (next: Shapes) => {
      viewer.render(
        next as unknown as Parameters<typeof viewer.render>[0],
        { edgeColor: EDGE, defaultOpacity: 1, normalLen: 0 },
        { up: "Z", axes: false, grid: [false, false, false], ortho: true },
      );
      display.showTools(false);
      display.showInfo(false);
      fit();
    };
    let drawn = shapes;
    draw(shapes);
    const resize = new ResizeObserver(fit);
    resize.observe(element);

    const canvas = viewer.renderer.domElement;
    const hit = (event: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      return viewer.idPicker?.pickAt(event.clientX - rect.left, event.clientY - rect.top, { topoFilter: ["face", "edge"] }) ?? null;
    };
    let down: { x: number; y: number } | null = null;
    const onDown = (event: PointerEvent) => {
      down = event.button === 0 ? { x: event.clientX, y: event.clientY } : null;
    };
    const onClick = (event: MouseEvent) => {
      const from = down;
      down = null;
      if (from === null || Math.hypot(event.clientX - from.x, event.clientY - from.y) > CLICK_SLOP_PX) return;
      onPick(pickOf(hit(event)?.info.path ?? ""), event.shiftKey);
    };
    const onDouble = (event: MouseEvent) => {
      if (FACE_PARTS.some((id) => hit(event)?.info.path.startsWith(`${id}/`))) onPick({ kind: "part" }, false);
    };
    viewer.setPickHandler(false);
    canvas.addEventListener("pointerdown", onDown);
    canvas.addEventListener("click", onClick);
    canvas.addEventListener("dblclick", onDouble);

    /** The face's path in the piece of the part that draws it, since the stress check's faces are pieces of their own. */
    const pathOf = (pick: Pick): string | null => {
      const source = viewer.compactNestedGroup?.meshGeometry;
      if (source === undefined || pick.kind === "part") return null;
      return (
        FACE_PARTS.map((id) => `${id}/${pick.kind}s/${pick.kind}s_${String(pick.index)}`).find((path) => {
          const geometry = source.resolve(path);
          return geometry !== null && (geometry.indices?.length ?? geometry.positions.length) > 0;
        }) ?? null
      );
    };

    const trackers = new Set<() => void>();
    viewer.onAfterRender = () => {
      trackers.forEach((run) => {
        run();
      });
    };

    // The library clips only while its clip tab is the active one. It has three planes and all three cut
    // while it does, so the two the person did not choose sit far beyond the part.
    let cut: Section | null = null;
    let planes: Axis | null = null;
    const cutAt = (plane: Section) => {
      const centre = viewer.rendered.clipping.center;
      const along = plane.at - (centre?.[AXIS_AT[plane.axis]] ?? 0);
      return plane.axis === "y" ? -along : along;
    };
    const applyCut = () => {
      const plane = cut;
      if (plane === null) {
        planes = null;
        viewer.setActiveTab("tree");
      } else if (planes === plane.axis) {
        viewer.setClipSlider(AXIS_AT[plane.axis], cutAt(plane));
      } else {
        const open = viewer.gridSize / 2;
        CUT_NORMAL.forEach((normal, index) => {
          viewer.setClipNormal(index as 0 | 1 | 2, normal, index === AXIS_AT[plane.axis] ? cutAt(plane) : open);
        });
        viewer.setActiveTab("clip");
        planes = plane.axis;
      }
      viewer.update(true, false);
    };

    return {
      track(points, listener) {
        const onCanvas = () => {
          const lens = viewer.camera.getCamera();
          lens.updateMatrixWorld();
          const { width, height } = canvas.getBoundingClientRect();
          return points.map((point) => toScreen(lens.matrixWorldInverse.elements, lens.projectionMatrix.elements, point, width, height));
        };
        // The library fits the part, so lines standing off it would run off the canvas. Zoom about the middle
        // of the view until they fit, as the person would.
        const room = zoomToFit(onCanvas(), canvas.clientWidth, canvas.clientHeight);
        if (room < 1) {
          const camera = viewer.getCameraLocationSettings();
          const [position, quaternion, target] = [camera.position, camera.quaternion, camera.target] as [Vector3Tuple, QuaternionTuple, Vector3Tuple];
          viewer.setCameraLocationSettings(position, quaternion, target, camera.zoom * room);
        }
        let last = "";
        const run = () => {
          const origin = element.getBoundingClientRect();
          const surface = canvas.getBoundingClientRect();
          const screen = onCanvas().map((at) => at && { x: at.x + surface.left - origin.left, y: at.y + surface.top - origin.top });
          const now = JSON.stringify(screen);
          if (now === last) return;
          last = now;
          listener(screen);
        };
        trackers.add(run);
        run();
        return () => {
          trackers.delete(run);
        };
      },
      show(next) {
        // The same box means the same part drawn with other faces marked, so the person's view stays.
        const camera = same(drawn.bb, next.bb) ? viewer.getCameraLocationSettings() : null;
        drawn = next;
        viewer.clear();
        planes = null;
        draw(next);
        applyCut();
        if (camera) {
          const [position, quaternion, target] = [camera.position, camera.quaternion, camera.target] as [Vector3Tuple, QuaternionTuple, Vector3Tuple];
          viewer.setCameraLocationSettings(position, quaternion, target, camera.zoom);
        }
      },
      select(picks) {
        const highlight = viewer.rendered.nestedGroup.highlight;
        if (highlight === null) return;
        highlight.clear();
        const ids = new Map<string, number>();
        for (const entry of highlight.registry.entries()) ids.set(entry.path, entry.id);
        const wanted = picks.flatMap((one) =>
          one.kind === "part"
            ? [...ids.keys()].filter((path) => FACE_PARTS.some((id) => path.startsWith(`${id}/faces/`)))
            : FACE_PARTS.map((id) => `${id}/${one.kind}s/${one.kind}s_${String(one.index)}`),
        );
        for (const path of wanted) {
          const id = ids.get(path);
          if (id !== undefined) highlight.setSelected(id, true);
        }
        viewer.update(true, false);
      },
      measure(a, b) {
        const [first, second] = [pathOf(a), pathOf(b)];
        if (first === null || second === null) return null;
        const result: unknown = viewer.meshBackend.distance(first, second, false)?.result;
        if (!Array.isArray(result)) return null;
        const rows: unknown[] = result;
        const distance = numberIn(rows[0], "distance");
        if (distance === null) return null;
        return { distance, angle: rows.map((row) => numberIn(row, "angle")).find((angle) => angle !== null) ?? null };
      },
      section(plane) {
        cut = plane;
        applyCut();
      },
      stop() {
        trackers.clear();
        canvas.removeEventListener("pointerdown", onDown);
        canvas.removeEventListener("click", onClick);
        canvas.removeEventListener("dblclick", onDouble);
        resize.disconnect();
        viewer.dispose();
        display.dispose();
      },
    };
  },
};
