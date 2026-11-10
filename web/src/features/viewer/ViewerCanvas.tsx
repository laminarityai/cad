import { useEffect, useRef, useState } from "react";
import { useServices } from "@/app/context";
import type { Mounted, Shapes, Theme } from "./engine";

function currentTheme(): Theme {
  const forced = document.documentElement.dataset.theme;
  if (forced === "light" || forced === "dark") return forced;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** One viewer for the life of the element. New `shapes` are drawn into it, not into a new one. */
export function ViewerCanvas({ shapes, label }: { shapes: Shapes; label: string }) {
  const { viewer } = useServices();
  const host = useRef<HTMLDivElement>(null);
  const mounted = useRef<{ view: Mounted; shapes: Shapes } | null>(null);
  const latest = useRef(shapes);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    latest.current = shapes;
    const held = mounted.current;
    if (held && held.shapes !== shapes) {
      held.view.show(shapes);
      held.shapes = shapes;
    }
  }, [shapes]);
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let live = true;
    const first = latest.current;
    viewer.mount(element, first, currentTheme()).then(
      (view) => {
        if (!live) {
          view.stop();
          return;
        }
        mounted.current = { view, shapes: first };
        if (latest.current !== first) {
          view.show(latest.current);
          mounted.current.shapes = latest.current;
        }
      },
      (error: unknown) => {
        if (live) setProblem(error instanceof Error ? error.message : "The viewer did not start.");
      },
    );
    return () => {
      live = false;
      mounted.current?.view.stop();
      mounted.current = null;
    };
  }, [viewer]);
  return (
    <div role="img" aria-label={label} data-viewer="ready" className="relative h-full min-h-[240px] w-full overflow-hidden bg-panel-2">
      <div ref={host} className="absolute inset-0 [&_canvas]:block" />
      {problem ? <p className="absolute inset-x-0 top-0 p-3 font-mono text-xs text-fail">{problem}</p> : null}
    </div>
  );
}
