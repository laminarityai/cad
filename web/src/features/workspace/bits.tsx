import { ChevronDown, CircleCheck, CircleDashed, CircleX, LoaderCircle, Sparkles } from "lucide-react";
import { Collapsible, CollapsibleTrigger, CollapsiblePanel } from "@/components/ui/collapsible";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { Line, Status } from "./cards";
import { assumedOf, awaitingOf, linesOf, type Card } from "./cards";
import type { Material } from "./model";

const DOT: Record<Status | "none", string> = {
  pass: "bg-pass",
  researched: "bg-res",
  agent: "bg-accent",
  fail: "bg-fail",
  unknown: "bg-unk",
  running: "bg-wait motion-safe:animate-pulse",
  unchecked: "bg-rule",
  none: "bg-rule",
};

export function Dot({ status, className }: { status: Status | "none"; className?: string }) {
  return <span aria-hidden className={cn("inline-block size-2.5 shrink-0 rounded-full", DOT[status], className)} />;
}

const PILL: Record<Status, { text: string; tone: string; Icon: typeof CircleCheck }> = {
  pass: { text: "Pass", tone: "text-pass", Icon: CircleCheck },
  researched: { text: "Pass", tone: "text-res", Icon: Sparkles },
  agent: { text: "Pass", tone: "text-accent", Icon: CircleCheck },
  fail: { text: "Fail", tone: "text-fail", Icon: CircleX },
  unknown: { text: "Unknown", tone: "text-unk", Icon: CircleDashed },
  running: { text: "Checking", tone: "text-wait", Icon: LoaderCircle },
  unchecked: { text: "No test yet", tone: "text-ink-3", Icon: CircleDashed },
};

function Row({ line }: { line: Line }) {
  const pill = PILL[line.status];
  const more = line.why !== "" || line.formula !== "" || line.sources.length > 0;
  return (
    <Collapsible render={<li />} data-line={line.status} className="border-b border-rule-2 last:border-b-0">
      <CollapsibleTrigger
        disabled={!more}
        className="flex w-full items-start gap-2.5 px-4 py-2.5 text-left hover:bg-panel-2 disabled:cursor-default"
      >
        <pill.Icon className={cn("mt-0.5 size-[18px] shrink-0", pill.tone, line.status === "running" && "motion-safe:animate-spin")} />
        <span className="min-w-0 flex-1 text-[15px] leading-snug">{line.label}</span>
        <span className="shrink-0 text-right">
          {line.value ? <span className="block font-mono text-[14px] tabular-nums">{line.value}</span> : <span className={cn("block text-[13px]", pill.tone)}>{pill.text}</span>}
          {line.status === "researched" ? <span className="block text-[12px] text-res">researched</span> : null}
          {line.tag ? (
            <span data-tag className="block max-w-48 text-[12px] leading-tight text-accent">
              {line.tag}
            </span>
          ) : null}
        </span>
      </CollapsibleTrigger>
      <CollapsiblePanel className="space-y-1.5 px-4 pb-3 pl-11 text-[14px] text-ink-2">
        {line.why ? <p>{line.why}</p> : null}
        {line.sources.slice(0, 2).map((one) => (
          <a key={one.url} href={one.url} target="_blank" rel="noreferrer" className="block truncate text-accent underline">
            {one.title}
          </a>
        ))}
      </CollapsiblePanel>
    </Collapsible>
  );
}

function AwaitingRows({ rows }: { rows: ReturnType<typeof awaitingOf> }) {
  return (
    <>
      <h3 className="px-4 pb-1 pt-3 text-[13px] font-medium text-ink-3">Awaiting your Confirm</h3>
      <ul data-awaiting>
        {rows.map((one) => (
          <li key={one.key} className="border-b border-rule-2 px-4 py-2.5 last:border-b-0">
            <p className="text-[15px] leading-snug">{one.label}</p>
            <p className="text-[13px] text-wait">Waiting for you, no verdict yet</p>
            {one.values.map((value) => (
              <p key={value.measure} className="font-mono text-[14px] tabular-nums text-ink-2">
                {value.measure}: {value.measured ?? "not measured"}, your target {value.target}
              </p>
            ))}
          </li>
        ))}
      </ul>
    </>
  );
}

function AssumedRows({ rows }: { rows: ReturnType<typeof assumedOf> }) {
  return (
    <>
      <h3 className="px-4 pb-1 pt-3 text-[13px] font-medium text-ink-3">Assumed by the agent</h3>
      <ul data-assumed>
        {rows.map((one) => (
          <li key={one.key} className="border-b border-rule-2 px-4 py-2.5 last:border-b-0">
            <p className="text-[15px] leading-snug">{one.label}</p>
            <p className="text-[13px] text-ink-3">{one.why}</p>
            {one.values.map((value) => (
              <p key={value.measure} className="font-mono text-[14px] tabular-nums text-ink-2">
                {value.measure}: {value.measured ?? "not measured"}, assumed {value.assumed}
              </p>
            ))}
          </li>
        ))}
      </ul>
    </>
  );
}

export function materialLabel(material: Material): string {
  return `${material.name} · ${material.chosenBy === "agent" ? "chosen by the agent" : "from your words"}`;
}

function MaterialLabel({ material }: { material: Material }) {
  const label = (
    <span data-material className="text-[13px] text-ink-2">
      {materialLabel(material)}
    </span>
  );
  return material.chosenBy === "agent" ? <Tooltip label="Ask in the chat to change it.">{label}</Tooltip> : label;
}

export function Checks({ card, material }: { card: Card | undefined; material: Material | null }) {
  const snapshot = card?.snapshot ?? null;
  const { asked, also } = snapshot ? linesOf(snapshot) : { asked: [], also: [] };
  const assumed = snapshot ? assumedOf(snapshot) : [];
  const waiting = snapshot ? awaitingOf(snapshot) : [];
  const loud = also.filter((one) => one.status !== "pass" && one.status !== "researched");
  const quiet = also.filter((one) => one.status === "pass" || one.status === "researched");
  return (
    <section aria-label="Checks" className="flex min-h-0 flex-col">
      <header className="flex items-baseline justify-between gap-2 px-4 pb-2 pt-3">
        <h2 className="text-[16px] font-semibold">Checks</h2>
        {material ? (
          <MaterialLabel material={material} />
        ) : null}
      </header>
      {!card ? (
        <p className="px-4 py-3 text-[15px] text-ink-3">Checks show once an option is built.</p>
      ) : !snapshot ? (
        <p className="flex items-center gap-2 px-4 py-3 text-[15px] text-ink-2">
          <LoaderCircle className="size-4 motion-safe:animate-spin" /> Checking
        </p>
      ) : (
        <div className="min-h-0 overflow-y-auto">
          {asked.length > 0 ? (
            <>
              <h3 className="px-4 pb-1 pt-2 text-[13px] font-medium text-ink-3">What you asked</h3>
              <ul>
                {asked.map((one) => (
                  <Row key={one.key} line={one} />
                ))}
              </ul>
            </>
          ) : null}
          {waiting.length > 0 ? <AwaitingRows rows={waiting} /> : null}
          {loud.length > 0 ? (
            <>
              <h3 className="px-4 pb-1 pt-3 text-[13px] font-medium text-ink-3">Needs a look</h3>
              <ul>
                {loud.map((one) => (
                  <Row key={one.key} line={one} />
                ))}
              </ul>
            </>
          ) : null}
          {quiet.length > 0 ? (
            <Collapsible>
              <CollapsibleTrigger className="flex w-full items-center gap-1.5 px-4 pb-1 pt-3 text-[13px] font-medium text-ink-3">
                <CircleCheck className="size-4 text-pass" /> {quiet.length} more passed
                <ChevronDown className="size-4 transition-transform group-data-[panel-open]:rotate-180" />
              </CollapsibleTrigger>
              <CollapsiblePanel>
                <ul>
                  {quiet.map((one) => (
                    <Row key={one.key} line={one} />
                  ))}
                </ul>
              </CollapsiblePanel>
            </Collapsible>
          ) : null}
          {assumed.length > 0 ? <AssumedRows rows={assumed} /> : null}
        </div>
      )}
    </section>
  );
}
