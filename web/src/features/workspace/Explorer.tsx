import { Box, Folder, FolderOpen, Plus } from "lucide-react";
import { useState, type Dispatch } from "react";
import type { Source } from "@/api/types";
import { Collapsible, CollapsibleTrigger, CollapsiblePanel } from "@/components/ui/collapsible";
import { Shimmer } from "@/components/ui/busy";
import { Tooltip } from "@/components/ui/tooltip";
import { workingLabel, type Working } from "@/features/chat/working";
import { cn } from "@/lib/utils";
import { summaryOf, type Card } from "./cards";
import type { Brief, Doc, Part, ViewAction } from "./model";
import { Dot } from "./bits";
import { Children, Chevron, Files, ROW } from "./Files";

function NoSlots({ state, working }: { state: Brief["state"]; working: Working | null }) {
  const text = state === "waiting" ? "Needs your OK" : working !== null ? null : state === "empty" ? "No options yet" : "";
  return <li className="px-2 py-1 text-[13px] text-ink-3">{text ?? <Shimmer>{workingLabel(working ?? { kind: "turn" })}</Shimmer>}</li>;
}

function BriefNode(props: { working: Working | null; brief: Brief; current: boolean; slot: number | undefined; open: boolean; cards: Record<string, Card>; dispatch: Dispatch<ViewAction>; toggle: () => void }) {
  const { brief, current, slot, open, cards, dispatch, toggle, working } = props;
  const FolderIcon = open ? FolderOpen : Folder;
  return (
    <Collapsible render={<li />} open={open} onOpenChange={toggle}>
      <div className="flex items-center">
        <CollapsibleTrigger aria-label={`${brief.title} options`} className="rounded p-1 hover:bg-panel-2">
          <Chevron />
        </CollapsibleTrigger>
        <Tooltip label={brief.words}>
          <button
            type="button"
            data-brief={brief.id}
            aria-current={current}
            onClick={() => {
              dispatch({ type: "brief", briefId: brief.id });
            }}
            className={cn(ROW, "flex-1 text-[15px]", current ? "bg-panel-2 ring-1 ring-rule" : "hover:bg-panel-2/60")}
          >
            <FolderIcon className="size-4 shrink-0 text-ink-2" />
            <span className="truncate font-medium">{brief.title}</span>
            {brief.state === "waiting" ? (
              <Tooltip label="Needs your OK">
                <span role="img" aria-label="Needs your OK" data-brief-waiting className="ml-auto size-2 shrink-0 rounded-full bg-wait" />
              </Tooltip>
            ) : null}
          </button>
        </Tooltip>
      </div>
      <CollapsiblePanel>
        <Children>
          {brief.slots.length === 0 ? <NoSlots state={brief.state} working={working} /> : null}
          {brief.slots.map((one) => {
            const latest = one.revisions.at(-1);
            const on = current && one.slot === slot;
            return (
              <li key={one.slot}>
                <button
                  type="button"
                  data-slot-node={one.slot}
                  aria-current={on}
                  onClick={() => {
                    dispatch({ type: "brief", briefId: brief.id });
                    dispatch({ type: "slot", briefId: brief.id, slot: one.slot });
                  }}
                  className={cn(ROW, "w-full text-[14px]", on ? "bg-panel-2 text-ink" : "text-ink-2 hover:bg-panel-2/60")}
                >
                  <Box className="size-4 shrink-0" />
                  <span className="truncate">{one.label}</span>
                  <Dot status={summaryOf(latest ? cards[latest.variantId] : undefined).status} className="ml-auto" />
                </button>
              </li>
            );
          })}
        </Children>
      </CollapsiblePanel>
    </Collapsible>
  );
}

export function Explorer(props: {
  projectId: string;
  briefs: Brief[];
  current: string;
  slot: number | undefined;
  cards: Record<string, Card>;
  parts: Part[];
  documents: Doc[];
  sources: Source[];
  dispatch: Dispatch<ViewAction>;
  onNew: () => void;
  onChanged: () => void;
  working: Working | null;
}) {
  const { projectId, briefs, current, slot, cards, parts, documents, sources, dispatch, onNew, onChanged, working } = props;
  const [closed, setClosed] = useState<ReadonlySet<string>>(new Set());
  const toggle = (key: string) => () => {
    setClosed((was) => {
      const next = new Set(was);
      if (!next.delete(key)) next.add(key);
      return next;
    });
  };
  return (
    <section aria-label="Explorer" className="min-h-0">
      <header className="flex items-center justify-between px-4 pb-1 pt-3">
        <h2 className="text-[13px] font-medium uppercase tracking-wide text-ink-3">Explorer</h2>
        <Tooltip label="New part">
          <button type="button" onClick={onNew} aria-label="New part" className="rounded p-1 text-accent hover:bg-panel-2">
            <Plus className="size-4" />
          </button>
        </Tooltip>
      </header>
      <ul data-tree className="space-y-0.5 px-2 pb-2">
        {briefs.map((one) => (
          <BriefNode key={one.id} working={working} brief={one} current={one.id === current} slot={slot} open={!closed.has(one.id)} cards={cards} dispatch={dispatch} toggle={toggle(one.id)} />
        ))}
        <Files projectId={projectId} parts={parts} documents={documents} sources={sources} open={!closed.has("files")} toggle={toggle("files")} onChanged={onChanged} />
      </ul>
    </section>
  );
}
