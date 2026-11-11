import { Box, ChevronRight, Folder, FolderOpen, Link2, Plus } from "lucide-react";
import { useState, type Dispatch, type ReactNode } from "react";
import type { Source } from "@/api/types";
import { cn } from "@/lib/utils";
import { summaryOf, type Card } from "./cards";
import type { Brief, Part, ViewAction } from "./model";
import { Dot } from "./bits";

const STATE_TEXT = {
  drafting: "Drafting",
  waiting: "Needs your OK",
  building: "Building",
  ready: "",
} as const;

const ROW = "flex min-w-0 items-center gap-2 rounded-md px-2 py-1 text-left";

function Children({ children }: { children: ReactNode }) {
  return <ul className="ml-[18px] space-y-0.5 border-l border-rule-2 pl-1.5">{children}</ul>;
}

function Chevron({ open }: { open: boolean }) {
  return <ChevronRight className={cn("size-4 shrink-0 text-ink-3 transition-transform", open && "rotate-90")} />;
}

function Part(props: { brief: Brief; current: boolean; slot: number | undefined; open: boolean; cards: Record<string, Card>; dispatch: Dispatch<ViewAction>; toggle: () => void }) {
  const { brief, current, slot, open, cards, dispatch, toggle } = props;
  const FolderIcon = open ? FolderOpen : Folder;
  return (
    <li>
      <div className="flex items-center">
        <button type="button" aria-expanded={open} aria-label={`${brief.title} options`} onClick={toggle} className="rounded p-1 hover:bg-panel-2">
          <Chevron open={open} />
        </button>
        <button
          type="button"
          data-brief={brief.id}
          aria-current={current}
          title={brief.words}
          onClick={() => {
            dispatch({ type: "brief", briefId: brief.id });
          }}
          className={cn(ROW, "flex-1 text-[15px]", current ? "bg-panel-2 ring-1 ring-rule" : "hover:bg-panel-2/60")}
        >
          <FolderIcon className="size-4 shrink-0 text-ink-2" />
          <span className="truncate font-medium">{brief.title}</span>
          {brief.state === "waiting" ? <span role="img" aria-label="Needs your OK" title="Needs your OK" data-brief-waiting className="ml-auto size-2 shrink-0 rounded-full bg-wait" /> : null}
        </button>
      </div>
      {open ? (
        <Children>
          {brief.slots.length === 0 ? <li className="px-2 py-1 text-[13px] text-ink-3">{STATE_TEXT[brief.state]}</li> : null}
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
      ) : null}
    </li>
  );
}

function siteOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

const TITLE_PARTS = /\s+[|–—-]\s+|:\s+/;

const documentOf = (one: Source) => one.title.split(TITLE_PARTS)[0]?.trim() || siteOf(one.url);

function pageOf(one: Source): string {
  const rest = one.title.split(TITLE_PARTS).slice(1).join(" · ").trim();
  return [rest, one.page].filter(Boolean).join(", ") || siteOf(one.url);
}

function byDocument(sources: Source[]): [string, Source[]][] {
  const groups = new Map<string, Source[]>();
  for (const one of sources) groups.set(documentOf(one), [...(groups.get(documentOf(one)) ?? []), one]);
  return [...groups];
}

function SourceFolder({ name, pages }: { name: string; pages: Source[] }) {
  const [open, setOpen] = useState(false);
  const FolderIcon = open ? FolderOpen : Folder;
  return (
    <li data-source-folder>
      <button
        type="button"
        aria-expanded={open}
        title={name}
        onClick={() => {
          setOpen((was) => !was);
        }}
        className={cn(ROW, "w-full text-[14px] hover:bg-panel-2/60")}
      >
        <Chevron open={open} />
        <FolderIcon className="size-4 shrink-0 text-ink-2" />
        <span className="min-w-0 flex-1 truncate">{name}</span>
        <span className="text-[12px] text-ink-3">{pages.length}</span>
      </button>
      {open ? (
        <Children>
          {pages.map((one) => (
            <li key={one.url} data-file="source">
              <a href={one.url} target="_blank" rel="noreferrer" title={one.url} className={cn(ROW, "text-[14px] text-accent hover:bg-panel-2/60")}>
                <Link2 className="size-4 shrink-0" />
                <span className="truncate underline">{pageOf(one)}</span>
              </a>
            </li>
          ))}
        </Children>
      ) : null}
    </li>
  );
}

function Files(props: { parts: Part[]; sources: Source[]; open: boolean; toggle: () => void }) {
  const { parts, sources, open, toggle } = props;
  const FolderIcon = open ? FolderOpen : Folder;
  return (
    <li>
      <div className="flex items-center">
        <button type="button" aria-expanded={open} onClick={toggle} className="flex min-w-0 flex-1 items-center gap-1 rounded-md py-1 pl-1 pr-2 text-left text-[15px] font-medium hover:bg-panel-2/60">
          <Chevron open={open} />
          <FolderIcon className="size-4 shrink-0 text-ink-2" />
          Files
        </button>
        <button type="button" disabled title="Coming soon" aria-label="Add files" className="rounded p-1 text-ink-3 disabled:cursor-not-allowed">
          <Plus className="size-4" />
        </button>
      </div>
      {open ? (
        <Children>
          {parts.map((one, at) => (
            <li key={at} data-file="part" className={cn(ROW, "text-[14px]")}>
              <Box className="size-4 shrink-0 text-ink-2" />
              <span className="min-w-0 flex-1">
                <span className="block truncate">{one.name}</span>
                <span className="block text-[12px] text-ink-3">{one.size} · must fit</span>
              </span>
              {one.state === "waiting" ? <span className="rounded-full bg-wait-bg px-2 text-[12px] text-wait">Needs OK</span> : null}
              {one.state === "declined" ? <span className="text-[12px] text-ink-3">Declined</span> : null}
            </li>
          ))}
          {byDocument(sources).map(([name, pages]) => (
            <SourceFolder key={name} name={name} pages={pages} />
          ))}
          {parts.length === 0 && sources.length === 0 ? <li className="px-2 py-1 text-[13px] text-ink-3">Nothing yet</li> : null}
        </Children>
      ) : null}
    </li>
  );
}

export function Explorer(props: {
  briefs: Brief[];
  current: string;
  slot: number | undefined;
  cards: Record<string, Card>;
  parts: Part[];
  sources: Source[];
  dispatch: Dispatch<ViewAction>;
  onNew: () => void;
}) {
  const { briefs, current, slot, cards, parts, sources, dispatch, onNew } = props;
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
        <button type="button" onClick={onNew} aria-label="New part" title="New part" className="rounded p-1 text-accent hover:bg-panel-2">
          <Plus className="size-4" />
        </button>
      </header>
      <ul data-tree className="space-y-0.5 px-2 pb-2">
        {briefs.map((one) => (
          <Part key={one.id} brief={one} current={one.id === current} slot={slot} open={!closed.has(one.id)} cards={cards} dispatch={dispatch} toggle={toggle(one.id)} />
        ))}
        <Files parts={parts} sources={sources} open={!closed.has("files")} toggle={toggle("files")} />
      </ul>
    </section>
  );
}
