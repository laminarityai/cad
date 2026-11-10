import type { Tessellated } from "@/api/types";

export type Theme = "light" | "dark";
export type Shapes = Tessellated["shapes"];

export interface Mounted {
  show(shapes: Shapes): void;
  stop(): void;
}

export interface ViewerEngine {
  mount(element: HTMLElement, shapes: Shapes, theme: Theme): Promise<Mounted>;
}

const EDGE: Record<Theme, number> = { light: 0x2a3236, dark: 0xb9c1be };

export const threeCadViewer: ViewerEngine = {
  async mount(element, shapes, theme) {
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
    return {
      show(next) {
        viewer.clear();
        draw(next);
      },
      stop() {
        resize.disconnect();
        viewer.dispose();
        display.dispose();
      },
    };
  },
};
