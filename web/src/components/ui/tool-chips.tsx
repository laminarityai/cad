import { useState } from "react";
import { Check, ChevronDown, X } from "lucide-react";
import { Collapsible, CollapsibleTrigger, CollapsiblePanel } from "@/components/ui/collapsible";
import { Shimmer, Spinner } from "@/components/ui/busy";
import { cn } from "@/lib/utils";

/*
 * Cut down from Beautiful UI's Tool Chips (https://www.beautifului.dev), MIT, Copyright (c) 2026
 * Shane Levine.
 */

export interface ToolRow {
  key: number;
  label: string;
  chip: string | null;
  status: "running" | "done" | "refused";
  detail: readonly string[];
}

function Row({ row }: { row: ToolRow }) {
  const icon =
    row.status === "running" ? <Spinner className="size-4" /> : row.status === "refused" ? <X aria-hidden className="size-4 shrink-0 text-fail" /> : <Check aria-hidden className="size-4 shrink-0 text-ink-3" />;
  const head = (
    <>
      {icon}
      <span className="shrink-0 text-ink">{row.status === "running" ? <Shimmer>{row.label}</Shimmer> : row.label}</span>
      {row.chip === null ? null : <span className="min-w-0 truncate rounded-md border border-rule-2 bg-panel-2 px-1.5 py-px font-mono text-[12px] text-ink-2">{row.chip}</span>}
      {row.status === "refused" ? <span className="text-fail">refused</span> : null}
    </>
  );
  if (row.detail.length === 0) return <li data-tool={row.status} className="flex h-7 items-center gap-2">{head}</li>;
  return (
    <Collapsible render={<li />} data-tool={row.status}>
      <CollapsibleTrigger className="flex h-7 w-full items-center gap-2 text-left hover:bg-panel-2/60">
        {head}
        <ChevronDown aria-hidden className="ml-auto size-3.5 shrink-0 transition-transform group-data-[panel-open]:rotate-180" />
      </CollapsibleTrigger>
      <CollapsiblePanel>
        <ul className="mb-1 ml-2 space-y-0.5 border-l border-rule pl-3 font-mono text-[12px] text-ink-2">
          {row.detail.map((line) => (
            <li key={line} className="truncate">
              {line}
            </li>
          ))}
        </ul>
      </CollapsiblePanel>
    </Collapsible>
  );
}

export function ToolChips({ summary, rows, live }: { summary: string; rows: readonly ToolRow[]; live: boolean }) {
  const running = rows.some((one) => one.status === "running");
  const [chosen, choose] = useState<boolean | null>(null);
  const open = chosen ?? live;
  return (
    <Collapsible data-activity open={open} onOpenChange={choose} className="text-[13px] text-ink-3">
      <CollapsibleTrigger className="flex items-center gap-1.5">
        {running ? <Spinner className="size-3.5" /> : null}
        <span className={cn(running && "text-ink-2")}>{summary}</span>
        <ChevronDown aria-hidden className="size-3.5 transition-transform group-data-[panel-open]:rotate-180" />
      </CollapsibleTrigger>
      <CollapsiblePanel>
        <ul className="mt-1 space-y-0.5">
          {rows.map((row) => (
            <Row key={row.key} row={row} />
          ))}
        </ul>
      </CollapsiblePanel>
    </Collapsible>
  );
}
