import { Box, ChevronLeft, ChevronRight, Crosshair } from "lucide-react";
import { useState, type Dispatch } from "react";
import type { Shapes } from "@/features/viewer/engine";
import { ViewerCanvas } from "@/features/viewer/ViewerCanvas";
import { useMesh } from "@/features/viewer/useMesh";
import { cn } from "@/lib/utils";
import { summaryOf, type Card } from "./cards";
import type { Brief, Fit, Slot, ViewAction } from "./model";
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
              "-mb-px flex min-w-[130px] max-w-[240px] flex-col items-start gap-0.5 rounded-t-lg border border-b-0 px-3.5 py-2 text-left",
              on ? "border-rule bg-panel" : "border-transparent text-ink-2 hover:bg-panel/60",
            )}
          >
            <span className="flex w-full items-center gap-2">
              <span className="truncate text-[15px] font-semibold text-ink">{one.label}</span>
              <Dot status={summary.status} className="ml-auto" />
            </span>
            {one.differs ? <span className="w-full truncate text-[13px] text-ink-2">{one.differs}</span> : null}
          </button>
        );
      })}
    </div>
  );
}

/** A part that must fit is built in that part's frame, so the two draw together as they are. */
function withFit(part: Shapes, fit: Shapes): Shapes {
  const ghost = fit.parts.map((one) => ({
    ...one,
    id: `/fit${one.id}`,
    name: `fit ${one.name}`,
    color: "#9aa7b4",
    alpha: 0.22,
  }));
  const bb = {
    xmin: Math.min(part.bb.xmin, fit.bb.xmin),
    xmax: Math.max(part.bb.xmax, fit.bb.xmax),
    ymin: Math.min(part.bb.ymin, fit.bb.ymin),
    ymax: Math.max(part.bb.ymax, fit.bb.ymax),
    zmin: Math.min(part.bb.zmin, fit.bb.zmin),
    zmax: Math.max(part.bb.zmax, fit.bb.zmax),
  };
  return { ...part, parts: [...part.parts, ...ghost], bb };
}

function Mesh({ variantId, label, fit }: { variantId: string; label: string; fit: Fit | null }) {
  const mesh = useMesh(variantId);
  const fitMesh = useMesh(fit?.variantId ?? variantId);
  if (mesh.status === "failed") return <p className="p-4 text-fail">{mesh.reason}</p>;
  const shapes = mesh.status === "ready" ? mesh.shapes : mesh.lastDrawn;
  if (shapes === null) return <p className="p-4 text-ink-3">Drawing…</p>;
  const ghost = fit && fitMesh.status === "ready" ? fitMesh.shapes : null;
  return <ViewerCanvas key={`${variantId}:${String(ghost !== null)}`} shapes={ghost ? withFit(shapes, ghost) : shapes} label={label} />;
}

const at = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

export function Stage(props: { slot: Slot; revision: number | null; dispatch: Dispatch<ViewAction>; briefId: string; fit: Fit | null }) {
  const { slot, revision, dispatch, briefId, fit } = props;
  const [showFit, setShowFit] = useState(true);
  const newest = slot.revisions.length;
  const showing = Math.min(revision ?? newest, newest);
  const shown = slot.revisions[showing - 1];
  if (!shown) return null;
  const key = `${briefId}:${String(slot.slot)}`;
  const step = (n: number) => {
    dispatch({ type: "revision", key, n: n === newest ? null : n });
  };
  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div className="relative min-h-0 flex-1" data-stage>
        <Mesh variantId={shown.variantId} label={`${slot.label}, revision ${String(showing)}`} fit={showFit ? fit : null} />
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
              <Box className="size-4" /> With {fit.name}
            </button>
          ) : null}
          <button
            type="button"
            disabled
            title="Coming soon"
            className="flex items-center gap-1.5 rounded-full border border-rule bg-panel px-3 py-1.5 text-[14px] text-ink-3 shadow-sm disabled:cursor-not-allowed"
          >
            <Crosshair className="size-4" /> Point at it
          </button>
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
          <span className="ml-auto text-ink-3">{at(shown.at)}</span>
        )}
      </div>
    </div>
  );
}
