import { useEffect, useRef, useState } from "react";
import { useServices } from "@/app/context";
import type { Shapes, Theme } from "./engine";

function currentTheme(): Theme {
  const forced = document.documentElement.dataset.theme;
  if (forced === "light" || forced === "dark") return forced;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ViewerCanvas({ shapes, label }: { shapes: Shapes; label: string }) {
  const { viewer } = useServices();
  const host = useRef<HTMLDivElement>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let stop: (() => void) | undefined;
    let live = true;
    viewer.mount(element, shapes, currentTheme()).then(
      (unmount) => {
        if (live) stop = unmount;
        else unmount();
      },
      (error: unknown) => {
        if (live) setProblem(error instanceof Error ? error.message : "The viewer did not start.");
      },
    );
    return () => {
      live = false;
      stop?.();
    };
  }, [viewer, shapes]);
  return (
    <div role="img" aria-label={label} data-viewer="ready" className="relative h-full min-h-[240px] w-full overflow-hidden bg-panel-2">
      <div ref={host} className="absolute inset-0 [&_canvas]:block" />
      {problem ? <p className="absolute inset-x-0 top-0 p-3 font-mono text-xs text-fail">{problem}</p> : null}
    </div>
  );
}
