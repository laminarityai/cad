import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Row } from "./rows";

type Tone = "pass" | "fail" | "researched" | "unknown" | "pending" | "neutral";

function chip(row: Row): { tone: Tone; text: string } {
  switch (row.kind) {
    case "pending":
      return { tone: "pending", text: "pending" };
    case "unverified":
      return { tone: "neutral", text: "not checked" };
    case "settled":
      if (row.verdict === "pass" && row.researched) return { tone: "researched", text: "pass · researched" };
      return { tone: row.verdict, text: row.verdict };
  }
}

export function ScoreRow({ row, ghost }: { row: Row; ghost?: string | undefined }) {
  const [open, setOpen] = useState(false);
  const { tone, text } = chip(row);
  const note = row.kind === "settled" ? row.note : "";
  return (
    <li
      data-row={row.kind}
      data-key={row.key}
      className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-2.5 gap-y-0.5 border-t border-rule-2 px-2.5 py-2 first:border-t-0"
    >
      <span className="min-w-0 break-words font-mono text-xs">{row.label}</span>
      <Badge tone={tone} className="self-start justify-self-end">
        {text}
      </Badge>
      {row.kind === "settled" && row.measures.length > 0 ? (
        <span className="col-span-2 font-mono text-xs tabular-nums text-ink-2">{row.measures.join("; ")}</span>
      ) : null}
      {row.kind === "pending" && ghost ? (
        <span data-ghost className="col-span-2 font-mono text-[11px] text-ink-3">
          before: {ghost}
        </span>
      ) : null}
      {row.kind === "settled" && row.researched ? (
        <span className="col-span-2 font-mono text-[10.5px] text-res">◆ rests on researched data</span>
      ) : null}
      {note ? (
        <button
          type="button"
          aria-expanded={open}
          onClick={() => {
            setOpen((was) => !was);
          }}
          className={cn(
            "col-span-2 cursor-pointer text-left text-xs text-ink-2",
            open ? "whitespace-normal" : "truncate",
          )}
        >
          {note}
        </button>
      ) : null}
    </li>
  );
}
