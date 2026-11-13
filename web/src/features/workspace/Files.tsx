import { Box, ChevronRight, FileText, Folder, FolderOpen, Link2, Lock, Plus } from "lucide-react";
import { useRef, useState, type DragEvent, type ReactNode } from "react";
import { useServices } from "@/app/context";
import type { Unit } from "@/api/client";
import type { Source } from "@/api/types";
import { Collapsible, CollapsibleTrigger, CollapsiblePanel } from "@/components/ui/collapsible";
import { toast } from "@/components/ui/toaster";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { Doc, Part } from "./model";

export const ROW = "flex min-w-0 items-center gap-2 rounded-md px-2 py-1 text-left";
export const ACCEPT = ".step,.stp,.stl,.pdf,.md,.markdown,.txt,.png,.jpg,.jpeg";

export function Children({ children }: { children: ReactNode }) {
  return <ul className="ml-[18px] space-y-0.5 border-l border-rule-2 pl-1.5">{children}</ul>;
}

export function Chevron() {
  return <ChevronRight className="size-4 shrink-0 text-ink-3 transition-transform group-data-[panel-open]:rotate-90" />;
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
    <Collapsible render={<li />} open={open} onOpenChange={setOpen} data-source-folder>
      <Tooltip label={name}>
        <CollapsibleTrigger className={cn(ROW, "w-full text-[14px] hover:bg-panel-2/60")}>
          <Chevron />
          <FolderIcon className="size-4 shrink-0 text-ink-2" />
          <span className="min-w-0 flex-1 truncate">{name}</span>
          <span className="text-[12px] text-ink-3">{pages.length}</span>
        </CollapsibleTrigger>
      </Tooltip>
      <CollapsiblePanel>
        <Children>
          {pages.map((one) => (
            <li key={one.url} data-file="source">
              <Tooltip label={one.url}>
                <a href={one.url} target="_blank" rel="noreferrer" className={cn(ROW, "text-[14px] text-accent hover:bg-panel-2/60")}>
                  <Link2 className="size-4 shrink-0" />
                  <span className="truncate underline">{pageOf(one)}</span>
                </a>
              </Tooltip>
            </li>
          ))}
        </Children>
      </CollapsiblePanel>
    </Collapsible>
  );
}

const isStl = (file: File) => file.name.toLowerCase().endsWith(".stl");
const isPdf = (file: File) => file.name.toLowerCase().endsWith(".pdf");
const asksFirst = (file: File) => isStl(file) || isPdf(file);

const said = (error: unknown) => (error instanceof Error ? error.message : String(error));

/** Sends each file in turn. An STL holds no units, so it waits until the person picks mm or inches. A PDF waits until the person says whether it is a licensed standard to keep from the agent. */
function useAdding(projectId: string, onChanged: () => void) {
  const { api } = useServices();
  const [queue, setQueue] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const send = async (file: File, unit: Unit | null, withheld: boolean, rest: File[]) => {
    setBusy(true);
    setProblem(null);
    try {
      await api.addFile(projectId, file, unit, withheld);
      onChanged();
    } catch (error) {
      setProblem(`${file.name}: ${said(error)}`);
    } finally {
      setBusy(false);
    }
    await next(rest);
  };
  const next = async (files: File[]) => {
    const [first, ...rest] = files;
    setQueue(first && asksFirst(first) ? files : []);
    if (first && !asksFirst(first)) await send(first, null, false, rest);
  };
  return {
    asking: queue[0] ?? null,
    busy,
    problem,
    add: (files: File[]) => void next([...queue, ...files]),
    unit: (unit: Unit) => {
      const [first, ...rest] = queue;
      if (first) void send(first, unit, false, rest);
    },
    standard: (withheld: boolean) => {
      const [first, ...rest] = queue;
      if (first) void send(first, null, withheld, rest);
    },
  };
}

function UnitPrompt({ file, onUnit }: { file: File; onUnit: (unit: Unit) => void }) {
  return (
    <li role="group" aria-label={`Units of ${file.name}`} className="space-y-1 rounded-md bg-wait-bg px-2 py-1.5 text-[13px]">
      <p>An STL file holds no units. What unit is {file.name} in?</p>
      <div className="flex gap-2">
        {(
          [
            ["mm", "Millimetres"],
            ["in", "Inches"],
          ] as const
        ).map(([unit, label]) => (
          <button
            key={unit}
            type="button"
            onClick={() => {
              onUnit(unit);
            }}
            className="rounded border border-rule bg-panel px-2 py-0.5 hover:bg-panel-2"
          >
            {label}
          </button>
        ))}
      </div>
    </li>
  );
}

function StandardPrompt({ file, onChoice }: { file: File; onChoice: (withheld: boolean) => void }) {
  return (
    <li role="group" aria-label={`Is ${file.name} a licensed standard?`} className="space-y-1 rounded-md bg-wait-bg px-2 py-1.5 text-[13px]">
      <p>Is {file.name} a licensed standard, such as a DIN or ISO document?</p>
      <p className="text-ink-3">If it is, the agent never reads it. It stays in the project, and a requirement can cite it when you type the words from it yourself.</p>
      <div className="flex gap-2">
        {(
          [
            [false, "No, the agent may read it"],
            [true, "Yes, keep it from the agent"],
          ] as const
        ).map(([withheld, label]) => (
          <button
            key={label}
            type="button"
            onClick={() => {
              onChoice(withheld);
            }}
            className="rounded border border-rule bg-panel px-2 py-0.5 hover:bg-panel-2"
          >
            {label}
          </button>
        ))}
      </div>
    </li>
  );
}

function PartRow({ part, onDecline }: { part: Part; onDecline: (() => void) | null }) {
  return (
    <li data-file="part" className={cn(ROW, "text-[14px]")}>
      <Box className="size-4 shrink-0 text-ink-2" />
      <span className="min-w-0 flex-1">
        <span className="block truncate">{part.name}</span>
        <span className="block text-[12px] text-ink-3">
          {part.size} · {part.uploaded ? "supplied by you" : "must fit"}
        </span>
        {part.leftOut ? <span className="block text-[12px] text-wait">{part.leftOut}</span> : null}
      </span>
      {part.state === "waiting" ? <span className="rounded-full bg-wait-bg px-2 text-[12px] text-wait">Needs OK</span> : null}
      {part.state === "declined" ? <span className="text-[12px] text-ink-3">Declined</span> : null}
      {onDecline && part.state === "confirmed" ? (
        <button type="button" onClick={onDecline} aria-label={`Decline ${part.name}`} className="rounded px-1.5 text-[12px] text-ink-3 hover:bg-panel-2 hover:text-ink">
          Decline
        </button>
      ) : null}
    </li>
  );
}

export function Files(props: { projectId: string; parts: Part[]; documents: Doc[]; sources: Source[]; open: boolean; toggle: () => void; onChanged: () => void }) {
  const { projectId, parts, documents, sources, open, toggle, onChanged } = props;
  const { api } = useServices();
  const adding = useAdding(projectId, onChanged);
  const picker = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const FolderIcon = open ? FolderOpen : Folder;
  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setOver(false);
    adding.add([...event.dataTransfer.files]);
  };
  const decline = (part: Part) => () => {
    api.declinePart(projectId, part.id).then(onChanged, (error: unknown) => toast.error(`${part.name}: ${said(error)}`));
  };
  const empty = parts.length === 0 && documents.length === 0 && sources.length === 0;
  return (
    <Collapsible
      render={<li />}
      open={open}
      onOpenChange={toggle}
      data-files-drop
      onDragOver={(event: DragEvent) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => {
        setOver(false);
      }}
      onDrop={onDrop}
      className={cn("rounded-md", over && "ring-2 ring-accent")}
    >
      <div className="flex items-center">
        <CollapsibleTrigger className="flex min-w-0 flex-1 items-center gap-1 rounded-md py-1 pl-1 pr-2 text-left text-[15px] font-medium hover:bg-panel-2/60">
          <Chevron />
          <FolderIcon className="size-4 shrink-0 text-ink-2" />
          Files
        </CollapsibleTrigger>
        <Tooltip label="Add a STEP or STL part, or a PDF, Markdown, text or image file" onDisabled={adding.busy}>
          <button
            type="button"
            disabled={adding.busy}
            aria-label="Add files"
            onClick={() => picker.current?.click()}
            className="rounded p-1 text-accent hover:bg-panel-2 disabled:text-ink-3"
          >
            <Plus className="size-4" />
          </button>
        </Tooltip>
        <input
          ref={picker}
          type="file"
          multiple
          accept={ACCEPT}
          aria-label="Choose files"
          className="hidden"
          onChange={(event) => {
            adding.add([...(event.target.files ?? [])]);
            event.target.value = "";
          }}
        />
      </div>
      <CollapsiblePanel>
        <Children>
          {adding.asking && isStl(adding.asking) ? <UnitPrompt file={adding.asking} onUnit={adding.unit} /> : null}
          {adding.asking && isPdf(adding.asking) ? <StandardPrompt file={adding.asking} onChoice={adding.standard} /> : null}
          {adding.busy ? <li className="px-2 py-1 text-[13px] text-ink-3">Reading the file…</li> : null}
          {adding.problem ? (
            <li role="alert" className="px-2 py-1 text-[13px] text-fail">
              {adding.problem}
            </li>
          ) : null}
          {parts.map((one) => (
            <PartRow key={one.id} part={one} onDecline={one.uploaded ? decline(one) : null} />
          ))}
          {documents.map((one) => (
            <li key={one.id} data-file="document" className={cn(ROW, "text-[14px]")}>
              {one.withheld ? <Lock className="size-4 shrink-0 text-ink-2" /> : <FileText className="size-4 shrink-0 text-ink-2" />}
              <span className="min-w-0 flex-1">
                <span className="block truncate">{one.name}</span>
                {one.withheld ? <span className="block text-[12px] text-ink-3">Standard, kept from the agent</span> : null}
              </span>
            </li>
          ))}
          {byDocument(sources).map(([name, pages]) => (
            <SourceFolder key={name} name={name} pages={pages} />
          ))}
          {empty ? <li className="px-2 py-1 text-[13px] text-ink-3">Drop STEP, STL, PDF or text files here</li> : null}
        </Children>
      </CollapsiblePanel>
    </Collapsible>
  );
}
