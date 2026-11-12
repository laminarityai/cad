import { useEffect, useRef, useState } from "react";
import { useServices } from "@/app/context";
import type { Mounted, OnPick, Shapes, Theme, Track } from "./engine";
import type { Measure } from "./readout";
import type { Pick } from "./selection";

function currentTheme(): Theme {
  const forced = document.documentElement.dataset.theme;
  if (forced === "light" || forced === "dark") return forced;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

interface Props {
  shapes: Shapes;
  label: string;
  picks: readonly Pick[];
  onPick: OnPick;
  /** Gets the viewer's measure once it is drawn, and null when it stops. */
  onMeasure: (measure: Measure | null) => void;
  /** Gets the viewer's projection once it is drawn, and null when it stops. */
  onTrack: (track: Track | null) => void;
}

export function ViewerCanvas({ shapes, label, picks, onPick, onMeasure, onTrack }: Props) {
  const { viewer } = useServices();
  const host = useRef<HTMLDivElement>(null);
  const mounted = useRef<{ view: Mounted; shapes: Shapes } | null>(null);
  const latest = useRef(shapes);
  const latestPicks = useRef(picks);
  const latestOnPick = useRef(onPick);
  const latestOnMeasure = useRef(onMeasure);
  const latestOnTrack = useRef(onTrack);
  const [problem, setProblem] = useState<string | null>(null);
  const countDraw = (into: HTMLElement) => {
    into.dataset.draws = String(Number(into.dataset.draws ?? "0") + 1);
  };
  useEffect(() => {
    latestOnPick.current = onPick;
    latestOnMeasure.current = onMeasure;
    latestOnTrack.current = onTrack;
  });
  useEffect(() => {
    latest.current = shapes;
    const held = mounted.current;
    if (held && held.shapes !== shapes) {
      held.view.show(shapes);
      held.view.select(latestPicks.current);
      held.shapes = shapes;
      if (host.current) countDraw(host.current);
    }
  }, [shapes]);
  useEffect(() => {
    latestPicks.current = picks;
    mounted.current?.view.select(picks);
  }, [picks]);
  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let live = true;
    const first = latest.current;
    viewer.mount(element, first, currentTheme(), (pick, shift) => {
      latestOnPick.current(pick, shift);
    }).then(
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
        view.select(latestPicks.current);
        latestOnMeasure.current((a, b) => view.measure(a, b));
        latestOnTrack.current((points, listener) => view.track(points, listener));
        countDraw(element);
      },
      (error: unknown) => {
        if (live) setProblem(error instanceof Error ? error.message : "The viewer did not start.");
      },
    );
    return () => {
      live = false;
      if (mounted.current) {
        latestOnMeasure.current(null);
        latestOnTrack.current(null);
      }
      mounted.current?.view.stop();
      mounted.current = null;
    };
  }, [viewer]);
  return (
    <div role="img" aria-label={label} data-viewer="ready" className="relative h-full min-h-[240px] w-full overflow-hidden bg-panel-2">
      <div ref={host} data-picks={picks.length} className="absolute inset-0 [&_canvas]:block" />
      {problem ? <p className="absolute inset-x-0 top-0 p-3 font-mono text-xs text-fail">{problem}</p> : null}
    </div>
  );
}
