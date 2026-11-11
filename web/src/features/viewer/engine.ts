import type { Tessellated } from "@/api/types";
import type { Pick } from "./selection";

export type Theme = "light" | "dark";
export type Shapes = Tessellated["shapes"];

export interface Mounted {
  show(shapes: Shapes): void;
  /** Highlights exactly these picks on the drawn mesh. */
  select(picks: readonly Pick[]): void;
  stop(): void;
}

/** `pick` is what is under the cursor, or null for empty space or the fit ghost. */
export type OnPick = (pick: Pick | null, shift: boolean) => void;

export interface ViewerEngine {
  mount(element: HTMLElement, shapes: Shapes, theme: Theme, onPick: OnPick): Promise<Mounted>;
}

const VARIANT_PART = "/variant/part";
const LEAF = /^\/variant\/part\/(faces|edges)\/(?:faces|edges)_(\d+)$/;
const CLICK_SLOP_PX = 4;

function pickOf(path: string): Pick | null {
  const [, group, index] = LEAF.exec(path) ?? [];
  if (index === undefined) return null;
  return { kind: group === "faces" ? "face" : "edge", index: Number(index) };
}

const EDGE: Record<Theme, number> = { light: 0x2a3236, dark: 0xb9c1be };

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
        { edgeColor: EDGE[theme], defaultOpacity: 1, normalLen: 0 },
        { up: "Z", axes: false, grid: [false, false, false], ortho: true },
      );
      display.showTools(false);
      display.showInfo(false);
      fit();
    };
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
      if (hit(event)?.info.path.startsWith(`${VARIANT_PART}/`)) onPick({ kind: "part" }, false);
    };
    viewer.setPickHandler(false);
    canvas.addEventListener("pointerdown", onDown);
    canvas.addEventListener("click", onClick);
    canvas.addEventListener("dblclick", onDouble);

    return {
      show(next) {
        viewer.clear();
        draw(next);
      },
      select(picks) {
        const highlight = viewer.rendered.nestedGroup.highlight;
        if (highlight === null) return;
        highlight.clear();
        const ids = new Map<string, number>();
        for (const entry of highlight.registry.entries()) ids.set(entry.path, entry.id);
        const wanted = picks.flatMap((one) =>
          one.kind === "part" ? [...ids.keys()].filter((path) => path.startsWith(`${VARIANT_PART}/faces/`)) : [`${VARIANT_PART}/${one.kind}s/${one.kind}s_${String(one.index)}`],
        );
        for (const path of wanted) {
          const id = ids.get(path);
          if (id !== undefined) highlight.setSelected(id, true);
        }
        viewer.update(true, false);
      },
      stop() {
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
