/* Throwaway prototype: the project's parts (briefs), files and sources, and the way files get in. */
import { Box, Cable, FileBox, FileText, Image, Link2, LoaderCircle, Plus, Upload } from "lucide-react";
import { useRef, useState, type Dispatch, type DragEvent } from "react";
import type { Source } from "@/api/types";
import { cn } from "@/lib/utils";
import { summaryOf, type Card } from "./cards";
import type { Brief, ProjectFile, ViewAction } from "./model";
import { Dot } from "./bits";

const STATE_TEXT = { drafting: "Drafting", waiting: "Needs your OK", building: "Building", ready: "" } as const;

export function BriefList(props: {
  briefs: Brief[];
  current: string | null;
  cards: Record<string, Card>;
  dispatch: Dispatch<ViewAction>;
  onNew: () => void;
}) {
  const { briefs, current, cards, dispatch, onNew } = props;
  return (
    <section aria-label="Parts">
      <h2 className="px-4 pb-1.5 text-[13px] font-medium text-ink-3">Parts</h2>
      <ul className="space-y-1 px-2">
        {briefs.map((brief) => {
          const on = brief.id === current;
          const count = brief.slots.length;
          const first = brief.slots[0]?.revisions.at(-1);
          const summary = summaryOf(first ? cards[first.variantId] : undefined);
          return (
            <li key={brief.id}>
              <button
                type="button"
                data-brief={brief.id}
                aria-current={on}
                onClick={() => {
                  dispatch({ type: "brief", briefId: brief.id });
                }}
                className={cn("w-full rounded-lg px-3 py-2 text-left", on ? "bg-panel-2 ring-1 ring-rule" : "hover:bg-panel-2/60")}
              >
                <span className="flex items-center gap-2">
                  <span className="truncate text-[15px] font-medium">{brief.title}</span>
                  {brief.state === "waiting" ? <span className="ml-auto rounded-full bg-wait-bg px-2 text-[12px] text-wait">{STATE_TEXT.waiting}</span> : <Dot status={summary.status} className="ml-auto" />}
                </span>
                <span className="mt-0.5 line-clamp-2 text-[13px] leading-snug text-ink-2">“{brief.words}”</span>
                <span className="mt-0.5 block text-[12px] text-ink-3">
                  {count === 0 ? STATE_TEXT[brief.state] : `${String(count)} option${count === 1 ? "" : "s"}`}
                </span>
              </button>
            </li>
          );
        })}
        <li>
          <button type="button" onClick={onNew} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-[15px] text-accent hover:bg-panel-2/60">
            <Plus className="size-4" /> New part
          </button>
        </li>
      </ul>
    </section>
  );
}

const TYPE_ICON = { cad: FileBox, document: FileText, image: Image, text: FileText } as const;

export function typeOf(name: string): "cad" | "document" | "image" | "text" {
  if (/\.(step|stp|stl)$/i.test(name)) return "cad";
  if (/\.(png|jpe?g|webp)$/i.test(name)) return "image";
  if (/\.pdf$/i.test(name)) return "document";
  return "text";
}

export function Files(props: { files: ProjectFile[]; sources: Source[]; onFiles: (files: File[]) => void; bare?: boolean }) {
  const { files, sources, onFiles, bare } = props;
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [showSources, setShowSources] = useState(false);
  const drop = (event: DragEvent) => {
    event.preventDefault();
    setOver(false);
    onFiles([...event.dataTransfer.files]);
  };
  return (
    <section aria-label="Files" className="space-y-2">
      {bare ? null : <h2 className="px-4 text-[13px] font-medium text-ink-3">Files</h2>}
      <ul className="space-y-0.5 px-2">
        {files.map((one, at) => {
          if (one.kind === "source") return null;
          const Icon = one.kind === "part" ? Box : TYPE_ICON[one.type];
          return (
            <li key={at} data-file={one.kind} className="flex items-center gap-2.5 rounded-lg px-3 py-1.5">
              <Icon className="size-4 shrink-0 text-ink-2" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[14px]">{one.name}</span>
                <span className="block text-[12px] text-ink-3">{one.kind === "part" ? `${one.facts || "part"} · must fit` : one.size}</span>
              </span>
              {one.state === "waiting" ? <span className="rounded-full bg-wait-bg px-2 text-[12px] text-wait">Needs OK</span> : null}
              {one.state === "reading" ? <LoaderCircle className="size-4 text-ink-3 motion-safe:animate-spin" /> : null}
            </li>
          );
        })}
      </ul>
      <div
        data-dropzone
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => {
          setOver(false);
        }}
        onDrop={drop}
        className={cn("mx-3 rounded-xl border border-dashed px-3 py-3 text-center", over ? "border-accent bg-accent/10" : "border-rule")}
      >
        <button
          type="button"
          onClick={() => input.current?.click()}
          className="inline-flex items-center gap-2 rounded-lg border border-rule bg-panel-2 px-3 py-1.5 text-[14px] hover:bg-panel"
        >
          <Upload className="size-4" /> Add files
        </button>
        <p className="mt-1.5 text-[12px] text-ink-3">or drop CAD, PDFs, images, text</p>
        <input
          ref={input}
          type="file"
          multiple
          hidden
          data-file-input
          accept=".step,.stp,.stl,.pdf,.png,.jpg,.jpeg,.txt,.md"
          onChange={(event) => {
            onFiles([...(event.target.files ?? [])]);
            event.target.value = "";
          }}
        />
      </div>
      <button
        type="button"
        disabled
        data-onshape
        title="Coming soon"
        className="mx-3 flex w-[calc(100%-1.5rem)] items-center gap-2 rounded-lg border border-rule px-3 py-1.5 text-[14px] text-ink-3 disabled:cursor-not-allowed"
      >
        <Cable className="size-4" /> Connect Onshape
        <span className="ml-auto rounded-full bg-unk-bg px-2 text-[12px]">soon</span>
      </button>
      {sources.length > 0 ? (
        <div className="px-2">
          <button
            type="button"
            onClick={() => {
              setShowSources((was) => !was);
            }}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-1.5 text-[14px] text-ink-2 hover:bg-panel-2/60"
          >
            <Link2 className="size-4" /> {sources.length} sources the checks cite
          </button>
          {showSources ? (
            <ul className="space-y-1 px-3 pb-2">
              {sources.map((one) => (
                <li key={one.url}>
                  <a href={one.url} target="_blank" rel="noreferrer" className="line-clamp-2 text-[13px] text-accent underline">
                    {one.title}
                  </a>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
