import { Box, ChevronLeft, ChevronRight, Ruler, Slice } from "lucide-react";
import { useMemo, useState, type Dispatch, type ReactElement } from "react";
import { DimensionOverlay } from "@/features/viewer/DimensionOverlay";
import type { Extents } from "@/features/viewer/dimensions";
import type { OnPick, Track } from "@/features/viewer/engine";
import { readoutOf, type Measure } from "@/features/viewer/readout";
import { sectionOf, type Cut } from "@/features/viewer/section";
import { SectionPanel } from "@/features/viewer/SectionPanel";
import type { Pick, Selection } from "@/features/viewer/selection";
import { SelectionNote } from "@/features/viewer/SelectionNote";
import { ViewerCanvas } from "@/features/viewer/ViewerCanvas";
import { useDrawn } from "@/features/viewer/useDrawn";
import { useMesh } from "@/features/viewer/useMesh";
import { ROLE_COLOUR, type Where } from "@/features/viewer/where";
import { TabsList, TabsTab } from "@/components/ui/tabs";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { passedExtents, summaryOf, type Card } from "./cards";
import type { Brief, Fit, Slot, ViewAction } from "./model";
import { Dot } from "./bits";
import { Download } from "./Download";

function TabOf({ differs, children }: { differs: string; children: ReactElement }) {
  return differs ? <Tooltip label={differs}>{children}</Tooltip> : children;
}

/** The option tabs. The workspace owns the Tabs root, so it can place the stage in the tab panel. */
export function SlotTabs(props: { brief: Brief; cards: Record<string, Card> }) {
  const { brief, cards } = props;
  return (
    <TabsList aria-label="Options" className="flex gap-1 overflow-x-auto border-b border-rule">
      {brief.slots.map((one) => {
        const latest = one.revisions[one.revisions.length - 1];
        const summary = summaryOf(latest ? cards[latest.variantId] : undefined);
        return (
          <TabOf key={one.slot} differs={one.differs}>
            <TabsTab
              value={one.slot}
              data-slot-tab={one.slot}
              className="-mb-px flex min-w-[130px] max-w-[240px] shrink-0 flex-col items-start gap-0.5 rounded-t-lg border border-b-0 border-transparent px-3.5 py-2 text-left text-ink-2 hover:bg-panel/60 data-[active]:border-rule data-[active]:bg-panel data-[active]:text-ink"
            >
              <span className="flex w-full items-center gap-2">
                <span className="truncate text-[15px] font-semibold text-ink">{one.label}</span>
                <Dot status={summary.status} className="ml-auto" />
              </span>
              {one.differs ? <span className="line-clamp-2 w-full text-[13px] leading-snug text-ink-2">{one.differs}</span> : null}
            </TabsTab>
          </TabOf>
        );
      })}
    </TabsList>
  );
}

const NO_PICKS: readonly Pick[] = [];
const ignore: OnPick = () => undefined;

const unmeasured: Measure = () => null;

/** `extents` is the size check's numbers to draw, or null for none. `cut` is the section the person chose, or null for the whole part. */
function Mesh(props: {
  variantId: string;
  label: string;
  fit: Fit | null;
  where: Where | null;
  selection: Selection | null;
  extents: Extents | null;
  cut: Cut | null;
  onCut: (next: Cut) => void;
  onPick: OnPick;
}) {
  const { variantId, label, fit, where, selection, extents, cut, onCut, onPick } = props;
  const mesh = useMesh(variantId);
  const fitMesh = useMesh(fit?.variantId ?? variantId);
  const [measure, setMeasure] = useState<Measure | null>(null);
  const [track, setTrack] = useState<Track | null>(null);
  const topology = mesh.status === "ready" ? mesh.topology : null;
  const picks = selection?.picks ?? NO_PICKS;
  const readout = useMemo(() => (topology ? readoutOf(picks, topology, measure ?? unmeasured) : null), [picks, topology, measure]);
  const part = mesh.status === "ready" ? mesh.shapes : mesh.status === "loading" ? mesh.lastDrawn : null;
  const ghost = fit && fitMesh.status === "ready" ? fitMesh.shapes : null;
  const drawn = useDrawn(part, ghost, where);
  // The box of everything drawn, so a cut can reach the context part beside the part.
  const bb = drawn?.bb ?? null;
  const axis = cut?.axis;
  const position = cut?.at;
  const plane = useMemo(() => (bb && axis ? sectionOf({ axis, at: position ?? null }, bb) : null), [bb, axis, position]);
  let body: ReactElement;
  if (mesh.status === "failed") {
    body = <p className="p-4 text-fail">{mesh.reason}</p>;
  } else if (drawn === null) {
    body = <p className="p-4 text-ink-3">Drawing…</p>;
  } else {
    body = (
      <ViewerCanvas
        key={`${variantId}:${String(ghost !== null)}`}
        shapes={drawn}
        label={label}
        picks={picks}
        section={plane}
        onPick={mesh.status === "ready" ? onPick : ignore}
        onMeasure={(next) => {
          setMeasure(() => next);
        }}
        onTrack={(next) => {
          setTrack(() => next);
        }}
      />
    );
  }
  return (
    <>
      {body}
      {cut && bb && plane ? <SectionPanel cut={cut} at={plane.at} bb={bb} onChange={onCut} /> : null}
      {extents && mesh.status === "ready" ? <DimensionOverlay extents={extents} bb={mesh.shapes.bb} track={track} /> : null}
      <SelectionNote selection={selection} readout={readout} />
    </>
  );
}

const LEGEND: readonly (readonly [keyof Where, string])[] = [
  ["support", "Held in place"],
  ["load", "Pushed on"],
];

/** Says what the two colours on the part mean, for the faces the stress check used. */
function WhereLegend({ where }: { where: Where }) {
  return (
    <ul data-where-legend className="pointer-events-none absolute bottom-3 right-3 z-30 space-y-1 rounded-md bg-panel/85 px-2.5 py-1.5 text-[13px] text-ink-2">
      {LEGEND.filter(([role]) => where[role].length > 0).map(([role, text]) => (
        <li key={role} data-where-role={role} className="flex items-center gap-2">
          <span aria-hidden className="inline-block size-3 rounded-sm" style={{ backgroundColor: ROLE_COLOUR[role] }} />
          {text}
        </li>
      ))}
    </ul>
  );
}

const at = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

export function Stage(props: {
  slot: Slot;
  revision: number | null;
  dispatch: Dispatch<ViewAction>;
  briefId: string;
  fit: Fit | null;
  where: Where | null;
  selection: Selection | null;
  cards: Record<string, Card>;
  onPick: OnPick;
}) {
  const { slot, revision, dispatch, briefId, fit, where, selection, cards, onPick } = props;
  const [showFit, setShowFit] = useState(true);
  const [showSize, setShowSize] = useState(false);
  const [cut, setCut] = useState<Cut | null>(null);
  const newest = slot.revisions.length;
  const showing = Math.min(revision ?? newest, newest);
  const shown = slot.revisions[showing - 1];
  if (!shown) return null;
  const size = passedExtents(cards[shown.variantId]?.snapshot);
  const key = `${briefId}:${String(slot.slot)}`;
  // A cut draws a cap across a closed solid. The held and pushed faces are drawn apart from the part, which
  // leaves it open, and the library then fills the cap across them, so the colours wait for the whole part.
  const marked = cut ? null : where;
  const step = (n: number) => {
    dispatch({ type: "revision", key, n: n === newest ? null : n });
  };
  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div className="relative min-h-0 flex-1" data-stage>
        <Mesh variantId={shown.variantId} label={`${slot.label}, revision ${String(showing)}`} fit={showFit ? fit : null} where={marked} selection={selection} extents={showSize ? size : null} cut={cut} onCut={setCut} onPick={onPick} />
        <div className="absolute right-3 top-3 z-30 flex max-w-[calc(100%-1.5rem)] items-start gap-2">
          {fit ? (
            <button
              type="button"
              aria-pressed={showFit}
              data-fit-toggle
              onClick={() => {
                setShowFit((was) => !was);
              }}
              className={cn(
                "flex min-w-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-[14px] shadow-sm",
                showFit ? "border-rule bg-panel-2 text-ink" : "border-rule bg-panel text-ink-3",
              )}
            >
              <Box className="size-4 shrink-0" /> <span className="truncate">With {fit.name}</span>
            </button>
          ) : null}
          <Tooltip label="Cut through the part to see inside">
            <button
              type="button"
              aria-pressed={cut !== null}
              aria-label="Section"
              data-section-toggle
              onClick={() => {
                setCut((was) => (was ? null : { axis: "x", at: null }));
              }}
              className={cn(
                "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[14px] shadow-sm",
                cut ? "border-rule bg-panel-2 text-ink" : "border-rule bg-panel text-ink-3",
              )}
            >
              <Slice className="size-4" /> <span className="hidden sm:inline">Section</span>
            </button>
          </Tooltip>
          {size ? (
            <Tooltip label="Dimensions from the size check">
              <button
                type="button"
                aria-pressed={showSize}
                aria-label="Dimensions"
                data-size-toggle
                onClick={() => {
                  setShowSize((was) => !was);
                }}
                className={cn(
                  "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[14px] shadow-sm",
                  showSize ? "border-rule bg-panel-2 text-ink" : "border-rule bg-panel text-ink-3",
                )}
              >
                <Ruler className="size-4" /> <span className="hidden sm:inline">Dimensions</span>
              </button>
            </Tooltip>
          ) : null}
          <Download key={shown.variantId} variantId={shown.variantId} briefId={briefId} />
        </div>
        {marked ? <WhereLegend where={marked} /> : null}
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
