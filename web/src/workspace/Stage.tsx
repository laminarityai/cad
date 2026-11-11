/* Throwaway prototype: the center of the page. Slot tabs, one 3D view that fills the space, the
 * slot's revisions to step back through, and a highlight the person points at. */
import { Box, ChevronLeft, ChevronRight, Crosshair, X } from "lucide-react";
import { useState, type Dispatch, type MouseEvent } from "react";
import type { Shapes } from "@/features/viewer/engine";
import { ViewerCanvas } from "@/features/viewer/ViewerCanvas";
import { useMesh } from "@/features/viewer/useMesh";
import { cn } from "@/lib/utils";
import { summaryOf, type Card } from "./cards";
import type { Brief, Fit, Highlight, Slot, ViewAction } from "./model";
import { Dot } from "./bits";

export function SlotTabs(props: { brief: Brief; slot: number; cards: Record<string, Card>; dispatch: Dispatch<ViewAction> }) {
  const { brief, slot, cards, dispatch } = props;
  return (
    <div role="tablist" aria-label="Options" className="flex gap-1 overflow-x-auto border-b border-rule">
      {brief.slots.map((one) => {
        const latest = one.revisions[one.revisions.length - 1];
        const summary = summaryOf(latest ? cards[latest.variantId] : undefined);
        const on = one.slot === slot;
        return (
          <button
            key={one.slot}
            role="tab"
            aria-selected={on}
            data-slot-tab={one.slot}
            onClick={() => {
              dispatch({ type: "slot", briefId: brief.id, slot: one.slot });
            }}
            className={cn(
              "-mb-px flex min-w-[150px] max-w-[240px] flex-col items-start gap-0.5 rounded-t-lg border border-b-0 px-3.5 py-2 text-left",
              on ? "border-rule bg-panel" : "border-transparent text-ink-2 hover:bg-panel/60",
            )}
          >
            <span className="flex w-full items-center gap-2">
              <span className="truncate text-[15px] font-semibold text-ink">{one.label}</span>
              <Dot status={summary.status} className="ml-auto" />
            </span>
            <span className="w-full truncate text-[13px] text-ink-2">{one.differs}</span>
          </button>
        );
      })}
    </div>
  );
}

/* MOCK: this lid option was modelled flat for printing, not in the box's frame, so it is seated by
 * hand: flipped and resting on the 30 mm rim. The real build models a part that must fit in that
 * part's frame, so the two draw together with no placement. */
const SEATED: Record<string, Shapes["parts"][number]["loc"]> = {
  "026445a319ce2b10": [
    [0, 0, 32],
    [1, 0, 0, 0],
  ],
  "928167d0fb6c61e6": [
    [0, 0, 33],
    [1, 0, 0, 0],
  ],
};

function withFit(part: Shapes, fit: Shapes, variantId: string): Shapes {
  const seat = SEATED[variantId];
  const own = part.parts.map((one) => (seat ? { ...one, loc: seat } : one));
  const ghost = fit.parts.map((one) => ({ ...one, id: "/variant/fit", name: "fit", color: "#9aa7b4", alpha: 0.22 }));
  return { ...part, parts: [...own, ...ghost], bb: { ...fit.bb, zmax: Math.max(fit.bb.zmax, seat ? seat[0][2] : part.bb.zmax) } };
}

/** Options that already hold the part they fit are drawn as they are. */
const HOLDS_FIT = new Set(["e4c5fd81fa49bb3a", "2ce31a3eb940337d", "27c2d5123a01c996"]);

function Mesh({ variantId, label, fit }: { variantId: string; label: string; fit: Fit | null }) {
  const mesh = useMesh(variantId);
  const fitMesh = useMesh(fit?.variantId ?? variantId);
  if (mesh.status === "failed") return <p className="p-4 text-fail">{mesh.reason}</p>;
  const shapes = mesh.status === "ready" ? mesh.shapes : mesh.lastDrawn;
  if (shapes === null) return <p className="p-4 text-ink-3">Drawing…</p>;
  const ghost = fit && !HOLDS_FIT.has(variantId) && fitMesh.status === "ready" ? fitMesh.shapes : null;
  return <ViewerCanvas key={`${variantId}:${String(ghost !== null)}`} shapes={ghost ? withFit(shapes, ghost, variantId) : shapes} label={label} />;
}

/** MOCK picking: where the person clicked, named by height on the view. The real build resolves
 * the click to a face of the revision's mesh (#201). */
function regionAt(y: number): string {
  if (y < 0.4) return "top rim";
  if (y < 0.7) return "side wall";
  return "base";
}

export function Stage(props: {
  slot: Slot;
  revision: number | null;
  highlight: Highlight | null;
  pointing: boolean;
  dispatch: Dispatch<ViewAction>;
  briefId: string;
  fit: Fit | null;
}) {
  const { slot, revision, highlight, pointing, dispatch, briefId, fit } = props;
  const [showFit, setShowFit] = useState(true);
  const newest = slot.revisions.length;
  const showing = revision ?? newest;
  const shown = slot.revisions[showing - 1] ?? slot.revisions[newest - 1];
  if (!shown) return null;
  const key = `${briefId}:${String(slot.slot)}`;
  const step = (n: number) => {
    dispatch({ type: "revision", key, n: n === newest ? null : n });
  };
  const pick = (event: MouseEvent<HTMLDivElement>) => {
    if (!pointing) return;
    const box = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - box.left) / box.width;
    const y = (event.clientY - box.top) / box.height;
    dispatch({ type: "highlight", highlight: { variantId: shown.variantId, x, y, label: `${slot.label}, ${regionAt(y)}` } });
  };
  const mine = highlight?.variantId === shown.variantId ? highlight : null;
  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div className={cn("relative min-h-0 flex-1", pointing && "cursor-crosshair")} onClickCapture={pick} data-stage>
        <Mesh variantId={shown.variantId} label={`${slot.label}, revision ${String(showing)}`} fit={showFit ? fit : null} />
        {pointing ? <div className="absolute inset-0 z-10 bg-accent/5 ring-2 ring-inset ring-accent/60" /> : null}
        {mine ? (
          <div
            data-highlight
            className="pointer-events-none absolute z-20 -translate-x-1/2 -translate-y-1/2"
            style={{ left: `${String(mine.x * 100)}%`, top: `${String(mine.y * 100)}%` }}
          >
            <div className="size-24 rounded-full border-2 border-accent bg-accent/25 shadow-[0_0_0_6px_rgba(95,176,224,0.15)]" />
          </div>
        ) : null}
        <div className="absolute right-3 top-3 z-30 flex gap-2">
          {fit ? (
            <button
              type="button"
              aria-pressed={showFit}
              data-fit-toggle
              onClick={() => {
                setShowFit((was) => !was);
              }}
              className={cn(
                "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[14px] shadow-sm",
                showFit ? "border-rule bg-panel-2 text-ink" : "border-rule bg-panel text-ink-3",
              )}
            >
              <Box className="size-4" /> {showFit ? `With ${fit.name}` : `Show ${fit.name}`}
            </button>
          ) : null}
          <button
            type="button"
            aria-pressed={pointing}
            onClick={() => {
              dispatch({ type: "point", on: !pointing });
            }}
            className={cn(
              "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[14px] shadow-sm",
              pointing ? "border-accent bg-accent text-accent-ink" : "border-rule bg-panel text-ink hover:bg-panel-2",
            )}
          >
            <Crosshair className="size-4" /> {pointing ? "Click the part" : "Point at it"}
          </button>
          {mine ? (
            <button
              type="button"
              onClick={() => {
                dispatch({ type: "highlight", highlight: null });
              }}
              className="flex items-center gap-1 rounded-full border border-rule bg-panel px-2.5 py-1.5 text-[14px]"
              aria-label="Clear highlight"
            >
              <X className="size-4" />
            </button>
          ) : null}
        </div>
      </div>
      <div className="flex items-center gap-3 border-t border-rule-2 px-4 py-2.5 text-[14px]" data-revisions>
        <button
          type="button"
          aria-label="Earlier revision"
          disabled={showing <= 1}
          onClick={() => {
            step(showing - 1);
          }}
          className="rounded-md border border-rule p-1 disabled:opacity-30"
        >
          <ChevronLeft className="size-4" />
        </button>
        <span className="tabular-nums">
          Revision {showing} of {newest}
        </span>
        <button
          type="button"
          aria-label="Later revision"
          disabled={showing >= newest}
          onClick={() => {
            step(showing + 1);
          }}
          className="rounded-md border border-rule p-1 disabled:opacity-30"
        >
          <ChevronRight className="size-4" />
        </button>
        <span className="truncate text-ink-2">{shown.note ?? ""}</span>
        {showing < newest ? (
          <span className="ml-auto flex items-center gap-2">
            <span className="rounded-full bg-wait-bg px-2.5 py-0.5 text-[13px] text-wait">Earlier revision</span>
            <button
              type="button"
              className="text-accent underline"
              onClick={() => {
                step(newest);
              }}
            >
              Back to latest
            </button>
          </span>
        ) : (
          <span className="ml-auto text-ink-3">{new Date(shown.at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</span>
        )}
      </div>
    </div>
  );
}
